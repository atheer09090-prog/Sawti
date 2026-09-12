import os
import re
import json
import time
import logging
import urllib.request
import tempfile
from typing import Optional
from groq import Groq

from app.services.stt_correction import (
    find_fuzzy_hints,
    apply_word_corrections,
    validate_word_substitution,
)

logger = logging.getLogger("sawti.speech_eval")

# كلمات عامة شائعة تساعد Whisper على التعرف الصحيح (تُستخدم دائماً كأساس).
# هذا الـ prompt هو "سياق مساعد" فقط لِـ Whisper (initial prompt) وليس نصاً
# يُفرَض على النموذج — لا يجعل Whisper يخترع كلمات لم يقلها الطالب، فقط يرفع
# احتمال التعرف الصحيح عند التباس صوتي بسيط.
BASE_ARABIC_PROMPT = (
    "هذا تسجيل صوتي لطالب عُماني في الصف السادس يتحدث باللغة العربية الفصحى بصوت طفل، "
    "بشكل حر وتلقائي وليس قراءة نص محفوظ. "
    "قد يتحدث بلهجة خليجية يُنطق فيها حرف الجيم أحياناً بصوت قريب من القاف (كما في كلمة الجو والجزر). "
    "اكتب فقط ما يُنطق فعلياً بدقة، دون إضافة أو حذف أو تحسين الصياغة. "
    "كلمات شائعة في حديث الطلاب: ذهبنا، قمنا، رأينا، شاهدنا، جميلة، رائعة، ممتعة، كثيراً، أيضاً، لقد، وقد، فقد، "
    "أعتقد، في رأيي، لأن، لذلك، أولاً، ثانياً، أخيراً."
)

# مفردات إضافية خاصة بكل موضوع/درس — كلما كانت أدق كانت دقة النسخ أعلى.
# نفس الكلمات المستخدمة في صفحات "الكلمات المساعدة" بالفرونت إند (Speaking.tsx / Writing.tsx)،
# مكرَّرة هنا عمداً لتغذية Whisper مباشرة قبل النسخ (وليس لعرضها للمستخدم).
TOPIC_VOCAB: dict[str, str] = {
    "رحلة بحرية": "البحر، السفينة، الشاطئ، الأمواج، السمك، الغوص، السباحة، الرمال، الشمس، المنظر الجميل",
    "رحلة جبلية": "الجبل، القمة، التسلق، الهواء النقي، الأشجار، المخيم، المشي، الطبيعة، البرودة، المنظر الخلاب",
    "رحلة جوية": "الطائرة، المطار، الرحلة، السفر، الجواز، الحقائب، السماء، المضيف، المقعد، الهبوط",
    "صورة دالة على تعلم": "التعلم، المعرفة، المعلم، الكتاب، المهارة، التجربة، الاكتشاف، الفهم، التدريب، النجاح",
    "الأجهزة الإلكترونية": "الهاتف، الإنترنت، الدراسة، الترفيه، تنظيم الوقت، مفيد، مضر",
    "البيئة": "البيئة، الأشجار، التلوث، النظافة، إعادة التدوير، المياه، المسؤولية، التعاون، المستقبل، المحافظة",
    "القراءة": "القراءة، المعرفة، التعلم، الكتب، المكتبة، المعلومات، الفهم، التركيز، الخيال، الثقافة",
    "ساعة الأرض": "ساعة الأرض، البيئة، المحافظة، الطاقة، الكهرباء، ترشيد، المشاركة، المجتمع، كوكب الأرض، التلوث، الوعي",
}


def _build_prompt(topic_hint: str = "") -> str:
    """يبني توجيهاً (Prompt) لِـ Whisper: الأساس العام + مفردات الموضوع المطابقة إن وُجدت."""
    prompt = BASE_ARABIC_PROMPT
    if topic_hint:
        clean_hint = re.sub(r"[\u064B-\u065F\u0670]", "", topic_hint)  # إزالة التشكيل قبل المطابقة
        for key, vocab in TOPIC_VOCAB.items():
            if key in clean_hint or clean_hint in key:
                prompt = f"{prompt} قد يستخدم الطالب بعض هذه الكلمات لأن موضوعه هو ({topic_hint}): {vocab}."
                break
    return prompt


def _topic_vocab_list(topic_hint: str = "") -> list[str]:
    """يُعيد قائمة كلمات مفردات الموضوع (بدون فواصل) لاستخدامها في المقارنة
    الصوتية (Layer 3)، بالاعتماد على نفس TOPIC_VOCAB المستخدم مع Whisper."""
    if not topic_hint:
        return []
    clean_hint = re.sub(r"[\u064B-\u065F\u0670]", "", topic_hint)
    for key, vocab in TOPIC_VOCAB.items():
        if key in clean_hint or clean_hint in key:
            return [w.strip() for w in vocab.split("،") if w.strip()]
    return []


