import re

# قاموس الأخطاء الإملائية الشائعة
SPELLING_ERRORS = {
    # همزة الوصل والقطع
    "إنتهى": "انتهى", "إستقبل": "استقبل", "إستخدم": "استخدم",
    "إنتظر": "انتظر", "إستمر": "استمر", "إنطلق": "انطلق",
    "اسكن": "أسكن", "اسكنت": "أسكنت", "اسكنا": "أسكنا",
    "اعيش": "أعيش", "اعيشت": "أعيشت",
    "اذهب": "أذهب", "اكل": "أكل", "اكتب": "أكتب",
    "ارى": "أرى", "اريد": "أريد", "احب": "أحب",
    # التاء المربوطة والمفتوحة
    "مدرست": "مدرسة", "طالبت": "طالبة", "كتابت": "كتابة",
    # الألف المقصورة والممدودة
    "عال": "عالٍ", "مستوا": "مستوى", "مبنا": "مبنى",
    # الهمزة المتوسطة
    "يسال": "يسأل", "يقرا": "يقرأ", "يبدا": "يبدأ",
    # أخطاء شائعة
    "الكن": "لكن", "هاذا": "هذا", "هاذه": "هذه",
    "ذالك": "ذلك", "االن": "الآن",
    "ايضا": "أيضاً", "اكثر": "أكثر", "اقل": "أقل",
    "اول": "أول", "احيانا": "أحياناً", "ابدا": "أبداً",
    "اخيرا": "أخيراً", "كثيرا": "كثيراً", "جدا": "جداً",
    "قليلا": "قليلاً", "معا": "معاً", "سويا": "سوياً",
    # راءعة / رائعة
    "راءعة": "رائعة", "راءع": "رائع", "راءعت": "رائعة",
    # تمييز العدد: خمسة غرف → خمس غرف
    # (يُعالج بقاعدة منفصلة أدناه)
}

# أخطاء المطابقة العددية: المذكر مع المؤنث والعكس
GENDER_ERRORS = {
    # أعداد مع مؤنث (يجب حذف التاء)
    r'\bخمسةُ?\s+(غرف|طاولات|كراسي|نوافذ|أبواب|سيارات|شجرات|أشجار)\b': lambda m: m.group(0).replace("خمسة", "خمس"),
    r'\bأربعةُ?\s+(غرف|طاولات|كراسي|نوافذ|أبواب|سيارات)\b': lambda m: m.group(0).replace("أربعة", "أربع"),
    r'\bثلاثةُ?\s+(غرف|طاولات|كراسي|نوافذ|أبواب|سيارات)\b': lambda m: m.group(0).replace("ثلاثة", "ثلاث"),
    r'\bستةُ?\s+(غرف|طاولات|كراسي|نوافذ|أبواب|سيارات)\b': lambda m: m.group(0).replace("ستة", "ست"),
    r'\bسبعةُ?\s+(غرف|طاولات|كراسي|نوافذ|أبواب|سيارات)\b': lambda m: m.group(0).replace("سبعة", "سبع"),
    r'\bثمانيةُ?\s+(غرف|طاولات|كراسي|نوافذ|أبواب|سيارات)\b': lambda m: m.group(0).replace("ثمانية", "ثماني"),
    r'\bتسعةُ?\s+(غرف|طاولات|كراسي|نوافذ|أبواب|سيارات)\b': lambda m: m.group(0).replace("تسعة", "تسع"),
    r'\bعشرةُ?\s+(غرف|طاولات|كراسي|نوافذ|أبواب|سيارات)\b': lambda m: m.group(0).replace("عشرة", "عشر"),
}

# أدوات الربط العربية
CONNECTORS = [
    'و', 'ثم', 'أو', 'لكن', 'لذلك', 'إذن', 'حيث',
    'بينما', 'كما', 'أيضاً', 'أما', 'مع ذلك', 'بالإضافة',
    'من ناحية', 'في حين', 'رغم', 'على الرغم', 'بعد أن', 'قبل أن',
]


