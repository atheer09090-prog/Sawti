"""
التدقيق الإملائي والنحوي المتقدم — نظام هجين بطبقتين:

الطبقة 1 (فورية، محلية، بدون API): PyArabic لتطبيع الحروف
   + قاموس موسّع لأخطاء الهمزات والتاء المربوطة والألف المقصورة الشائعة.
الطبقة 2 (اختيارية عبر Gemini): تُستدعى فقط للتحقق العميق (نحو/سياق)
   ولا تُستدعى إذا كانت الطبقة الأولى كافية أو كان النص قصيراً جداً.

كل خطأ يُعاد مع (start, end) موقع الحرف في النص الأصلي لإبرازه في الواجهة.
"""
import os
import re
import json
import urllib.request

try:
    import pyarabic.araby as araby
    _HAS_PYARABIC = True
except ImportError:
    _HAS_PYARABIC = False


# ============ الطبقة 1: قاموس موسّع + قواعد الهمزة ============

# أخطاء همزة القطع/الوصل الشائعة (الأفعال والأسماء التي تبدأ بها)
HAMZA_ERRORS: dict[str, str] = {
    "اكتب": "أكتب", "اكل": "أكل", "اذهب": "أذهب", "اقرا": "أقرأ",
    "ارى": "أرى", "اريد": "أريد", "احب": "أحب", "احضر": "أحضر",
    "اسكن": "أسكن", "اسكنت": "أسكنت", "اسكنا": "أسكنا",
    "اعيش": "أعيش", "اعيشت": "أعيشت", "اخذ": "أخذ", "امل": "أمل",
    "ابدا": "أبدأ" if False else "أبدأ",  # يُترك بدون تكرار الالتباس مع "أبداً" الظرف
    "اسال": "أسأل", "اجب": "أجب", "اعمل": "أعمل", "افهم": "أفهم",
    "استخدم": "استخدم",  # صحيحة أصلاً (وصل) — تُبقى للتوثيق فقط
    "إستخدم": "استخدم", "إستقبل": "استقبل", "إنتهى": "انتهى",
    "إنتظر": "انتظر", "إستمر": "استمر", "إنطلق": "انطلق",
    "إجتمع": "اجتمع", "إحتاج": "احتاج", "إستمتع": "استمتع",
    "إشترك": "اشترك", "إعتقد": "اعتقد", "إستطاع": "استطاع",
    "إنتقل": "انتقل", "إتصل": "اتصل", "إستفاد": "استفاد",
}

# التاء المربوطة/المفتوحة والهاء
TA_HA_ERRORS: dict[str, str] = {
    "مدرست": "مدرسة", "طالبت": "طالبة", "كتابت": "كتابة",
    "غرفت": "غرفة", "حديقت": "حديقة", "رحلت": "رحلة",
    "معلمه": "معلمة", "طالبه": "طالبة", "مدرسه": "مدرسة",
}

# الألف المقصورة/الممدودة والياء
ALEF_YA_ERRORS: dict[str, str] = {
    "مستوا": "مستوى", "مبنا": "مبنى", "معنا": "معنى",  # ملاحظة: "معنا" الضمير مستثنى بالسياق
    "يسال": "يسأل", "يقرا": "يقرأ", "يبدا": "يبدأ", "يرا": "يرى",
    "علا": "على", "الا": "إلى",  # فقط عند استخدامها كحرف جر
}

# أخطاء شائعة عامة
COMMON_ERRORS: dict[str, str] = {
    "الكن": "لكن", "هاذا": "هذا", "هاذه": "هذه", "ذالك": "ذلك",
    "االن": "الآن", "ايضا": "أيضاً", "اكثر": "أكثر", "اقل": "أقل",
    "اول": "أول", "احيانا": "أحياناً", "ابدا": "أبداً",
    "اخيرا": "أخيراً", "كثيرا": "كثيراً", "جدا": "جداً",
    "قليلا": "قليلاً", "معا": "معاً", "سويا": "سوياً",
    "راءعة": "رائعة", "راءع": "رائع", "راءعت": "رائعة",
    "شاء الله": "شاء الله", "انشاء": "إنشاء",
    "هاؤلاء": "هؤلاء", "هؤلاء": "هؤلاء",
}

ALL_DICTS = [
    (HAMZA_ERRORS, "خطأ في همزة القطع/الوصل"),
    (TA_HA_ERRORS, "خطأ في التاء المربوطة/المفتوحة"),
    (ALEF_YA_ERRORS, "خطأ في الألف المقصورة/الياء"),
    (COMMON_ERRORS, "خطأ إملائي شائع"),
]

_TOKEN_RE = re.compile(r"[\w\u0621-\u064A]+", re.UNICODE)


