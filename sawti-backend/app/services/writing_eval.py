import re

# قاموس الأخطاء الإملائية الشائعة
SPELLING_ERRORS = {
    # همزة الوصل والقطع
    "إنتهى": "انتهى",
    "إستقبل": "استقبل",
    "إستخدم": "استخدم",
    "إنتظر": "انتظر",
    "إستمر": "استمر",
    "إنطلق": "انطلق",
    # التاء المربوطة والمفتوحة
    "مدرست": "مدرسة",
    "طالبت": "طالبة",
    "كتابت": "كتابة",
    # الألف المقصورة والممدودة
    "عال": "عالٍ",
    "مستوا": "مستوى",
    "مبنا": "مبنى",
    # الهمزة المتوسطة
    "يسال": "يسأل",
    "يقرا": "يقرأ",
    "يبدا": "يبدأ",
    # أخطاء شائعة أخرى
    "الكن": "لكن",
    "هاذا": "هذا",
    "هاذه": "هذه",
    "ذالك": "ذلك",
    "االن": "الآن",
    "دائما": "دائماً",
    "ايضا": "أيضاً",
    "اكثر": "أكثر",
    "اقل": "أقل",
    "اول": "أول",
    "احيانا": "أحياناً",
    "فقط": "فقط",
    "ابدا": "أبداً",
    "اخيرا": "أخيراً",
    "كثيرا": "كثيراً",
    "جدا": "جداً",
    "قليلا": "قليلاً",
    "معا": "معاً",
    "سويا": "سوياً",
    "ممتازا": "ممتازاً",
}

# أدوات الربط العربية
CONNECTORS = [
    'و', 'ثم', 'أو', 'لكن', 'ألن', 'لذلك', 'إذن', 'حيث',
    'بينما', 'كما', 'أيضاً', 'أما', 'مع ذلك', 'بالإضافة',
    'من ناحية', 'في حين', 'رغم', 'على الرغم', 'بعد أن', 'قبل أن',
]


def evaluate_writing(text: str, min_words: int = 20) -> dict:
    """
    تقييم الكتابة العربية على محوَرين:
    1. الإملاء الصحيح
    2. تركيب الجمل والكلمات
    """
    if not text or len(text.strip()) < 10:
        return {
            "spelling_score": 0,
            "structure_score": 0,
            "overall_score": 0,
            "errors": [],
            "feedback": "النص قصير جداً. يرجى الكتابة أكثر.",
        }

    words = text.split()
    word_count = len(words)

    spelling_result = _check_spelling(text, words)
    structure_result = _check_structure(text, words, word_count, min_words)

    overall = round(
        (spelling_result["score"] * 0.5) +
        (structure_result["score"] * 0.5)
    )

    return {
        "spelling_score": spelling_result["score"],
        "structure_score": structure_result["score"],
        "overall_score": overall,
        "word_count": word_count,
        "spelling_errors": spelling_result["errors"],
        "spelling_corrections": spelling_result["corrections"],
        "connectors_found": structure_result["connectors"],
        "sentences_count": structure_result["sentences"],
        "strengths": _get_strengths(spelling_result, structure_result),
        "improvements": _get_improvements(spelling_result, structure_result, word_count, min_words),
        "feedback": _generate_writing_feedback(overall),
    }


def _check_spelling(text: str, words: list) -> dict:
    errors = []
    corrections = []

    for word in words:
        clean_word = re.sub(r'[\u064B-\u065F\u060C\u061B\u061F.,!?]', '', word)
        if clean_word in SPELLING_ERRORS:
            errors.append(clean_word)
            corrections.append({
                "wrong": clean_word,
                "correct": SPELLING_ERRORS[clean_word],
            })

    total_words = max(len(words), 1)
    error_rate = len(errors) / total_words
    score = max(0, int((1 - error_rate * 3) * 100))

    return {
        "score": min(100, score),
        "errors": errors,
        "corrections": corrections,
        "error_count": len(errors),
    }


def _check_structure(text: str, words: list, word_count: int, min_words: int) -> dict:
    score = 40

    if word_count >= min_words * 2:
        score += 25
    elif word_count >= min_words:
        score += 15
    elif word_count >= min_words // 2:
        score += 5

    found_connectors = [c for c in CONNECTORS if c in text]
    connector_bonus = min(20, len(found_connectors) * 5)
    score += connector_bonus

    punctuation_count = len(re.findall(r'[.،؟!]', text))
    if punctuation_count >= 3:
        score += 10
    elif punctuation_count >= 1:
        score += 5

    sentences = max(1, len(re.split(r'[.!؟]', text)))
    if sentences >= 3:
        score += 5

    return {
        "score": min(100, score),
        "connectors": found_connectors,
        "sentences": sentences,
        "punctuation_count": punctuation_count,
    }


def _get_strengths(spelling: dict, structure: dict) -> list:
    strengths = []
    if spelling["score"] >= 80:
        strengths.append("إملاء ممتاز مع أخطاء قليلة")
    if len(structure["connectors"]) >= 3:
        strengths.append("استخدام جيد لأدوات الربط")
    if structure["sentences"] >= 4:
        strengths.append("تنوع في بناء الجمل")
    if structure["punctuation_count"] >= 3:
        strengths.append("استخدام صحيح لعلامات الترقيم")
    return strengths if strengths else ["استمر في الكتابة والتدريب!"]


def _get_improvements(spelling: dict, structure: dict, word_count: int, min_words: int) -> list:
    improvements = []
    if spelling["error_count"] > 0:
        improvements.append(f"صحّح {spelling['error_count']} خطأ إملائي")
    if len(structure["connectors"]) < 2:
        improvements.append("أضف أدوات ربط مثل (لأن، لذلك، بينما)")
    if word_count < min_words:
        improvements.append(f"أضف {min_words - word_count} كلمة على الأقل")
    if structure["punctuation_count"] < 2:
        improvements.append("استخدم علامات الترقيم (. ، ؟)")
    return improvements


def _generate_writing_feedback(overall: int) -> str:
    if overall >= 85:
        return "ممتاز! كتابتك واضحة وصحيحة إملائياً."
    elif overall >= 70:
        return "جيد جداً! انتبه لبعض الأخطاء الإملائية البسيطة."
    elif overall >= 55:
        return "جيد! ركّز على الإملاء الصحيح وأدوات الربط."
    else:
        return "استمر في التدريب! راجع قواعد الإملاء وحاول الكتابة بجمل أطول."