# تصحيح ما بعد النسخ لالتباسات صوتية شائعة في اللهجة الخليجية/العُمانية (القاف تُسمع مكان الجيم
# أحياناً بسبب طريقة النطق المحلية). هذه مطابقة "كلمة كاملة" وليست استبدال حرف عام، لتفادي
# إفساد كلمات صحيحة تحتوي فعلاً على قاف (مثل: قمنا، قارب، قال).
#
# ملاحظة: تعمّدت عدم إضافة بعض الكلمات رغم شيوعها في مواضيعنا لأنها قد تتعارض مع كلمات
# شائعة جداً وصحيحة بالقاف، فتُفسد أكثر مما تصلح:
#   - "جبل/الجبل" (رحلة جبلية) → لم تُضَف لأن "قبل" من أكثر الكلمات استخداماً في العربية
#   - "جوي/جوية/جواً" (رحلة جوية) → لم تُضَف لأن "قوي/قوية/أقوى" شائعة جداً (خصوصاً في دروس الهمزة)
#   - "جاء" → لم تُضَف لأن "قاء" كلمة حقيقية أيضاً ولا يمكن ترجيح إحداهما بثقة
PHONETIC_CONFUSIONS: dict[str, str] = {
    # عام
    "القو": "الجو", "قو": "جو",
    "القزر": "الجزر", "قزر": "جزر",
    "البعر": "البحر", "بعر": "بحر",
    "قدا": "جدا",
    "قميل": "جميل", "قميلا": "جميلا", "قميلة": "جميلة",
    "القميع": "الجميع", "قميع": "جميع",
    # رحلة بحرية / جبلية (كلمات مفتاحية)
    "الأمواق": "الأمواج", "أمواق": "أمواج",
    "الأشقار": "الأشجار", "أشقار": "أشجار",
    "القزيرة": "الجزيرة", "قزيرة": "جزيرة",
    # رحلة جوية
    "القواز": "الجواز", "قواز": "جواز",
    # الأجهزة الإلكترونية / التعلم
    "الأقهزة": "الأجهزة", "أقهزة": "أجهزة", "قهاز": "جهاز", "القهاز": "الجهاز",
    "التقربة": "التجربة", "تقربة": "تجربة",
    # البيئة / ساعة الأرض / التعبير عن الرأي
    "المقتمع": "المجتمع", "مقتمع": "مجتمع",
    # وصف المسجد (كتابة)
    "المسقد": "المسجد", "مسقد": "مسجد",
}
_TASHKEEL_RE = re.compile(r"[\u064B-\u065F\u0670]")


_PREFIX_LETTERS = ("و", "ف", "ب", "ك", "ل")

# التباسات صوتية مرتبطة بموضوع مُحدَّد فقط (وليست عامة)، لأن الكلمة الملتبَسة
# صحيحة ومختلفة المعنى في مواضيع أخرى، فلا يصح استبدالها إلا ضمن سياق موضوعها.
# مثال: "الأموال" كلمة صحيحة تماماً (بمعنى المال)، لكنها في سياق "رحلة بحرية"
# غالباً ما تكون نتيجة سماع خاطئ لكلمة "الأمواج".
TOPIC_PHONETIC_CONFUSIONS: dict[str, dict[str, str]] = {
    "رحلة بحرية": {
        "الأموال": "الأمواج", "أموال": "أمواج",
    },
}


def _fix_phonetic_confusions(text: str, topic_hint: str = "") -> str:
    local_confusions = dict(PHONETIC_CONFUSIONS)
    if topic_hint:
        clean_hint = re.sub(r"[\u064B-\u065F\u0670]", "", topic_hint)
        for key, confusions in TOPIC_PHONETIC_CONFUSIONS.items():
            if key in clean_hint or clean_hint in key:
                local_confusions.update(confusions)
                break

    def repl(m: "re.Match[str]") -> str:
        word = m.group(0)
        clean = _TASHKEEL_RE.sub("", word)
        if clean in local_confusions:
            return local_confusions[clean]
        # حاول إزالة حرف عطف/جر ملتصق بالكلمة (مثل: والجزر، بالجزر) ثم أعِد مطابقتها
        if len(clean) > 2 and clean[0] in _PREFIX_LETTERS:
            rest = clean[1:]
            if rest in local_confusions:
                return clean[0] + local_confusions[rest]
        return word
    return re.sub(r"[\w\u0621-\u064A\u064B-\u065F\u0670]+", repl, text)


def transcribe_arabic_audio(audio_bytes: bytes, audio_format: str = "wav", topic_hint: str = "") -> str:
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    logger.info("Whisper request: format=%s size_bytes=%d topic_hint_set=%s",
                audio_format, len(audio_bytes), bool(topic_hint))

    with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    t0 = time.monotonic()
    try:
        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(f"recording.{audio_format}", audio_file.read()),
                model="whisper-large-v3",
                language="ar",
                response_format="text",
                prompt=_build_prompt(topic_hint),
                temperature=0.0,  # أقل عشوائية = أدق
            )
        raw = transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
        fixed = _fix_phonetic_confusions(raw, topic_hint=topic_hint)
        logger.info("Whisper response: duration_s=%.2f raw_word_count=%d layer1_changed=%s",
                    time.monotonic() - t0, len(raw.split()), raw != fixed)
        logger.debug("Whisper raw transcript: %s", raw)
        return fixed
    finally:
        os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════════════
