"""
طبقات مساعدة لتحسين دقة التعرف الآلي على الكلام العربي (Speech-to-Text)
واستخدامها بشكل آمن ومحافظ، دون المخاطرة بتغيير كلام الطالب الفعلي.

هذه الوحدة توفر:
  • Layer 2 — Arabic normalization: تطبيع آمن للمقارنة فقط (لا يُطبَّق على
    النص المعروض/المُقيَّم أبداً، فقط يُستخدم داخلياً للمطابقة).
  • Layer 3 — Fuzzy / phonetic similarity: اقتراح كلمات مرشَّحة للتصحيح بناءً
    على تشابه صوتي مع مفردات موضوع النشاط، دون استبدال تلقائي أبداً — تُستخدم
    فقط كـ"تلميحات" تُرفَق مع طلب Gemini (Layer 4) ليقيّمها بالسياق الكامل.
  • Layer 5 — Confidence / safety validation: تطبيق التصحيحات المقترَحة على
    النص الأصلي بأمان (استبدال كلمة بكلمة فقط، بدون حذف/إضافة/تبديل ترتيب)،
    مع حماية إضافية (تشابه حرفي أدنى + عتبة ثقة) قبل قبول أي تصحيح.

القاعدة الذهبية في كل هذه الطبقات: "تصحيح خاطئ أسوأ من ترك خطأ محتمل" —
فعند أي شك، لا يحدث أي تغيير.
"""
import re
import logging
from difflib import SequenceMatcher

import pyarabic.araby as araby

logger = logging.getLogger("sawti.stt_correction")

_PUNCT = ".,،؟!؛:«»\"'\u200f\u200e"
_TASHKEEL_RE = re.compile(r"[\u064B-\u065F\u0670]")


# ═══════════════════════════ Layer 2: Arabic normalization ═══════════════════════════
# تطبيع "للمقارنة فقط" — لا يُستخدم أبداً لتعديل النص المعروض أو المُقيَّم،
# فقط لتحديد ما إذا كانت كلمتان تُعتبران "نفس الكلمة تقريباً" عند المقارنة.

def normalize_for_compare(word: str) -> str:
    if not word:
        return ""
    w = word.strip(_PUNCT)
    w = araby.strip_tashkeel(w)
    w = araby.strip_tatweel(w)
    w = araby.normalize_ligature(w)   # لام-ألف المركّبة → لام + ألف
    w = araby.normalize_alef(w)       # أ / إ / آ / ٱ → ا (للمقارنة فقط)
    w = w.replace("ى", "ي").replace("ة", "ه")  # تقريب ألف مقصورة/تاء مربوطة (مقارنة فقط)
    return w


# مجموعات حروف مُتقارِبة صوتياً في اللهجات العربية (وخصوصاً الخليجية/العُمانية)
# تُستخدم فقط لحساب "مفتاح صوتي تقريبي" يساعد على رصد التباس محتمل، وليس
# للتصحيح المباشر.
_PHONETIC_GROUPS = ["جق", "سص", "تط", "ذز", "حه", "ضظ", "كق"]
_PHONETIC_MAP = {ch: grp[0] for grp in _PHONETIC_GROUPS for ch in grp}


def phonetic_key(word: str) -> str:
    normalized = normalize_for_compare(word)
    return "".join(_PHONETIC_MAP.get(ch, ch) for ch in normalized)