def evaluate_writing(text: str, min_words: int = 20) -> dict:
    if not text or len(text.strip()) < 10:
        return {
            "spelling_score": 0, "structure_score": 0, "overall_score": 0,
            "errors": [], "feedback": "النص قصير جداً. يرجى الكتابة أكثر.",
        }

    words = text.split()
    word_count = len(words)

    spelling_result  = _check_spelling(text, words)
    structure_result = _check_structure(text, words, word_count, min_words)
    gender_errors    = _check_gender_agreement(text)

    # دمج أخطاء المطابقة مع أخطاء الإملاء
    all_errors = spelling_result["corrections"] + gender_errors
    error_count = len(all_errors)

    # إعادة حساب الدرجة مع الأخطاء النحوية
    total_words = max(word_count, 1)
    combined_error_rate = error_count / total_words
    adjusted_spelling = max(0, int((1 - combined_error_rate * 3) * 100))
    adjusted_spelling = min(100, adjusted_spelling)

    overall = round((adjusted_spelling * 0.5) + (structure_result["score"] * 0.5))

    return {
        "spelling_score": adjusted_spelling,
        "structure_score": structure_result["score"],
        "overall_score": overall,
        "word_count": word_count,
        "spelling_errors": [e["wrong"] for e in all_errors],
        "spelling_corrections": all_errors,
        "errors": all_errors,
        "connectors_found": structure_result["connectors"],
        "sentences_count": structure_result["sentences"],
        "strengths": _get_strengths({"score": adjusted_spelling, "error_count": error_count}, structure_result),
        "improvements": _get_improvements({"error_count": error_count}, structure_result, word_count, min_words),
        "feedback": _generate_writing_feedback(overall),
    }


def _check_spelling(text: str, words: list) -> dict:
    errors = []
    corrections = []
    for word in words:
        clean_word = re.sub(r'[\u064B-\u065F\u060C\u061B\u061F.,!?]', '', word)
        if clean_word in SPELLING_ERRORS:
            errors.append(clean_word)
            corrections.append({"wrong": clean_word, "correct": SPELLING_ERRORS[clean_word],
                                 "explanation": "خطأ إملائي"})
    total_words = max(len(words), 1)
    error_rate = len(errors) / total_words
    score = max(0, int((1 - error_rate * 3) * 100))
    return {"score": min(100, score), "errors": errors, "corrections": corrections, "error_count": len(errors)}


def _check_gender_agreement(text: str) -> list:
    errors = []
    for pattern, fix in GENDER_ERRORS.items():
        for m in re.finditer(pattern, text):
            wrong   = m.group(0)
            correct = fix(m)
            if wrong != correct:
                errors.append({"wrong": wrong, "correct": correct,
                                "explanation": "خطأ في المطابقة العددية"})
    return errors


def _check_structure(text: str, words: list, word_count: int, min_words: int) -> dict:
    score = 40
    if word_count >= min_words * 2:   score += 25
    elif word_count >= min_words:      score += 15
    elif word_count >= min_words // 2: score += 5
    found_connectors = [c for c in CONNECTORS if c in text]
    score += min(20, len(found_connectors) * 5)
    punctuation_count = len(re.findall(r'[.،؟!]', text))
    if punctuation_count >= 3:   score += 10
    elif punctuation_count >= 1: score += 5
    sentences = max(1, len(re.split(r'[.!؟]', text)))
    if sentences >= 3: score += 5
    return {"score": min(100, score), "connectors": found_connectors,
            "sentences": sentences, "punctuation_count": punctuation_count}


def _get_strengths(spelling: dict, structure: dict) -> list:
    strengths = []
    if spelling["score"] >= 80:
        strengths.append("إملاء ممتاز مع أخطاء قليلة")
    if len(structure["connectors"]) >= 3:
        strengths.append("استخدام جيد لأدوات الربط")
    if structure["sentences"] >= 4:
        strengths.append("تنوع في بناء الجمل")
    return strengths if strengths else ["استمر في الكتابة والتدريب!"]


def _get_improvements(spelling: dict, structure: dict, word_count: int, min_words: int) -> list:
    improvements = []
    ec = spelling["error_count"]
    if ec == 1:
        improvements.append("صحّح الخطأ الإملائي")
    elif ec > 1:
        improvements.append("صحّح الأخطاء الإملائية")
    if len(structure["connectors"]) < 2:
        improvements.append("أضف أدوات ربط مثل (لأن، لذلك، بينما، مع ذلك)")
    if word_count < min_words:
        improvements.append(f"أضف {min_words - word_count} كلمة على الأقل")
    return improvements


def _generate_writing_feedback(overall: int) -> str:
    if overall >= 85:   return "ممتاز! كتابتك واضحة وصحيحة إملائياً."
    elif overall >= 70: return "جيد جداً! انتبه لبعض الأخطاء الإملائية البسيطة."
    elif overall >= 55: return "جيد! ركّز على الإملاء الصحيح وأدوات الربط."
    else:               return "استمر في التدريب! راجع قواعد الإملاء وحاول الكتابة بجمل أطول."