# مرحلة مستقلة: تصحيح أخطاء التعرف على الكلام (Speech Recognition Correction)
# تأتي بين النسخ الصوتي (Whisper) وبين مرحلة التقييم — تُصحِّح فقط الأخطاء
# التي يبدو بنسبة عالية أنها ناتجة عن خطأ آلي في التعرف على الصوت (وليست
# أخطاء إملائية/نحوية حقيقية من الطالب)، بالاستعانة بسياق موضوع النشاط.
# ═══════════════════════════════════════════════════════════════════════

# ملاحظة تصميم مهمة: هذا الـ Prompt لا يطلب من Gemini "إعادة كتابة" النص
# إطلاقاً — فقط يطلب منه قائمة تصحيحات (كلمة خطأ → كلمة صحيحة + درجة ثقة).
# النص النهائي يُبنى برمجياً بعدها (apply_word_corrections) عبر استبدال كل
# كلمة في مكانها بالضبط، فيستحيل بنيوياً أن يُضيف/يحذف/يُعيد ترتيب أي كلمة —
# بعكس الاعتماد على نص مُعاد صياغته بالكامل من النموذج.
_STT_CORRECTION_PROMPT_TEMPLATE = """أنت خبير في تصحيح أخطاء أنظمة التعرف الآلي على الكلام العربي (Speech-to-Text) فقط.
سيصلك نص ناتج عن تحويل كلام طالب عُماني في الصف السادس إلى نص كتابةً.

مهمتك الوحيدة: تحديد الكلمات التي يبدو بوضوح أنها أخطاء تعرّف آلي على الصوت
(كلمة سُمِعت خطأ وتحولت لكلمة أخرى قريبة صوتياً)، وليس تصحيح إملاء الطالب أو أسلوبه أو نحوه.

أمثلة على أخطاء التعرف الآلي على الكلام (وليست أخطاء الطالب):
جلسنا ← قلسنا، الأسماك ← الأسماء، المسبح ← المصبح، البذور ← الكثور،
الشاطئ ← الشاتي، رجعنا ← رقعنا، جدي ← قدي، سبحت ← صبحت

يجب عليك الالتزام الصارم بهذه القواعد:
- لا تقترح إعادة صياغة أي جملة، ولا تجعل النص أكثر فصاحة، ولا تُغيّر أسلوب الطالب.
- لا تقترح إضافة كلمات جديدة أو حذف كلمات موجودة أو تغيير ترتيبها — فقط استبدال كلمة خطأ بكلمة صحيحة في نفس موضعها.
- لا تُصحِّح الأخطاء النحوية الطبيعية للطالب، ولا الأخطاء الإملائية العادية
  (مثل: هاذا، مدرسه) — هذه ليست من مهمتك هنا إطلاقاً.
- لا تعتبر اختلاف التشكيل/التنوين/الإعراب/علامات الترقيم خطأً على الإطلاق.
- لا تصحّح كلمة لمجرد أنها غير مرتبطة بموضوع النشاط — كلمة صحيحة وواقعية حتى
  لو كانت خارج سياق الموضوع يجب أن تبقى كما هي (الطالب يتحدث بحرية).
- اقترح تصحيحاً فقط إذا توفّر معك دليل كافٍ من كل ما يلي معاً:
  (١) الكلمة الناتجة غير منطقية أو غريبة جداً في سياق الجملة،
  (٢) توجد كلمة بديلة قريبة صوتياً ومناسبة للسياق،
  (٣) البديل لا يُغيّر المعنى العام لكلام الطالب بشكل جوهري.
- إن لم تتوفر الأدلة الثلاثة معاً بثقة عالية، لا تقترح شيئاً لهذه الكلمة إطلاقاً.

سياق النشاط (استخدمه للمساعدة في الاستنتاج فقط، لا تكرره في الإجابة):
{context}

اقتراحات تشابه صوتي محسوبة آلياً بمقارنة الكلمات مع مفردات الموضوع (للاستئناس
فقط، تحقق أنت من صحتها بالسياق قبل استخدامها، فقد تكون بعضها غير صحيحة):
{hints}

النص الناتج من التعرف الآلي على الكلام:
\"\"\"{text}\"\"\"

أعد النتيجة بصيغة JSON فقط دون أي نص إضافي أو Markdown، وفق هذا الشكل بالضبط.
اجعل القائمة فارغة تماماً إن لم تجد أي تصحيح واثق منه بشدة:
{{"corrections": [{{"wrong": "الكلمة كما وردت حرفياً في النص أعلاه (بدون أي تغيير)", "correct": "الكلمة الصحيحة", "reason": "سبب مختصر", "confidence": 0.0}}]}}

قواعد تقدير الثقة (confidence، رقم بين 0 و1):
- 0.9 فأعلى: شبه مؤكد أنه خطأ تعرّف آلي (الكلمة غير منطقية إطلاقاً ويوجد بديل صوتي واضح ومناسب للسياق).
- 0.75 إلى 0.89: مرجَّح بقوة لكن ليس مؤكداً تماماً.
- أقل من 0.75: شك فقط — لا تُدرجه في القائمة أصلاً، لأن ما دون ذلك لن يُطبَّق على أي حال.
مهم جداً: قيمة "wrong" يجب أن تُطابق حرفياً كلمة موجودة فعلاً في النص أعلاه، وإلا فلن يُطبَّق تصحيحك مطلقاً.
"""