def char_similarity(a: str, b: str) -> float:
    """تشابه حرفي (0-1) بين كلمتين بعد التطبيع الصوتي — يُستخدم كحارس أمان
    لرفض أي استبدال بين كلمتين مختلفتين تماماً حتى لو اقترحه Gemini خطأً."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, phonetic_key(a), phonetic_key(b)).ratio()


# ═══════════════════════════ Layer 3: Fuzzy / phonetic hints ═══════════════════════════
# لا تستبدل أي كلمة تلقائياً هنا — فقط تُنتج قائمة "اشتباه" تُرفَق كسياق إضافي
# لِـ Gemini (Layer 4) ليقرر بنفسه مستعيناً بالسياق الكامل للجملة.

_STOPWORDS = {
    "في", "من", "إلى", "على", "عن", "مع", "بين", "عند", "قبل", "بعد", "حتى",
    "و", "أو", "لكن", "ثم", "هذا", "هذه", "ذلك", "تلك", "التي", "الذي",
    "كان", "كانت", "كانوا", "قد", "لقد", "وقد", "فقد", "لا", "لم", "لن",
    "أن", "إن", "كل", "بعض", "غير", "أيضا", "أيضاً", "جدا", "جداً",
}

_ARABIC_WORD_RE = re.compile(r"[\u0621-\u064A]+")


def find_fuzzy_hints(transcript: str, vocab_words: list[str], threshold: float = 0.80,
                      max_hints: int = 5, min_word_len: int = 3) -> list[dict]:
    """
    يقارن كل كلمة (غير شائعة) في النص بمفردات موضوع النشاط صوتياً، ويُعيد
    أفضل تلميح لكل كلمة مشبوهة إن تجاوز التشابه العتبة المحدَّدة. لا يُغيّر
    أي شيء في النص — فقط يُرجع قائمة اقتراحات للاستئناس بها لاحقاً.
    """
    if not vocab_words:
        return []
    hints: list[dict] = []
    seen: set[str] = set()
    for tok in _ARABIC_WORD_RE.findall(transcript):
        tok_norm = normalize_for_compare(tok)
        if len(tok_norm) < min_word_len or tok_norm in seen or tok in _STOPWORDS:
            continue
        seen.add(tok_norm)
        # إن كانت الكلمة مطابقة أصلاً لكلمة من مفردات الموضوع، فلا داعي لأي اقتراح
        if any(tok_norm == normalize_for_compare(v) for v in vocab_words):
            continue
        best = None
        tok_key = phonetic_key(tok)
        for cand in vocab_words:
            score = SequenceMatcher(None, tok_key, phonetic_key(cand)).ratio()
            if score >= threshold and (best is None or score > best[1]):
                best = (cand, score)
        if best:
            hints.append({"whisper_word": tok, "candidate": best[0], "similarity": round(best[1], 2)})
        if len(hints) >= max_hints:
            break
    return hints


# ═══════════════════════════ Layer 5: Safe application + validation ═══════════════════════════

def apply_word_corrections(transcript: str, corrections: list[dict], min_confidence: float = 0.75,
                            min_similarity: float = 0.35) -> tuple[str, list[dict]]:
    """
    يطبّق تصحيحات (wrong→correct) على النص الأصلي بأمان تام:
      • استبدال كلمة بكلمة واحدة فقط في مكانها (نفس الموضع، بلا حذف/إضافة/إعادة ترتيب).
      • يرفض أي تصحيح إن لم تكن الكلمة "الخطأ" موجودة حرفياً في النص أصلاً
        (لتفادي أن يخترع Gemini كلمة لم ترد في النص).
      • يرفض أي تصحيح تحت عتبة الثقة، أو إن كان الاستبدال بين كلمتين مختلفتين
        تماماً (حماية ضد استبدالات غريبة حتى لو وردت بثقة عالية مزعومة).
    يُعيد (النص بعد التصحيح، قائمة التصحيحات المُطبَّقة فعلياً فقط).
    """
    tokens = transcript.split()
    applied: list[dict] = []

    for corr in corrections or []:
        wrong = (corr.get("wrong") or corr.get("original") or "").strip()
        correct = (corr.get("correct") or corr.get("corrected") or "").strip()
        try:
            confidence = float(corr.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        reason = corr.get("reason", "Speech Recognition Error")

        if not wrong or not correct or wrong == correct:
            continue
        if confidence < min_confidence:
            logger.info("Correction skipped (low confidence %.2f): %s -> %s", confidence, wrong, correct)
            continue
        if char_similarity(wrong, correct) < min_similarity:
            logger.info("Correction rejected (too dissimilar): %s -> %s", wrong, correct)
            continue

        wrong_norm = normalize_for_compare(wrong)
        matched_index = None
        for i, tok in enumerate(tokens):
            if normalize_for_compare(tok) == wrong_norm:
                matched_index = i
                break
        if matched_index is None:
            logger.info("Correction skipped (word not found verbatim in transcript): %s", wrong)
            continue

        tok = tokens[matched_index]
        tok_clean = tok.strip(_PUNCT)
        prefix = tok[:len(tok) - len(tok.lstrip(_PUNCT))] if tok != tok.lstrip(_PUNCT) else ""
        suffix = tok[len(tok_clean) + len(prefix):] if len(tok_clean) + len(prefix) <= len(tok) else ""
        tokens[matched_index] = f"{prefix}{correct}{suffix}"
        applied.append({"wrong": wrong, "correct": correct, "reason": reason, "confidence": round(confidence, 2)})

    corrected_text = " ".join(tokens)
    return corrected_text, applied


def validate_word_substitution(original: str, corrected: str) -> bool:
    """
    تأكيد إضافي (Layer 5 safety net) بعد التطبيق: يضمن أن النص المُصحَّح لم
    يفقد أو يكتسب أي كلمات، وأن الترتيب لم يتغيّر — أي أن الفرق الوحيد الممكن
    هو استبدال كلمات في أماكنها بالضبط.
    """
    orig_words = original.split()
    new_words = corrected.split()
    if len(orig_words) != len(new_words):
        return False
    sm = SequenceMatcher(None, orig_words, new_words)
    return all(tag in ("equal", "replace") for tag, *_ in sm.get_opcodes())


def validate_diacritization(plain: str, diacritized: str) -> bool:
    """
    يتحقق أن نص التشكيل لم يُغيّر أي كلمة أو يحذفها أو يضيف كلمات جديدة —
    فقط أضاف علامات التشكيل. يقارن الكلمات بعد إزالة التشكيل من كليهما.
    """
    if not diacritized or not diacritized.strip():
        return False
    orig_words = plain.split()
    new_words_raw = diacritized.split()
    if len(orig_words) != len(new_words_raw):
        return False
    for ow, nw in zip(orig_words, new_words_raw):
        ow_clean = _TASHKEEL_RE.sub("", ow).strip(_PUNCT)
        nw_clean = _TASHKEEL_RE.sub("", nw).strip(_PUNCT)
        if normalize_for_compare(ow_clean) != normalize_for_compare(nw_clean):
            return False
    return True
