"""
التدقيق الإملائي والنحوي المتقدم — محرك تدقيق حقيقي (وليس مجرد قوائم يدوية).

البنية (من الأسرع إلى الأشمل):
  الطبقة ١ — قاموس الأخطاء الشائعة المُعدَّة يدوياً (فورية، بشرح دقيق لكل خطأ).
  الطبقة ٢ — قاموس عربي حقيقي (٤٤٬١٣٠ كلمة من Arramooz) + تسامح صرفي بسيط
             (نزع السوابق/اللواحق الشائعة) + اقتراح أقرب كلمة عبر BK-Tree
             ومسافة Damerau-Levenshtein موزونة بحروف عربية متشابهة صوتياً.
  الطبقة ٣ (اختيارية، غير مفعّلة افتراضياً) — Gemini، ولا تُستخدم لاكتشاف
             الأخطاء الإملائية بعد الآن (بناءً على طلب صريح)، بل تبقى متاحة
             فقط كدالة يمكن استدعاؤها يدوياً لأغراض أخرى (نحو/سياق)، مع العلم
             أن هذه المهمة أصبحت مسؤولية app/services/context_eval.py.

كل خطأ يُعاد مع (start, end) الدقيقين في النص الأصلي، محسوبين عبر finditer
(وليس str.find) — لضمان تمييز الكلمة الصحيحة حتى لو تكررت عدة مرات في النص.
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


# ═══════════════════════ التطبيع (Normalization) ═══════════════════════
# نطبّع الكلمة للمقارنة فقط (إزالة تشكيل/تطويل)، ونعرض دائماً الكتابة الأصلية.

_TASHKEEL_TATWEEL_RE = re.compile(r"[\u064B-\u065F\u0670\u0640]")


def _normalize_for_lookup(word: str) -> str:
    if _HAS_PYARABIC:
        return araby.strip_tashkeel(araby.strip_tatweel(word))
    return _TASHKEEL_TATWEEL_RE.sub("", word)


# ═══════════════════════ الطبقة ١: قاموس الأخطاء الشائعة ═══════════════════════

HAMZA_ERRORS: dict[str, str] = {
    "انا": "أنا",
    "اكتب": "أكتب", "اكل": "أكل", "اذهب": "أذهب", "اقرا": "أقرأ",
    "ارى": "أرى", "اريد": "أريد", "احب": "أحب", "احضر": "أحضر",
    "اسكن": "أسكن", "اسكنت": "أسكنت", "اسكنا": "أسكنا",
    "اعيش": "أعيش", "اعيشت": "أعيشت", "اخذ": "أخذ", "امل": "أمل",
    "ابدا": "أبدأ",
    "اسال": "أسأل", "اجب": "أجب", "اعمل": "أعمل", "افهم": "أفهم",
    "إستخدم": "استخدم", "إستقبل": "استقبل", "إنتهى": "انتهى",
    "إنتظر": "انتظر", "إستمر": "استمر", "إنطلق": "انطلق",
    "إجتمع": "اجتمع", "إحتاج": "احتاج", "إستمتع": "استمتع",
    "إشترك": "اشترك", "إعتقد": "اعتقد", "إستطاع": "استطاع",
    "إنتقل": "انتقل", "إتصل": "اتصل", "إستفاد": "استفاد",
    "الوان": "ألوان", "الوانها": "ألوانها", "الوانه": "ألوانه",
    "انيق": "أنيق", "انيقة": "أنيقة",
    "هاديء": "هادئ", "هاديئة": "هادئة",
    "دافيء": "دافئ", "دافيئة": "دافئة",
}

TA_HA_ERRORS: dict[str, str] = {
    "مدرست": "مدرسة", "طالبت": "طالبة", "كتابت": "كتابة",
    "غرفت": "غرفة", "حديقت": "حديقة", "رحلت": "رحلة",
    "معلمه": "معلمة", "طالبه": "طالبة", "مدرسه": "مدرسة",
    "حديقه": "حديقة", "مساحه": "مساحة", "كبيره": "كبيرة",
}

ALEF_YA_ERRORS: dict[str, str] = {
    "مستوا": "مستوى", "مبنا": "مبنى", "معنا": "معنى",
    "يسال": "يسأل", "يقرا": "يقرأ", "يبدا": "يبدأ", "يرا": "يرى",
    "علا": "على", "الا": "إلى",
}

COMMON_ERRORS: dict[str, str] = {
    "الكن": "لكن", "هاذا": "هذا", "هاذه": "هذه", "ذالك": "ذلك",
    "االن": "الآن", "ايضا": "أيضاً", "اكثر": "أكثر", "اقل": "أقل",
    "اول": "أول", "احيانا": "أحياناً", "ابدا": "أبداً",
    "اخيرا": "أخيراً", "كثيرا": "كثيراً", "جدا": "جداً",
    "قليلا": "قليلاً", "معا": "معاً", "سويا": "سوياً",
    "راءعة": "رائعة", "راءع": "رائع", "راءعت": "رائعة",
    "انشاء": "إنشاء", "هاؤلاء": "هؤلاء",
}

ALL_DICTS = [
    (HAMZA_ERRORS, "خطأ في همزة القطع/الوصل"),
    (TA_HA_ERRORS, "خطأ في التاء المربوطة/المفتوحة"),
    (ALEF_YA_ERRORS, "خطأ في الألف المقصورة/الياء"),
    (COMMON_ERRORS, "خطأ إملائي شائع"),
]

_TOKEN_RE = re.compile(r"[\w\u0621-\u064A]+", re.UNICODE)


_DICT_PREFIXES = ["وبال", "وكال", "وفال", "وال", "فال", "بال", "كال", "لل",
                   "ال", "و", "ف", "ب", "ك", "ل"]


def _check_manual_dictionary(raw_word: str, clean: str) -> dict | None:
    """يبحث عن الكلمة في القواميس اليدوية، مع نزع سوابق شائعة (أل التعريف
    وحروف العطف/الجر الملتصقة بها معاً، مثل: والمساحه، فالمدرسه، بالحديقه)."""
    for dictionary, explanation in ALL_DICTS:
        if clean in dictionary and dictionary[clean] != clean:
            return {"correct": dictionary[clean], "explanation": explanation, "source": "dictionary"}
        for pre in _DICT_PREFIXES:
            if clean.startswith(pre) and len(clean) - len(pre) >= 2:
                rest = clean[len(pre):]
                if rest in dictionary and dictionary[rest] != rest:
                    return {"correct": pre + dictionary[rest], "explanation": explanation, "source": "dictionary"}
    return None


# ═══════════════════════ الطبقة ٢: قاموس عربي حقيقي + اقتراح ذكي ═══════════════════════

_WORDLIST_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "arabic_wordlist.txt")


def _load_wordlist() -> set:
    try:
        with open(_WORDLIST_PATH, encoding="utf-8") as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()


ARABIC_WORDS: set = _load_wordlist()  # ٤٤٬١٣٠ كلمة عربية حقيقية (Arramooz)

# سوابق ولواحق شائعة نُزيلها مؤقتاً قبل البحث في القاموس، لتفادي اعتبار صيغ
# صرفية صحيحة (جمع/مثنى/تأنيث/ضمائر متصلة) أخطاءً وهمية (False Positives).
_PREFIXES = ["وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب", "ك", "ل", "س",
             "أ", "ي", "ت", "ن"]  # الأربعة الأخيرة: بادئات تصريف الفعل المضارع
_SUFFIXES = ["تان", "تين", "ون", "ين", "ات", "هما", "هم", "هن", "كما", "كم", "كن",
             "نا", "ها", "ني", "تي", "وا", "ة", "ه", "ي", "ت", "ا", "ن"]


def _in_dict(word: str) -> bool:
    if word in ARABIC_WORDS:
        return True
    # التاء المربوطة تتحوّل إلى مفتوحة قبل الضمائر المتصلة (مدرستي ← مدرسة+ي)
    if word.endswith("ت") and (word[:-1] + "ة") in ARABIC_WORDS:
        return True
    return False


def _is_known_word(word: str) -> bool:
    """يتحقق من وجود الكلمة في القاموس، مع تجربة نزع السوابق/اللواحق الشائعة
    (تسامح صرفي بسيط يغني عن محلل صرفي كامل لحالات الاستخدام المدرسية)،
    بما في ذلك بادئات تصريف الفعل المضارع (يفعل/تفعل/نفعل/أفعل)."""
    if not word or len(word) < 2:
        return True  # حرف مفرد/رمز — لا نخوض في تدقيقه
    if _in_dict(word):
        return True

    candidates = {word}
    # مستويان من نزع السوابق (مثل: و + يـ = "ويفعل")
    for _ in range(2):
        new_candidates = set(candidates)
        for w in candidates:
            for pre in _PREFIXES:
                if w.startswith(pre) and len(w) - len(pre) >= 2:
                    new_candidates.add(w[len(pre):])
        candidates = new_candidates

    for w in candidates:
        if _in_dict(w):
            return True
        for suf in _SUFFIXES:
            if w.endswith(suf) and len(w) - len(suf) >= 2:
                if _in_dict(w[: -len(suf)]):
                    return True
    return False


# ── مسافة Damerau-Levenshtein قياسية (لبناء BK-Tree بمقياس صحيح ومتّسق) ──

def _dl_distance(a: str, b: str) -> int:
    la, lb = len(a), len(b)
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,
                d[i][j - 1] + 1,
                d[i - 1][j - 1] + cost,
            )
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)  # قلب حرفين (Transposition)
    return d[la][lb]


# ── حروف عربية متشابهة صوتياً/كتابياً — تُستخدم لإعادة ترتيب المرشّحين فقط ──
_CONFUSABLE_PAIRS = {
    frozenset(("ض", "ظ")): 0.5, frozenset(("س", "ص")): 0.5, frozenset(("ط", "ت")): 0.5,
    frozenset(("ذ", "ز")): 0.5, frozenset(("د", "ذ")): 0.5, frozenset(("ق", "ك")): 0.5,
    frozenset(("ه", "ة")): 0.3, frozenset(("ي", "ى")): 0.3, frozenset(("ئ", "ى")): 0.4,
    frozenset(("ا", "أ")): 0.2, frozenset(("ا", "إ")): 0.2, frozenset(("ا", "آ")): 0.2,
    frozenset(("ء", "ئ")): 0.3, frozenset(("ء", "ؤ")): 0.3, frozenset(("ئ", "ؤ")): 0.3,
    frozenset(("ا", "ئ")): 0.5, frozenset(("ا", "ء")): 0.5,
}


def _weighted_distance(a: str, b: str) -> float:
    """نسخة موزونة من نفس الخوارزمية، تُستخدم فقط لترتيب أفضل مرشّح من بين
    عدة كلمات متقاربة (وليست للبحث في الشجرة، حفاظاً على صحة القياس فيها)."""
    la, lb = len(a), len(b)
    d = [[0.0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            if a[i - 1] == b[j - 1]:
                cost = 0
            else:
                cost = _CONFUSABLE_PAIRS.get(frozenset((a[i - 1], b[j - 1])), 1)
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


class _BKTree:
    """هيكل بيانات BK-Tree للبحث السريع عن أقرب الكلمات، بدل مقارنة الكلمة
    الخاطئة بكل كلمات القاموس (٤٤ ألف كلمة) واحدة تلو الأخرى."""

    __slots__ = ("word", "children")

    def __init__(self, word: str):
        self.word = word
        self.children: dict[int, "_BKTree"] = {}

    def add(self, word: str) -> None:
        d = _dl_distance(self.word, word)
        if d == 0:
            return
        child = self.children.get(d)
        if child is None:
            self.children[d] = _BKTree(word)
        else:
            child.add(word)

    def search(self, word: str, max_dist: int) -> list[tuple[str, int]]:
        results = []
        d = _dl_distance(self.word, word)
        if d <= max_dist:
            results.append((self.word, d))
        for dist, child in self.children.items():
            if abs(dist - d) <= max_dist:
                results.extend(child.search(word, max_dist))
        return results


_bk_root: "_BKTree | None" = None


def _get_bk_tree() -> "_BKTree | None":
    """يُنشئ الشجرة مرة واحدة فقط عند أول استخدام (Lazy build) لتفادي إبطاء
    إقلاع الخادم؛ البناء لمرة واحدة يستغرق ثوانٍ معدودة لـ٤٤ ألف كلمة."""
    global _bk_root
    if _bk_root is None and ARABIC_WORDS:
        it = iter(ARABIC_WORDS)
        _bk_root = _BKTree(next(it))
        for w in it:
            _bk_root.add(w)
    return _bk_root


def _suggest_correction(word: str, max_dist: int | None = None) -> str | None:
    """يقترح أقرب كلمة صحيحة من القاموس الحقيقي عبر BK-Tree، مُرتَّبة بحسب
    المسافة الموزونة (تُفضِّل تصحيحات الحروف المتشابهة صوتياً) ثم طول الكلمة
    الأقرب للأصل (لتفادي اقتراح كلمة قصيرة جداً غير ذات صلة).
    نُشدِّد العتبة المسموحة للكلمات الأطول لتقليل الاقتراحات الخاطئة على
    أفعال معتلّة نادرة لا يغطيها القاموس بشكل كافٍ."""
    if max_dist is None:
        max_dist = 1 if len(word) >= 6 else 2
    tree = _get_bk_tree()
    if tree is None or len(word) < 3:
        return None
    candidates = tree.search(word, max_dist)
    if not candidates:
        return None
    candidates.sort(key=lambda c: (_weighted_distance(word, c[0]), abs(len(c[0]) - len(word))))
    return candidates[0][0]


def check_spelling_layer1(text: str) -> list[dict]:
    """
    الفحص المحلي الكامل (الطبقتان ١ و٢ معاً): يمر على كل كلمة في النص،
    يبحث أولاً في القاموس اليدوي (تفسير دقيق جاهز)، فإن لم يجدها يتحقق من
    وجودها في القاموس العربي الحقيقي (مع تسامح صرفي)، فإن لم تكن موجودة
    يقترح أقرب كلمة صحيحة عبر BK-Tree.
    """
    errors: list[dict] = []
    for m in _TOKEN_RE.finditer(text):
        raw_word = m.group(0)
        clean = _normalize_for_lookup(raw_word)

        manual = _check_manual_dictionary(raw_word, clean)
        if manual is not None:
            errors.append({
                "wrong": raw_word, "correct": manual["correct"],
                "explanation": manual["explanation"],
                "start": m.start(), "end": m.end(), "source": "dictionary",
            })
            continue

        if ARABIC_WORDS and len(clean) >= 3 and not _is_known_word(clean):
            suggestion = _suggest_correction(clean)
            if suggestion and suggestion != clean:
                errors.append({
                    "wrong": raw_word, "correct": suggestion,
                    "explanation": "الكلمة غير موجودة في القاموس العربي، أقرب كلمة صحيحة مقترحة",
                    "start": m.start(), "end": m.end(), "source": "dictionary_lookup",
                })
    return errors


# ═══════════════════════ الطبقة ٣ (اختيارية): Gemini ═══════════════════════
# ⚠️ لم تعد تُستخدم افتراضياً لاكتشاف الأخطاء الإملائية (بناءً على طلب صريح) —
# مهمة النحو/السياق أصبحت مسؤولية app/services/context_eval.py حصرياً.
# أبقيت الدالة هنا فقط للتوافق مع أي استدعاء قديم صريح (use_ai=True يدوياً).

_GEMINI_PROMPT = """أنت مدقق لغوي عربي متخصص وشديد الدقة. اقرأ النص التالي كلمة كلمة بعناية فائقة،
ولا تكتفِ بفحص سريع. اكتشف كل الأخطاء الإملائية والنحوية بلا استثناء، خصوصاً:
- أخطاء الهمزة المتوسطة والمتطرفة (مثل: هاديء بدل هادئ، دافيء بدل دافئ)
- أخطاء همزة القطع/الوصل في أول الكلمة (مثل: انيق بدل أنيق)
- أخطاء التاء المربوطة/الهاء في نهاية الكلمة (مثل: كبيره بدل كبيرة)
- أخطاء الألف المقصورة/الممدودة
- أخطاء المطابقة النحوية (التذكير/التأنيث، الإفراد/الجمع)
لا تصحح الأسلوب أو تقترح كلمات مرادفة، وركّز فقط على الصحة الإملائية والنحوية.
راجع النص مرتين ذهنياً قبل إعادة الإجابة للتأكد من عدم تفويت أي خطأ.