def correct_stt_errors(transcript: str, topic_hint: str = "") -> dict:
    """
    مرحلة "Speech Recognition Correction" المستقلة (Layers 3+4+5): تصحح فقط
    أخطاء ناتجة عن التعرف الآلي على الكلام (وليس أخطاء الطالب اللغوية
    الحقيقية)، بالاستعانة بسياق موضوع النشاط وتلميحات تشابه صوتي محسوبة
    آلياً (Layer 3)، ثم تحكيم Gemini (Layer 4) الذي يُعيد فقط قائمة تصحيحات
    مع درجة ثقة — لا نصاً معاد صياغته. يُطبَّق كل تصحيح برمجياً وبأمان
    (Layer 5) عبر استبدال كلمة بكلمة في مكانها فقط. تُعيد النص كما هو دون أي
    تعديل إن تعذّر الاتصال بـGemini أو لم تتوفر ثقة كافية بأي تصحيح.
    """
    fallback = {"correctedText": transcript, "corrections": []}
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not transcript or not transcript.strip():
        return fallback
    if not api_key:
        logger.warning("STT correction skipped: GEMINI_API_KEY not configured")
        return fallback

    clean_hint = re.sub(r"[\u064B-\u065F\u0670]", "", topic_hint) if topic_hint else ""
    context_parts = [f"عنوان النشاط: {topic_hint}"] if topic_hint else ["لا يوجد عنوان نشاط محدد."]
    vocab_words = _topic_vocab_list(topic_hint)
    for key, vocab in TOPIC_VOCAB.items():
        if key in clean_hint or clean_hint in key:
            context_parts.append(f"الكلمات المساعدة لهذا الموضوع: {vocab}")
            break
    context = "\n".join(context_parts)

    # Layer 3: تلميحات تشابه صوتي آلية (لا تُغيّر شيئاً بنفسها، فقط تُرفَق كسياق)
    hints = find_fuzzy_hints(transcript, vocab_words)
    hints_text = (
        "\n".join(f"- «{h['whisper_word']}» قد تكون سماعاً خاطئاً لـ «{h['candidate']}» "
                  f"(تشابه صوتي محسوب: {h['similarity']})" for h in hints)
        if hints else "لا توجد تلميحات تشابه صوتي آلية لهذا النص."
    )

    t0 = time.monotonic()
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-3.6-flash:generateContent?key={api_key}"
        )
        prompt = _STT_CORRECTION_PROMPT_TEMPLATE.format(context=context, hints=hints_text, text=transcript)
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0, "maxOutputTokens": 1024,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            parsed = json.loads(raw)

        proposed = parsed.get("corrections", []) or []
    except Exception as ex:
        # فشل الاتصال بـGemini لا يُسقط تقييم الطالب أبداً — نُكمل بالنص كما هو.
        logger.warning("STT correction: failed (%s: %s) — continuing with uncorrected transcript",
                        type(ex).__name__, ex)
        return fallback

    # Layer 5: تطبيق آمن (استبدال كلمة بكلمة فقط) + تحقق نهائي من سلامة النتيجة
    corrected_text, applied = apply_word_corrections(transcript, proposed)
    if applied and not validate_word_substitution(transcript, corrected_text):
        # لا يجب أن يحدث هذا أبداً بما أن apply_word_corrections تستبدل كلمة
        # بكلمة فقط، لكن نتحقق دفاعياً قبل الوثوق بالنتيجة على أي حال.
        logger.warning("STT correction: rejected — post-substitution validation failed unexpectedly")
        return fallback

    duration = time.monotonic() - t0
    if applied:
        logger.info("STT correction: success — %d correction(s) applied in %.2fs: %s",
                    len(applied), duration,
                    ", ".join(f"{c['wrong']}->{c['correct']}({c['confidence']})" for c in applied))
    else:
        logger.info("STT correction: skipped — no correction met the confidence threshold (%.2fs)", duration)

    return {"correctedText": corrected_text, "corrections": applied}