def _normalize_for_lookup(word: str) -> str:
    """تطبيع الكلمة للمقارنة مع القاموس (بدون تشكيل)."""
    if _HAS_PYARABIC:
        return araby.strip_tashkeel(word)
    return re.sub(r"[\u064B-\u065F]", "", word)


def check_spelling_layer1(text: str) -> list[dict]:
    """
    يفحص كل كلمة في النص مقابل القواميس، ويعيد الأخطاء مع موقعها
    الدقيق (start, end) في النص الأصلي لإبرازها في الواجهة.
    """
    errors: list[dict] = []
    for m in _TOKEN_RE.finditer(text):
        raw_word = m.group(0)
        clean = _normalize_for_lookup(raw_word)

        # إن كانت الكلمة معرّفة بـ"ال"، جرّب أيضاً بحثها بدون "ال"
        has_al_prefix = clean.startswith("ال") and len(clean) > 3
        clean_without_al = clean[2:] if has_al_prefix else None

        for dictionary, explanation in ALL_DICTS:
            match_key = None
            if clean in dictionary and dictionary[clean] != clean:
                match_key = clean
                prefix = ""
            elif clean_without_al and clean_without_al in dictionary and dictionary[clean_without_al] != clean_without_al:
                match_key = clean_without_al
                prefix = "ال"

            if match_key is not None:
                errors.append({
                    "wrong": raw_word,
                    "correct": prefix + dictionary[match_key],
                    "explanation": explanation,
                    "start": m.start(),
                    "end": m.end(),
                    "source": "dictionary",
                })
                break
    return errors


# ============ الطبقة 2: Gemini (فحص نحوي/سياقي عميق) ============

_GEMINI_PROMPT = """أنت مدقق لغوي عربي متخصص. افحص النص التالي واكتشف الأخطاء الإملائية والنحوية فقط
(أخطاء الهمزات، التاء المربوطة/المفتوحة، الألف المقصورة/الممدودة، أخطاء المطابقة النحوية،
الأخطاء الإملائية الشائعة). لا تصحح الأسلوب أو تقترح كلمات مرادفة.

أعد النتيجة بصيغة JSON فقط، بدون أي نص إضافي، وفق هذا الشكل بالضبط:
{"errors": [{"wrong": "الكلمة الخاطئة كما وردت حرفياً في النص", "correct": "التصحيح", "explanation": "شرح موجز بالعربية"}]}

إذا لم تجد أي أخطاء، أعد: {"errors": []}

النص:
""" 


def check_spelling_layer2_gemini(text: str, known_wrong_words: set[str]) -> list[dict]:
    """
    يستدعي Gemini API فقط لاكتشاف أخطاء نحوية/إملائية أعمق لم تكتشفها
    الطبقة الأولى. يُستبعد استدعاؤه إن لم يوجد مفتاح API.
    """
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key or not text.strip():
        return []
    try:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": _GEMINI_PROMPT + text}]}],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 1024},
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
            results = []
            for e in parsed.get("errors", []):
                wrong = e.get("wrong", "")
                if not wrong or wrong in known_wrong_words:
                    continue  # تجنّب التكرار مع الطبقة الأولى
                idx = text.find(wrong)
                if idx == -1:
                    continue
                results.append({
                    "wrong": wrong,
                    "correct": e.get("correct", wrong),
                    "explanation": e.get("explanation", "خطأ نحوي/إملائي"),
                    "start": idx,
                    "end": idx + len(wrong),
                    "source": "ai",
                })
            return results
    except Exception:
        return []  # فشل صامت — لا نوقف الطلب بسبب Gemini


# ============ الدالة الرئيسية ============

def check_spelling(text: str, use_ai: bool = True) -> dict:
    """
    نقطة الدخول الموحّدة: تُشغّل الطبقة الأولى دائماً، ثم تُضيف نتائج
    الطبقة الثانية (Gemini) إن طُلب ذلك (use_ai=True) ولم تُغطِّ
    الطبقة الأولى نصاً طويلاً بما يكفي أصلاً.
    """
    if not text or not text.strip():
        return {"errors": [], "error_count": 0, "score": 100}

    layer1_errors = check_spelling_layer1(text)
    known_wrong = {e["wrong"] for e in layer1_errors}

    layer2_errors = []
    if use_ai:
        layer2_errors = check_spelling_layer2_gemini(text, known_wrong)

    all_errors = sorted(layer1_errors + layer2_errors, key=lambda e: e["start"])
    word_count = max(len(text.split()), 1)
    error_rate = len(all_errors) / word_count
    score = max(0, min(100, int((1 - error_rate * 3) * 100)))

    return {
        "errors": all_errors,
        "error_count": len(all_errors),
        "score": score,
    }