أعد النتيجة بصيغة JSON فقط، بدون أي نص إضافي، وفق هذا الشكل بالضبط:
{"errors": [{"wrong": "الكلمة الخاطئة كما وردت حرفياً في النص", "correct": "التصحيح", "explanation": "شرح موجز بالعربية"}]}

إذا لم تجد أي أخطاء، أعد: {"errors": []}

النص:
"""


def check_spelling_layer2_gemini(text: str, known_wrong_words: set) -> list[dict]:
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
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 2048},
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
            results = []
            for e in parsed.get("errors", []):
                wrong = e.get("wrong", "")
                if not wrong or wrong in known_wrong_words:
                    continue
                idx = text.find(wrong)
                if idx == -1:
                    wrong_clean = _normalize_for_lookup(wrong)
                    idx = text.find(wrong_clean)
                    if idx == -1:
                        print(f"[spell_check] Gemini returned unmatched word: {wrong!r} not found in text")
                        continue
                    wrong = wrong_clean
                results.append({
                    "wrong": wrong, "correct": e.get("correct", wrong),
                    "explanation": e.get("explanation", "خطأ نحوي/إملائي"),
                    "start": idx, "end": idx + len(wrong), "source": "ai",
                })
            return results
    except Exception as ex:
        print(f"[spell_check] Gemini layer failed: {type(ex).__name__}: {ex}")
        return []


# ═══════════════════════ نقطة الدخول الموحّدة ═══════════════════════

def check_spelling(text: str, use_ai: bool = False) -> dict:
    """
    نقطة الدخول: تُشغّل دائماً الفحص المحلي الكامل (قاموس يدوي + قاموس عربي
    حقيقي مع اقتراح ذكي). use_ai=True يُضيف طبقة Gemini كطبقة رابعة اختيارية
    فقط (معطّلة افتراضياً الآن، انظر التعليق أعلى check_spelling_layer2_gemini).
    """
    if not text or not text.strip():
        return {"errors": [], "error_count": 0, "score": 100}

    local_errors = check_spelling_layer1(text)
    known_wrong = {e["wrong"] for e in local_errors}

    ai_errors = []
    if use_ai:
        ai_errors = check_spelling_layer2_gemini(text, known_wrong)

    all_errors = sorted(local_errors + ai_errors, key=lambda e: e["start"])
    word_count = max(len(text.split()), 1)
    error_rate = len(all_errors) / word_count
    score = max(0, min(100, int((1 - error_rate * 3) * 100)))

    return {"errors": all_errors, "error_count": len(all_errors), "score": score}