def evaluate_speaking(transcript: str, reference_text: Optional[str] = None, lesson_id: str = "") -> dict:
    """
    ملاحظة مهمة: يجب أن يكون `transcript` هنا دائماً هو الـcanonical transcript
    (أي بعد تصحيح أخطاء STT عبر correct_stt_errors، وليس النص الخام من
    Whisper مباشرة) — بهذا لا يُعاقَب الطالب أبداً على خطأ تعرّف آلي على
    الصوت، فقط على أخطائه اللغوية الحقيقية الموجودة فعلاً في كلامه.
    """
    if not transcript or len(transcript.strip()) < 5:
        empty = {
            "overall": 0, "word_count": 0, "transcript": transcript,
            "feedback": "لم يتم التعرف على الكلام. يرجى المحاولة مجدداً.",
        }
        if lesson_id == "opinion":
            empty.update({"opinion_clarity": 0, "reasons_score": 0, "phrases_score": 0, "coherence_score": 0, "conclusion_score": 0})
        elif lesson_id == "earth":
            empty.update({"understanding_score": 0, "goal_score": 0, "vocabulary_score": 0, "coherence_score": 0, "opinion_score": 0})
        else:
            empty.update({"pronunciation": 0, "sentence_structure": 0, "diacritics": 0, "grammar": 0})
        return empty

    if lesson_id == "opinion":
        return _evaluate_opinion_speaking(transcript)
    if lesson_id == "earth":
        return _evaluate_comprehension_speaking(transcript)

    words = transcript.split()
    word_count = len(words)

    pronunciation_score = _evaluate_pronunciation(transcript, reference_text)
    sentence_score      = _evaluate_sentence_structure(transcript, word_count)
    diacritics_score    = _evaluate_diacritics(transcript)
    grammar_score       = _evaluate_grammar(transcript)

    overall = round(
        (pronunciation_score * 0.35) +
        (sentence_score      * 0.25) +
        (diacritics_score    * 0.20) +
        (grammar_score       * 0.20)
    )

    return {
        "pronunciation": pronunciation_score,
        "sentence_structure": sentence_score,
        "diacritics": diacritics_score,
        "grammar": grammar_score,
        "overall": overall,
        "word_count": word_count,
        "transcript": transcript,
        "feedback": _generate_feedback(overall, pronunciation_score, sentence_score),
        "strengths": _speaking_strengths(pronunciation_score, sentence_score, diacritics_score, grammar_score, word_count),
        "suggestions": _speaking_suggestions(pronunciation_score, sentence_score, diacritics_score, grammar_score, word_count, transcript),
    }


def _speaking_strengths(pronunciation: int, sentence: int, diacritics: int, grammar: int, word_count: int) -> list:
    s = []
    if pronunciation >= 80: s.append("🗣️ نُطْقُكَ وَاضِحٌ وَمَفْهُومٌ تَمَامًا")
    if sentence >= 80:      s.append("📝 جُمَلُكَ مُرَتَّبَةٌ وَمُتَسَلْسِلَةٌ بِشَكْلٍ جَيِّدٍ")
    if diacritics >= 80:    s.append("🔤 اسْتَخْدَمْتَ التَّشْكِيلَ الصَّحِيحَ فِي مُعْظَمِ الْكَلِمَاتِ")
    if grammar >= 80:       s.append("✅ تَرْكِيبُكَ النَّحْوِيُّ سَلِيمٌ")
    if word_count >= 40:    s.append("💬 تَحَدَّثْتَ بِإِسْهَابٍ وَتَفْصِيلٍ جَيِّدٍ")
    if not s:
        s.append("👍 أَكْمَلْتَ النَّشَاطَ بِنَجَاحٍ — اسْتَمِرَّ فِي الْمُحَاوَلَةِ!")
    return s


def _speaking_suggestions(pronunciation: int, sentence: int, diacritics: int, grammar: int, word_count: int, transcript: str) -> list:
    tips = []
    if pronunciation < 80:
        tips.append("حَاوِلْ نُطْقَ الْكَلِمَاتِ الطَّوِيلَةِ بِبُطْءٍ أَكْبَرَ وَوُضُوحٍ")
    if sentence < 80:
        tips.append("اسْتَخْدِمْ أَدَوَاتِ رَبْطٍ مِثْلَ (ثُمَّ، بَعْدَ ذَلِكَ، لِذَلِكَ) لِتَحْسِينِ تَسَلْسُلِ جُمَلِكَ")
    if diacritics < 80:
        tips.append("انْتَبِهْ لِتَشْكِيلِ أَوَاخِرِ الْكَلِمَاتِ (الْحَرَكَاتِ) أَثْنَاءَ النُّطْقِ")
    if grammar < 80:
        tips.append("رَاجِعْ تَرْكِيبَ الْجُمْلَةِ وَتَأَكَّدْ مِنَ التَّطَابُقِ بَيْنَ الْفِعْلِ وَالْفَاعِلِ")
    if word_count < 20:
        tips.append("حَاوِلْ التَّحَدُّثَ لِفَتْرَةٍ أَطْوَلَ لِإِثْرَاءِ حَدِيثِكَ بِمَزِيدٍ مِنَ التَّفَاصِيلِ")
    if not tips:
        tips.append("أَدَاؤُكَ مُمْتَازٌ — اسْتَمِرَّ عَلَى هَذَا الْمُسْتَوَى!")
    return tips


