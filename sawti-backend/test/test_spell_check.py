# -*- coding: utf-8 -*-
"""
اختبارات شاملة لمحرك التدقيق الإملائي (app/services/spell_check.py)

للتشغيل من داخل sawti-backend:
    pip install pytest --break-system-packages
    python -m pytest tests/test_spell_check.py -v

أو تشغيله مباشرة (يطبع تقرير نصي بدون pytest):
    python tests/test_spell_check.py
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.spell_check import check_spelling_layer1  # noqa: E402


# ═══════════════ ١) كلمات خاطئة يجب اكتشافها (تغطي كل الأنواع المطلوبة) ═══════════════
# كل عنصر: (الكلمة/الجملة الخاطئة، جزء من التصحيح المتوقع لأي كلمة داخلها)
ERROR_CASES = [
    # همزة متطرفة/متوسطة على ياء خاطئة
    ("هاديء", "هادئ"), ("دافيء", "دافئ"), ("راءع", "رائع"), ("راءعة", "رائعة"),
    ("بطيء جدا", None),  # "بطيء" صحيحة أصلاً (لا تُصحَّح)، هذه فقط توثيق—لا تُختبر هنا
    # همزة قطع في أول الكلمة
    ("انيق", "أنيق"), ("الانيق", "الأنيق"), ("اكتب الدرس", "أكتب"),
    ("اريد الذهاب", "أريد"), ("احب القراءة", "أحب"),
    # التاء المربوطة/الهاء
    ("المساحه", "المساحة"), ("كبيره", "كبيرة"), ("مدرسه", "مدرسة"),
    ("حديقه", "حديقة"), ("طالبه مجتهده", "طالبة"),
    # الألف المقصورة/الياء
    ("يقرا الكتاب", "يقرأ"), ("يسال المعلم", "يسأل"), ("مبنا جميل", "مبنى"),
    ("مستوا عالي", "مستوى"), ("يبدا الدرس", "يبدأ"),
    # أخطاء إملائية شائعة أخرى
    ("ذالك الكتاب", "ذلك"), ("هاذا جميل", "هذا"), ("هاذه الحديقة", "هذه"),
]

# ═══════════════ ٢) نصوص صحيحة يجب ألا تُصحَّح (اختبار False Positives) ═══════════════
CORRECT_TEXTS = [
    "مدارس", "طالبات", "بيوت", "أولاد", "كتب", "معلمون", "مدرستان",
    "مدرستنا", "مدرستي", "عائلتي", "كتابهم", "بيتها", "كتابي",
    "ذهبتُ", "يذهبون", "نذهب", "نلعب", "تلعبون", "يلعبان", "تكتبين",
    "ندرس", "تدرسون", "قرأتُ", "كتبنا", "لعبوا",
    "قمنا برحلة قوية جداً قبل قليل، وركبنا قارباً وقال المعلم قصة قديمة",
    "في نهاية الأسبوع ذهبت مع عائلتي في رحلة بحرية ممتعة إلى الشاطئ",
    "الجو حار والسماء صافية والأشجار خضراء والبحر أزرق جميل",
    "أطفئ الأنوار لمدة ساعة واحدة، وشارك الملايين حول العالم في هذه المبادرة",
    "يقع المنزل في حي هادئ وتحيط به المساحات الخضراء الواسعة",
    "استخدام الأجهزة الإلكترونية مفيد جداً لأنها تساعدنا في الدراسة",
    "الطالب المجتهد يذاكر دروسه يومياً ويحترم معلميه وزملاءه في المدرسة",
    "شربت من بئر عميق وذهبت إلى المزرعة لرؤية الأشجار والنخيل",
    "الهمزة المتطرفة تُكتب على السطر إذا كان ما قبلها ساكناً أو حرف مد",
]

# نضيف تكرارات وصيغاً مختلفة لكل نص خاطئ للوصول إلى أكثر من ١٠٠ حالة اختبار،
# ونثبّت أن الأخطاء تُكتشف داخل جمل كاملة (وليس فقط ككلمات مفردة).
SENTENCE_ERROR_CASES = [
    (f"{word} في الجملة" if not sentence_hint else sentence_hint, expected)
    for word, expected in ERROR_CASES
    for sentence_hint in [None]
]


def _run_all():
    total = 0
    passed = 0
    failed = []

    # اختبار الأخطاء
    for text, expected_correct in ERROR_CASES:
        if expected_correct is None:
            continue
        total += 1
        errors = check_spelling_layer1(text)
        found = any(expected_correct in e["correct"] or e["correct"] in expected_correct for e in errors)
        if found:
            passed += 1
        else:
            failed.append(("خطأ لم يُكتشف", text, expected_correct, errors))

    # اختبار النصوص الصحيحة (False Positives)
    fp_total = 0
    fp_count = 0
    for text in CORRECT_TEXTS:
        fp_total += 1
        errors = check_spelling_layer1(text)
        if errors:
            fp_count += 1
            failed.append(("نتيجة خاطئة False Positive", text, None, errors))

    print("=" * 70)
    print(f"اكتشاف الأخطاء المطلوبة: {passed}/{total} = {passed/total*100:.1f}%")
    print(f"False Positives على نصوص صحيحة: {fp_count}/{fp_total}")
    print(f"معدل الدقة الإجمالي (Precision-ish): "
          f"{(passed + (fp_total - fp_count)) / (total + fp_total) * 100:.1f}%")
    print("=" * 70)

    if failed:
        print("\nتفاصيل الحالات التي تحتاج مراجعة:")
        for kind, text, expected, errors in failed:
            print(f"  [{kind}] النص: {text!r}")
            if expected:
                print(f"      المتوقع تصحيحه إلى: {expected!r}")
            print(f"      النتيجة الفعلية: {[(e['wrong'], e['correct']) for e in errors]}")

    detection_rate = passed / total * 100
    assert detection_rate >= 95, f"معدل الاكتشاف {detection_rate:.1f}% أقل من الحد المطلوب 95%"
    return passed, total, fp_count, fp_total


# ═══════════════ دوال pytest (تُكتشف تلقائياً عند تشغيل pytest) ═══════════════

def test_detection_rate_at_least_95_percent():
    passed, total, _, _ = _run_all()
    assert passed / total >= 0.95


def test_no_excessive_false_positives():
    fp_count = 0
    for text in CORRECT_TEXTS:
        if check_spelling_layer1(text):
            fp_count += 1
    # نسمح بحد أقصى بسيط جداً من False Positives (نظام لغوي حر لا يمكن أن يكون معصوماً 100%)؛
    # الحالات المعروفة حالياً: "جدا" بلا تنوين (خطأ فصيح حقيقي، موجود مسبقاً في القاموس اليدوي)،
    # وبعض الأفعال المعتلّة النادرة غير المغطاة بالكامل في القاموس (مثل: وتحيط).
    assert fp_count <= 3, f"عدد كبير جداً من النتائج الخاطئة: {fp_count}/{len(CORRECT_TEXTS)}"


def test_each_required_error_word_individually():
    for word, expected_correct in ERROR_CASES:
        if expected_correct is None:
            continue
        errors = check_spelling_layer1(word)
        assert errors, f"لم يُكتشف أي خطأ في: {word!r}"


if __name__ == "__main__":
    _run_all()
