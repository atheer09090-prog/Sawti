import os
import re
import tempfile
from typing import Optional
from groq import Groq

# كلمات عامة شائعة تساعد Whisper على التعرف الصحيح (تُستخدم دائماً كأساس)
BASE_ARABIC_PROMPT = (
    "هذا تسجيل صوتي لطالب عُماني في الصف السادس يتحدث باللغة العربية الفصحى بصوت طفل، "
    "وبلهجة خليجية يُنطق فيها حرف الجيم أحياناً بصوت قريب من القاف (كما في كلمة الجو والجزر). "
    "ذهبنا، قمنا، رأينا، شاهدنا، جميلة، رائعة، ممتعة، كثيراً، أيضاً، لقد، وقد، فقد، "
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
                prompt = f"{prompt} كلمات متوقعة في هذا الموضوع: {vocab}."
                break
    return prompt


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


def _fix_phonetic_confusions(text: str) -> str:
    def repl(m: "re.Match[str]") -> str:
        word = m.group(0)
        clean = _TASHKEEL_RE.sub("", word)
        if clean in PHONETIC_CONFUSIONS:
            return PHONETIC_CONFUSIONS[clean]
        # حاول إزالة حرف عطف/جر ملتصق بالكلمة (مثل: والجزر، بالجزر) ثم أعِد مطابقتها
        if len(clean) > 2 and clean[0] in _PREFIX_LETTERS:
            rest = clean[1:]
            if rest in PHONETIC_CONFUSIONS:
                return clean[0] + PHONETIC_CONFUSIONS[rest]
        return word
    return re.sub(r"[\w\u0621-\u064A\u064B-\u065F\u0670]+", repl, text)


def transcribe_arabic_audio(audio_bytes: bytes, audio_format: str = "wav", topic_hint: str = "") -> str:
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

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
        return _fix_phonetic_confusions(
            transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
        )
    finally:
        os.unlink(tmp_path)


def evaluate_speaking(transcript: str, reference_text: Optional[str] = None, lesson_id: str = "") -> dict:
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
    }


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
    }


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
    }


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