# ═══════════════ تقييم مخصَّص لنشاط "التعبير عن الرأي" ═══════════════
# يركّز على: وضوح الرأي، وجود أسباب مقنعة، استخدام عبارات إبداء الرأي،
# ترابط الأفكار، ووجود خاتمة — وليس على عدد الكلمات فقط.

_OPINION_OPENERS = ["أعتقد", "برأيي", "في رأيي", "من وجهة نظري", "أرى أن", "أظن"]
_REASON_MARKERS  = ["لأن", "لأنّ", "بسبب", "وذلك لأن", "نظراً لـ", "نظراً ل"]
_CONNECTORS      = ["أولاً", "ثانياً", "ثالثاً", "بعد ذلك", "أيضاً", "بالإضافة إلى ذلك", "كذلك", "علاوة على ذلك", "من ناحية أخرى"]
_CONCLUDERS      = ["لذلك", "لهذا", "وأخيراً", "أخيراً", "في الختام", "وفي الختام", "وباختصار", "خلاصة القول", "إذن"]


def _evaluate_opinion_speaking(transcript: str) -> dict:
    words = transcript.split()
    word_count = len(words)
    last_third = transcript[int(len(transcript) * 0.6):]  # الجزء الأخير من الحديث، لفحص الخاتمة

    # ١) وضوح الرأي: وجود عبارة إبداء رأي صريحة + طول كافٍ للتعبير
    openers_found = [p for p in _OPINION_OPENERS if p in transcript]
    clarity_score = 40
    if openers_found: clarity_score += 40
    if word_count >= 15: clarity_score += 20
    clarity_score = min(100, clarity_score)

    # ٢) الأسباب: كل "لأن" أو ما شابهها تُحسب سبباً داعماً للرأي
    reasons_found = sum(transcript.count(m) for m in _REASON_MARKERS)
    if reasons_found == 0:   reasons_score = 30
    elif reasons_found == 1: reasons_score = 70
    else:                    reasons_score = 100

    # ٣) عبارات إبداء الرأي (أعتقد/في رأيي/لأن/لذلك...) — عدد العبارات المميزة المستخدمة
    phrase_pool = _OPINION_OPENERS + _REASON_MARKERS + _CONCLUDERS
    phrases_used = sorted(set(p for p in phrase_pool if p in transcript))
    phrases_score = min(100, 30 + len(phrases_used) * 20)

    # ٤) ترابط الأفكار: أدوات ربط/تسلسل + وجود أكثر من جملة (فواصل/نقاط)
    connectors_found = sum(1 for c in _CONNECTORS if c in transcript)
    coherence_score = 40 + min(40, connectors_found * 15)
    if "،" in transcript or "." in transcript:
        coherence_score += 20
    coherence_score = min(100, coherence_score)

    # ٥) الخاتمة: هل ظهرت عبارة ختامية في الجزء الأخير من الحديث؟
    concluders_found = [c for c in _CONCLUDERS if c in last_third]
    conclusion_score = 100 if concluders_found else (50 if any(c in transcript for c in _CONCLUDERS) else 20)

    overall = round(
        (clarity_score    * 0.25) +
        (reasons_score    * 0.30) +
        (phrases_score    * 0.15) +
        (coherence_score  * 0.15) +
        (conclusion_score * 0.15)
    )

    return {
        "opinion_clarity": clarity_score,
        "reasons_score": reasons_score,
        "reasons_count": reasons_found,
        "phrases_score": phrases_score,
        "phrases_used": phrases_used,
        "coherence_score": coherence_score,
        "conclusion_score": conclusion_score,
        "overall": overall,
        "word_count": word_count,
        "transcript": transcript,
        "feedback": _generate_opinion_feedback(overall, reasons_found, bool(openers_found), bool(concluders_found)),
        "strengths": _opinion_strengths(clarity_score, reasons_found, coherence_score, bool(concluders_found)),
        "suggestions": _opinion_suggestions(bool(openers_found), reasons_found, bool(concluders_found), coherence_score),
    }


def _opinion_strengths(clarity_score: int, reasons_found: int, coherence_score: int, has_conclusion: bool) -> list:
    s = []
    if clarity_score >= 80:   s.append("🗣️ عبّرت عن رأيك بوضوح منذ البداية")
    if reasons_found >= 2:    s.append("📌 دعمت رأيك بسببين أو أكثر — إقناعٌ جيدٌ")
    elif reasons_found == 1:  s.append("📌 دعمت رأيك بسبب واحد")
    if coherence_score >= 80: s.append("🔗 أفكارك مترابطة ومتسلسلة بشكل منطقي")
    if has_conclusion:        s.append("🏁 ختمت حديثك بخاتمة مناسبة")
    if not s:
        s.append("👍 أكملت النشاط بنجاح — استمر في المحاولة!")
    return s


def _opinion_suggestions(has_opener: bool, reasons_found: int, has_conclusion: bool, coherence_score: int) -> list:
    tips = []
    if not has_opener:
        tips.append("ابدأ حديثك بعبارة واضحة مثل «أعتقد أن...» أو «في رأيي...»")
    if reasons_found == 0:
        tips.append("أضِف سبباً واحداً على الأقل يدعم رأيك باستخدام «لأن...»")
    elif reasons_found == 1:
        tips.append("حاول إضافة سبب ثانٍ ليصبح رأيك أكثر إقناعاً")
    if coherence_score < 80:
        tips.append("استخدم أدوات ربط مثل (أولاً، بالإضافة إلى ذلك) لتنظيم أفكارك")
    if not has_conclusion:
        tips.append("اختم حديثك بجملة قصيرة تلخّص رأيك، مثل «لذلك أعتقد...»")
    if not tips:
        tips.append("أداؤك ممتاز — استمر على هذا المستوى!")
    return tips


def _generate_opinion_feedback(overall: int, reasons_found: int, has_opener: bool, has_conclusion: bool) -> str:
    if overall >= 85:
        return "ممتاز! عبّرت عن رأيك بوضوح ودعمته بأسباب مقنعة، وأنهيت حديثك بخاتمة مناسبة."
    tips = []
    if not has_opener:
        tips.append("ابدأ حديثك بعبارة واضحة مثل «أعتقد أن...» أو «في رأيي...»")
    if reasons_found == 0:
        tips.append("أضِف سبباً واحداً على الأقل يدعم رأيك باستخدام «لأن...»")
    elif reasons_found == 1:
        tips.append("حاول إضافة سبب ثانٍ ليصبح رأيك أكثر إقناعاً")
    if not has_conclusion:
        tips.append("اختم حديثك بجملة قصيرة تلخّص رأيك، مثل «لذلك أعتقد...»")
    if not tips:
        return "جيد جداً! رأيك واضح ومنظّم، استمر في التدريب لتطوير أسلوبك أكثر."
    return "جيد! " + " — ".join(tips)


def _evaluate_pronunciation(transcript: str, reference: Optional[str]) -> int:
    if not reference:
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', transcript))
        total_chars  = max(len(transcript.replace(" ", "")), 1)
        return min(100, int((arabic_chars / total_chars) * 100))
    ref_words   = set(reference.split())
    trans_words = set(transcript.split())
    if not ref_words:
        return 70
    overlap = len(ref_words & trans_words) / len(ref_words)
    return min(100, int(overlap * 100))


def _evaluate_sentence_structure(transcript: str, word_count: int) -> int:
    score = 50
    if word_count >= 20:   score += 20
    elif word_count >= 10: score += 10
    connectors = ['ثم','لأن','لذلك','أما','بينما','حيث','كما','أيضاً','و','لكن']
    found = sum(1 for c in connectors if c in transcript)
    score += min(20, found * 5)
    if '.' in transcript or '،' in transcript:
        score += 10
    return min(100, score)


def _evaluate_diacritics(transcript: str) -> int:
    total_chars = len(re.findall(r'[\u0600-\u06FF]', transcript))
    diacritics  = len(re.findall(r'[\u064B-\u065F]', transcript))
    if total_chars == 0:
        return 50
    return min(100, int((diacritics / total_chars) * 200))


def _evaluate_grammar(transcript: str) -> int:
    score = 60
    verb_patterns = ['يعمل','يذهب','يقول','يكتب','يقرأ','كان','أصبح']
    if any(v in transcript for v in verb_patterns):
        score += 15
    al_count = len(re.findall(r'\bال\w+', transcript))
    score += min(15, al_count * 3)
    common_errors = ['هاذا','هاذه','ذالك']
    score -= sum(1 for e in common_errors if e in transcript) * 5
    return max(0, min(100, score))


def _generate_feedback(overall: int, pronunciation: int, structure: int) -> str:
    if overall >= 85: return "ممتاز! أداؤك رائع في التحدث باللغة العربية."
    elif overall >= 70: return "جيد جداً! يمكنك تحسين النطق أكثر بالتدريب المستمر."
    elif overall >= 55: return "جيد! ركّز على بناء الجمل الكاملة وإضافة أدوات الربط."
    else: return "استمر في التدريب! حاول التحدث بجمل أطول وأكثر وضوحاً."


# ═══════════════ تقييم مخصَّص لنشاط "قراءة منشور توعوي" (فهم واستيعاب) ═══════════════
# يركّز على: فهم الفكرة، توضيح الهدف، مفردات الموضوع، ترابط الأفكار، ورأي/اقتراح مناسب.

_EARTH_TOPIC_WORDS = ["ساعة الأرض", "البيئة", "المحافظة", "الطاقة", "الكهرباء", "ترشيد",
                      "المشاركة", "المجتمع", "كوكب الأرض", "المستقبل", "التلوث", "الوعي",
                      "أضواء", "إطفاء", "انطفاء", "استهلاك"]
_GOAL_MARKERS = ["الهدف", "من أجل", "لكي", "حتى", "بهدف", "تهدف", "الغرض"]
_OPINION_SUGGESTION_MARKERS = ["أعتقد", "أرى", "أقترح", "يجب", "من المهم", "ينبغي",
                               "لذلك", "أنصح", "من رأيي", "في رأيي"]


def _evaluate_comprehension_speaking(transcript: str) -> dict:
    words = transcript.split()
    word_count = len(words)

    # ١) فهم الفكرة الرئيسة: وجود كلمات الموضوع الأساسية
    topic_hits = sum(1 for w in _EARTH_TOPIC_WORDS if w in transcript)
    understanding_score = min(100, 30 + topic_hits * 18)

    # ٢) توضيح الهدف من المنشور
    has_goal_marker = any(m in transcript for m in _GOAL_MARKERS)
    goal_score = 85 if (has_goal_marker and topic_hits >= 1) else (55 if topic_hits >= 1 else 25)

    # ٣) مفردات مرتبطة بالموضوع (تنوّع الكلمات المستخدمة من قاموس الموضوع)
    vocabulary_score = min(100, 20 + topic_hits * 15)

    # ٤) ترابط الأفكار وتسلسلها
    connectors_found = sum(1 for c in _CONNECTORS if c in transcript)
    coherence_score = 40 + min(40, connectors_found * 15)
    if "،" in transcript or "." in transcript:
        coherence_score += 20
    coherence_score = min(100, coherence_score)

    # ٥) رأي أو اقتراح مناسب في نهاية الحديث
    has_opinion = any(m in transcript for m in _OPINION_SUGGESTION_MARKERS)
    opinion_score = 90 if has_opinion else 30

    overall = round(
        (understanding_score * 0.30) +
        (goal_score          * 0.20) +
        (vocabulary_score    * 0.20) +
        (coherence_score     * 0.15) +
        (opinion_score       * 0.15)
    )

    return {
        "understanding_score": understanding_score,
        "goal_score": goal_score,
        "vocabulary_score": vocabulary_score,
        "coherence_score": coherence_score,
        "opinion_score": opinion_score,
        "overall": overall,
        "word_count": word_count,
        "transcript": transcript,
        "feedback": _generate_comprehension_feedback(overall, topic_hits, has_goal_marker, has_opinion),
        "strengths": _comprehension_strengths(understanding_score, goal_score, coherence_score, has_opinion),
        "suggestions": _comprehension_suggestions(topic_hits, has_goal_marker, has_opinion, coherence_score),
    }


def _comprehension_strengths(understanding_score: int, goal_score: int, coherence_score: int, has_opinion: bool) -> list:
    s = []
    if understanding_score >= 80: s.append("🧠 فهمت فكرة المنشور الرئيسة بوضوح")
    if goal_score >= 80:          s.append("🎯 وضّحت الهدف من المنشور بدقة")
    if coherence_score >= 80:     s.append("🔗 أفكارك مترابطة ومتسلسلة بشكل منطقي")
    if has_opinion:               s.append("🌱 قدّمت رأياً أو اقتراحاً مناسباً")
    if not s:
        s.append("👍 أكملت النشاط بنجاح — استمر في المحاولة!")
    return s


def _comprehension_suggestions(topic_hits: int, has_goal: bool, has_opinion: bool, coherence_score: int) -> list:
    tips = []
    if topic_hits == 0:
        tips.append("استخدم كلمات من المنشور نفسه (مثل: ساعة الأرض، البيئة، الطاقة) لتُظهر فهمك للفكرة")
    if not has_goal:
        tips.append("وضّح الهدف من المنشور، مثلاً: «الهدف من هذا المنشور هو...»")
    if coherence_score < 80:
        tips.append("استخدم أدوات ربط لتنظيم أفكارك بشكل أوضح")
    if not has_opinion:
        tips.append("اختم حديثك برأيك أو اقتراحك، مثل: «أعتقد أن...» أو «أقترح أن...»")
    if not tips:
        tips.append("أداؤك ممتاز — استمر على هذا المستوى!")
    return tips


def _generate_comprehension_feedback(overall: int, topic_hits: int, has_goal: bool, has_opinion: bool) -> str:
    if overall >= 85:
        return "ممتاز! فهمت فكرة المنشور ووضّحت هدفه، واستخدمت مفردات مناسبة، وختمت برأي واضح."
    tips = []
    if topic_hits == 0:
        tips.append("استخدم كلمات من المنشور نفسه (مثل: ساعة الأرض، البيئة، الطاقة) لتُظهر فهمك للفكرة")
    if not has_goal:
        tips.append("وضّح الهدف من المنشور، مثلاً: «الهدف من هذا المنشور هو...»")
    if not has_opinion:
        tips.append("اختم حديثك برأيك أو اقتراحك، مثل: «أعتقد أن...» أو «أقترح أن...»")
    if not tips:
        return "جيد جداً! استمر في تنظيم أفكارك بهذا الشكل الواضح."
    return "جيد! " + " — ".join(tips)
