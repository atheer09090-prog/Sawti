"""
إدارة الدروس والمواضيع.

يُحفَظ المحتوى القابل للتعديل من لوحة المعلم في PostgreSQL (جدول
content_store عبر app/services/content_store.py) وليس في ملفات على قرص
الخادم، حتى لا تضيع التعديلات عند إعادة النشر. شكل JSON الذي تعيده
الواجهات لم يتغير.
"""
import os
import copy
from fastapi import APIRouter, HTTPException, Depends
from app.services.current_user import require_teacher
from app.services import content_store
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

# كل عمليات التعديل (POST/PUT/DELETE) للمعلم فقط؛ الـGET يبقى مفتوحًا لأن الطالب يقرأ منه.
TEACHER_ONLY = [Depends(require_teacher)]

# البيانات الافتراضية
DEFAULT_DATA = {
    "speaking": [
        {
            "id": "summer",
            "title": "وَصْفُ رِحْلَةٍ صَيْفِيَّةٍ",
            "level": "سَهْلٌ",
            "icon": "🏖️",
            "desc": "تَحَدَّثْ عَنْ عُطْلَتِكَ الصَّيْفِيَّةِ",
            "topics": ["رِحْلَةٌ بَحْرِيَّةٌ", "رِحْلَةٌ جَبَلِيَّةٌ", "صُورَةٌ دَالَّةٌ عَلَى تَعَلُّمٍ", "رِحْلَةٌ جَوِّيَّةٌ"]
        },
        {
            "id": "earth",
            "title": "قِرَاءَةُ مَنْشُورٍ تَوْعَوِيٍّ — سَاعَةُ الأَرْضِ",
            "level": "مُتَوَسِّطٌ",
            "icon": "🌍",
            "desc": "اقْرَأِ الْمَنْشُورَ وَأَجِبْ عَنِ الأَسْئِلَةِ",
            "topics": []
        },
        {
            "id": "opinion",
            "title": "التَّعْبِيرُ عَنِ الرَّأْيِ",
            "level": "مُتَقَدِّمٌ",
            "icon": "💬",
            "desc": "عَبِّرْ عَنْ رَأْيِكَ بِأُسْلُوبٍ لُغَوِيٍّ سَلِيمٍ",
            "topics": []
        }
    ],
    "writing": [
        {
            "id": "home",
            "title": "وَصْفُ الْمَنْزِلِ",
            "icon": "🏠",
            "hints": ["الْمَوْقِعُ وَالْحَيُّ", "الشَّكْلُ الْخَارِجِيُّ", "الْغُرَفُ", "مَا يُمَيِّزُهُ"]
        },
        {
            "id": "neighborhood",
            "title": "وَصْفُ النَّخْلَةِ",
            "icon": "🌴",
            "hints": ["مَوْقِعُ النَّخْلَةِ", "شَكْلُهَا", "فَوَائِدُهَا", "أَهَمِّيَّتُهَا"]
        },
        {
            "id": "mosque",
            "title": "وَصْفُ الْمَسْجِدِ",
            "icon": "🕌",
            "hints": ["الشَّكْلُ الْمَعْمَارِيُّ", "الأَجْوَاءُ الرُّوحَانِيَّةُ", "الْخَدَمَاتُ", "الأَهَمِّيَّةُ"]
        }
    ]
}


def _read() -> dict:
    return {
        "speaking": content_store.get("speaking", lambda: DEFAULT_DATA["speaking"]),
        "writing": content_store.get("writing", lambda: DEFAULT_DATA["writing"]),
    }


def _write(data: dict):
    content_store.put("speaking", data["speaking"])
    content_store.put("writing", data["writing"])


# ── Models ──

class SpeakingLesson(BaseModel):
    id: str
    title: str
    level: str
    icon: str
    desc: str
    topics: List[str] = []

class WritingTopic(BaseModel):
    id: str
    title: str
    icon: str
    hints: List[str] = []


# ── Endpoints ──

@router.get("/speaking")
def get_speaking_lessons():
    return _read()["speaking"]

@router.get("/writing")
def get_writing_topics():
    return _read()["writing"]

@router.post("/speaking", dependencies=TEACHER_ONLY)
def add_speaking_lesson(lesson: SpeakingLesson):
    data = _read()
    # تحقق من عدم تكرار الـ id
    if any(l["id"] == lesson.id for l in data["speaking"]):
        raise HTTPException(400, "معرّف الدرس موجود مسبقاً")
    data["speaking"].append(lesson.dict())
    _write(data)
    return {"ok": True}

@router.post("/writing", dependencies=TEACHER_ONLY)
def add_writing_topic(topic: WritingTopic):
    data = _read()
    if any(t["id"] == topic.id for t in data["writing"]):
        raise HTTPException(400, "معرّف الموضوع موجود مسبقاً")
    data["writing"].append(topic.dict())
    _write(data)
    return {"ok": True}

@router.put("/speaking/{lesson_id}", dependencies=TEACHER_ONLY)
def update_speaking_lesson(lesson_id: str, lesson: SpeakingLesson):
    data = _read()
    for i, l in enumerate(data["speaking"]):
        if l["id"] == lesson_id:
            data["speaking"][i] = lesson.dict()
            _write(data)
            return {"ok": True}
    raise HTTPException(404, "الدرس غير موجود")

@router.put("/writing/{topic_id}", dependencies=TEACHER_ONLY)
def update_writing_topic(topic_id: str, topic: WritingTopic):
    data = _read()
    for i, t in enumerate(data["writing"]):
        if t["id"] == topic_id:
            data["writing"][i] = topic.dict()
            _write(data)
            return {"ok": True}
    raise HTTPException(404, "الموضوع غير موجود")

@router.delete("/speaking/{lesson_id}", dependencies=TEACHER_ONLY)
def delete_speaking_lesson(lesson_id: str):
    data = _read()
    data["speaking"] = [l for l in data["speaking"] if l["id"] != lesson_id]
    _write(data)
    return {"ok": True}

@router.delete("/writing/{topic_id}", dependencies=TEACHER_ONLY)
def delete_writing_topic(topic_id: str):
    data = _read()
    data["writing"] = [t for t in data["writing"] if t["id"] != topic_id]
    _write(data)
    return {"ok": True}


# ── Self Learning Questions ──

DEFAULT_SELF_LEARNING = {
    "quiz": [
        {"q": "مَا ضِدُّ كَلِمَةِ «حَزِينٌ»؟", "options": ["غَاضِبٌ", "سَعِيدٌ", "خَائِفٌ", "مُتْعَبٌ"], "correct": 1},
        {"q": "أَيُّ الْجُمَلِ صَحِيحَةٌ؟", "options": ["ذَهَبَ الطَّالِبُ إِلَى الْمَدْرَسَةِ", "الطَّالِبُ ذَهَبَ مَدْرَسَةٍ", "ذَهَبَتْ مَدْرَسَةٌ الطَّالِبُ", "إِلَى ذَهَبَ مَدْرَسَةٍ"], "correct": 0},
        {"q": "مَا مُفْرَدُ «كُتُبٌ»؟", "options": ["كُتَيِّبٌ", "كِتَابٌ", "كَاتِبٌ", "مَكْتُوبٌ"], "correct": 1},
    ],
    "word_order": [
        {"words": ["إِلَى", "ذَهَبَ", "الْمَدْرَسَةِ", "الطَّالِبُ"], "answer": "الطَّالِبُ ذَهَبَ إِلَى الْمَدْرَسَةِ"},
    ],
    "fill_in": [
        {"sentence": "اللُّغَةُ الْعَرَبِيَّةُ لُغَةٌ ________ وَغَنِيَّةٌ بِمُفْرَدَاتِهَا", "answer": "جَمِيلَةٌ"},
    ],
}

def _read_sl() -> dict:
    return content_store.get("self_learning", lambda: DEFAULT_SELF_LEARNING)

def _write_sl(data: dict):
    content_store.put("self_learning", data)


class QuizQuestion(BaseModel):
    q: str
    options: List[str]
    correct: int

class WordOrderQuestion(BaseModel):
    words: List[str]
    answer: str

class FillInQuestion(BaseModel):
    sentence: str
    answer: str


@router.get("/self-learning")
def get_self_learning():
    return _read_sl()

@router.post("/self-learning/quiz", dependencies=TEACHER_ONLY)
def add_quiz_question(q: QuizQuestion):
    data = _read_sl()
    data["quiz"].append(q.dict())
    _write_sl(data)
    return {"ok": True}

@router.put("/self-learning/quiz/{idx}", dependencies=TEACHER_ONLY)
def update_quiz_question(idx: int, q: QuizQuestion):
    data = _read_sl()
    if idx >= len(data["quiz"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["quiz"][idx] = q.dict()
    _write_sl(data)
    return {"ok": True}

@router.delete("/self-learning/quiz/{idx}", dependencies=TEACHER_ONLY)
def delete_quiz_question(idx: int):
    data = _read_sl()
    if idx >= len(data["quiz"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["quiz"].pop(idx)
    _write_sl(data)
    return {"ok": True}

@router.post("/self-learning/word-order", dependencies=TEACHER_ONLY)
def add_word_order(q: WordOrderQuestion):
    data = _read_sl()
    data["word_order"].append(q.dict())
    _write_sl(data)
    return {"ok": True}

@router.put("/self-learning/word-order/{idx}", dependencies=TEACHER_ONLY)
def update_word_order(idx: int, q: WordOrderQuestion):
    data = _read_sl()
    if idx >= len(data["word_order"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["word_order"][idx] = q.dict()
    _write_sl(data)
    return {"ok": True}

@router.delete("/self-learning/word-order/{idx}", dependencies=TEACHER_ONLY)
def delete_word_order(idx: int):
    data = _read_sl()
    if idx >= len(data["word_order"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["word_order"].pop(idx)
    _write_sl(data)
    return {"ok": True}

@router.post("/self-learning/fill-in", dependencies=TEACHER_ONLY)
def add_fill_in(q: FillInQuestion):
    data = _read_sl()
    data["fill_in"].append(q.dict())
    _write_sl(data)
    return {"ok": True}

@router.put("/self-learning/fill-in/{idx}", dependencies=TEACHER_ONLY)
def update_fill_in(idx: int, q: FillInQuestion):
    data = _read_sl()
    if idx >= len(data["fill_in"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["fill_in"][idx] = q.dict()
    _write_sl(data)
    return {"ok": True}

@router.delete("/self-learning/fill-in/{idx}", dependencies=TEACHER_ONLY)
def delete_fill_in(idx: int):
    data = _read_sl()
    if idx >= len(data["fill_in"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["fill_in"].pop(idx)
    _write_sl(data)
    return {"ok": True}


# ── Writing Games ──

DEFAULT_GAMES = {
    "middle_hamza": [
        {"before": "س", "after": "ال", "correct": "ؤ", "opts": ["ؤ","ئ","أ","ء"], "hint": "الهمزة على واو لأن ما قبلها ضمة", "word": "سؤال", "emoji": "❔"},
        {"before": "يَس", "after": "ل", "correct": "أ", "opts": ["أ","ئ","ؤ","ء"], "hint": "الهمزة على ألف لأن ما قبلها ساكن وما بعدها مفتوح", "word": "يسأل", "emoji": "🗣️"},
        {"before": "رَ", "after": "س", "correct": "أ", "opts": ["أ","ئ","ؤ","ء"], "hint": "الهمزة على ألف لأن ما قبلها فتحة", "word": "رأس", "emoji": "🧠"},
        {"before": "بِ", "after": "ر", "correct": "ئ", "opts": ["ئ","ؤ","أ","ء"], "hint": "الهمزة على نبرة لأن ما قبلها كسرة", "word": "بئر", "emoji": "💧"},
        {"before": "فُ", "after": "اد", "correct": "ؤ", "opts": ["ؤ","ئ","أ","ء"], "hint": "الهمزة على واو لأن ما قبلها ضمة", "word": "فؤاد", "emoji": "❤️"},
    ],
    "end_hamza": [
        {"word": "سماء", "type": "ء", "rule": "ما قبلها ألف مد", "emoji": "☁️"},
        {"word": "شيء", "type": "ء", "rule": "ما قبلها ياء ساكنة", "emoji": "📦"},
        {"word": "مبدأ", "type": "أ", "rule": "ما قبلها فتحة", "emoji": "🎯"},
        {"word": "امرؤ", "type": "ؤ", "rule": "ما قبلها ضمة", "emoji": "🧍"},
    ],
    "quick_quiz": [
        {"q": "أيّ كتابة صحيحة؟", "opts": ["سؤال","سئال","سأال","سوال"], "correct": "سؤال", "explain": "الهمزة المتوسطة على واو لأن ما قبلها ضمة", "emoji": "❔"},
        {"q": "أيّ كتابة صحيحة؟", "opts": ["شيء","شئ","شيأ","شيؤ"], "correct": "شيء", "explain": "الهمزة المتطرفة على السطر لأن ما قبلها ياء ساكنة", "emoji": "📦"},
        {"q": "أيّ كتابة صحيحة؟", "opts": ["رأس","رءس","رؤس","رئس"], "correct": "رأس", "explain": "الهمزة المتوسطة على ألف لأن ما قبلها فتحة", "emoji": "🧠"},
    ],
}


def _read_games() -> dict:
    return content_store.get("games", lambda: DEFAULT_GAMES)


def _write_games(data: dict):
    content_store.put("games", data)


class MiddleHamzaQ(BaseModel):
    before: str
    after: str
    correct: str
    opts: List[str]
    hint: str
    word: str
    emoji: str = "✨"

class EndHamzaQ(BaseModel):
    word: str
    type: str
    rule: str
    emoji: str = "✨"

class QuickQuizQ(BaseModel):
    q: str
    opts: List[str]
    correct: str
    explain: str
    emoji: str = "✨"


@router.get("/games")
def get_games():
    return _read_games()

# Middle Hamza
@router.post("/games/middle-hamza", dependencies=TEACHER_ONLY)
def add_middle_hamza(q: MiddleHamzaQ):
    data = _read_games()
    data["middle_hamza"].append(q.dict())
    _write_games(data)
    return {"ok": True}

@router.put("/games/middle-hamza/{idx}", dependencies=TEACHER_ONLY)
def update_middle_hamza(idx: int, q: MiddleHamzaQ):
    data = _read_games()
    if idx >= len(data["middle_hamza"]): raise HTTPException(404, "غير موجود")
    data["middle_hamza"][idx] = q.dict()
    _write_games(data)
    return {"ok": True}

@router.delete("/games/middle-hamza/{idx}", dependencies=TEACHER_ONLY)
def delete_middle_hamza(idx: int):
    data = _read_games()
    data["middle_hamza"].pop(idx)
    _write_games(data)
    return {"ok": True}

# End Hamza
@router.post("/games/end-hamza", dependencies=TEACHER_ONLY)
def add_end_hamza(q: EndHamzaQ):
    data = _read_games()
    data["end_hamza"].append(q.dict())
    _write_games(data)
    return {"ok": True}

@router.put("/games/end-hamza/{idx}", dependencies=TEACHER_ONLY)
def update_end_hamza(idx: int, q: EndHamzaQ):
    data = _read_games()
    if idx >= len(data["end_hamza"]): raise HTTPException(404, "غير موجود")
    data["end_hamza"][idx] = q.dict()
    _write_games(data)
    return {"ok": True}

@router.delete("/games/end-hamza/{idx}", dependencies=TEACHER_ONLY)
def delete_end_hamza(idx: int):
    data = _read_games()
    data["end_hamza"].pop(idx)
    _write_games(data)
    return {"ok": True}

# Quick Quiz
@router.post("/games/quick-quiz", dependencies=TEACHER_ONLY)
def add_quick_quiz(q: QuickQuizQ):
    data = _read_games()
    data["quick_quiz"].append(q.dict())
    _write_games(data)
    return {"ok": True}

@router.put("/games/quick-quiz/{idx}", dependencies=TEACHER_ONLY)
def update_quick_quiz(idx: int, q: QuickQuizQ):
    data = _read_games()
    if idx >= len(data["quick_quiz"]): raise HTTPException(404, "غير موجود")
    data["quick_quiz"][idx] = q.dict()
    _write_games(data)
    return {"ok": True}

@router.delete("/games/quick-quiz/{idx}", dependencies=TEACHER_ONLY)
def delete_quick_quiz(idx: int):
    data = _read_games()
    data["quick_quiz"].pop(idx)
    _write_games(data)
    return {"ok": True}


# ── Dictation Journey ──

DEFAULT_DICTATION = [
    {"word": "بِئْرٌ", "type": "الْهَمْزَةُ الْمُتَوَسِّطَةُ", "correct": "بِئْرٌ", "opts": ["بِيرٌ", "بِئْرٌ", "بِيئَرٌ", "بِئَرٌ"], "hint": "الْهَمْزَةُ عَلَى نَبْرَةٍ لِأَنَّ مَا قَبْلَهَا كَسْرَةٌ", "img": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600&q=80"},
    {"word": "فِئَةٌ", "type": "الْهَمْزَةُ الْمُتَوَسِّطَةُ", "correct": "فِئَةٌ", "opts": ["فِيئَةٌ", "فِأَةٌ", "فِئَةٌ", "فِاَةٌ"], "hint": "الْهَمْزَةُ عَلَى نَبْرَةٍ لِأَنَّ مَا قَبْلَهَا كَسْرَةٌ", "img": "https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=600&q=80"},
    {"word": "سُئِلَ", "type": "الْهَمْزَةُ الْمُتَوَسِّطَةُ", "correct": "سُئِلَ", "opts": ["سُءِلَ", "سُئِلَ", "سُوئِلَ", "سُيِلَ"], "hint": "الْهَمْزَةُ عَلَى نَبْرَةٍ لِأَنَّ مَا بَعْدَهَا كَسْرَةٌ", "img": "https://images.unsplash.com/photo-1488190211105-8b0e65b80b4e?w=600&q=80"},
    {"word": "يَسْأَلُ", "type": "الْهَمْزَةُ الْمُتَوَسِّطَةُ", "correct": "يَسْأَلُ", "opts": ["يَسْئَلُ", "يَسَالُ", "يَسْأَلُ", "يَسَألُ"], "hint": "الْهَمْزَةُ عَلَى أَلِفٍ لِأَنَّ مَا قَبْلَهَا سَاكِنٌ", "img": "https://images.unsplash.com/photo-1532153975070-2e9ab71f1b14?w=600&q=80"},
    {"word": "بَدْءٌ", "type": "الْهَمْزَةُ الْمُتَطَرِّفَةُ", "correct": "بَدْءٌ", "opts": ["بَدَأٌ", "بَدَاءٌ", "بَدْءٌ", "بَدِيءٌ"], "hint": "الْهَمْزَةُ عَلَى السَّطْرِ لِأَنَّ مَا قَبْلَهَا سَاكِنٌ", "img": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600&q=80"},
    {"word": "شَيْءٌ", "type": "الْهَمْزَةُ الْمُتَطَرِّفَةُ", "correct": "شَيْءٌ", "opts": ["شَيِئٌ", "شَيْءٌ", "شَيَاءٌ", "شَيَءٌ"], "hint": "الْهَمْزَةُ عَلَى السَّطْرِ لِأَنَّ مَا قَبْلَهَا سَاكِنٌ", "img": "https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=600&q=80"},
    {"word": "مَسَاءٌ", "type": "الْهَمْزَةُ الْمُتَطَرِّفَةُ", "correct": "مَسَاءٌ", "opts": ["مَسَاءً", "مَسَاؤُ", "مَسَاءٌ", "مَسَائٌ"], "hint": "الْهَمْزَةُ عَلَى السَّطْرِ لِأَنَّ مَا قَبْلَهَا أَلِفٌ", "img": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=600&q=80"},
    {"word": "هُدُوءٌ", "type": "الْهَمْزَةُ الْمُتَطَرِّفَةُ", "correct": "هُدُوءٌ", "opts": ["هُدُوُ", "هُدُوئٌ", "هُدُءٌ", "هُدُوءٌ"], "hint": "الْهَمْزَةُ عَلَى السَّطْرِ لِأَنَّ مَا قَبْلَهَا وَاوٌ سَاكِنَةٌ", "img": "https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=600&q=80"},
    {"word": "لُؤْلُؤٌ", "type": "الْهَمْزَةُ الْمُتَطَرِّفَةُ", "correct": "لُؤْلُؤٌ", "opts": ["لُولُوٌ", "لُؤْلُوٌ", "لُؤْلُؤٌ", "لُولُؤٌ"], "hint": "الْهَمْزَةُ عَلَى وَاوٍ لِأَنَّ مَا قَبْلَهَا ضَمَّةٌ", "img": "https://images.unsplash.com/photo-1515377905703-c4788e51af15?w=600&q=80"},
    {"word": "قَرَأَ", "type": "الْهَمْزَةُ الْمُتَطَرِّفَةُ", "correct": "قَرَأَ", "opts": ["قَرَاءَ", "قَرَءَ", "قَرَأَ", "قَرَئَ"], "hint": "الْهَمْزَةُ عَلَى أَلِفٍ لِأَنَّ مَا قَبْلَهَا فَتْحَةٌ", "img": "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=600&q=80"},
]


def _read_dictation() -> list:
    return content_store.get("dictation", lambda: DEFAULT_DICTATION)


def _write_dictation(data: list):
    content_store.put("dictation", data)


class DictationQuestion(BaseModel):
    word: str
    type: str
    correct: str
    opts: List[str]
    hint: str
    img: str = "https://images.unsplash.com/photo-1456513080510-7bf3a84b82f8?w=600&q=80"


@router.get("/dictation")
def get_dictation():
    return _read_dictation()

@router.post("/dictation", dependencies=TEACHER_ONLY)
def add_dictation(q: DictationQuestion):
    data = _read_dictation()
    data.append(q.dict())
    _write_dictation(data)
    return {"ok": True}

@router.put("/dictation/{idx}", dependencies=TEACHER_ONLY)
def update_dictation(idx: int, q: DictationQuestion):
    data = _read_dictation()
    if idx >= len(data): raise HTTPException(404, "غير موجود")
    data[idx] = q.dict()
    _write_dictation(data)
    return {"ok": True}

@router.delete("/dictation/{idx}", dependencies=TEACHER_ONLY)
def delete_dictation(idx: int):
    data = _read_dictation()
    data.pop(idx)
    _write_dictation(data)
    return {"ok": True}


# ── Hamza Games (WritingGames) ──

# ملف مرفق مع المشروع يحوي المحتوى الافتراضي الحقيقي لألعاب الهمزة: يُستخدم
# للبذر الأول فقط (قراءة فقط) — لا يُكتب عليه أبدًا؛ التعديلات تُحفَظ في القاعدة.
HAMZA_SEED_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "hamza_games.json")

DEFAULT_HAMZA = {
    "l1_gate":     [],
    "l1_cross":    [],
    "l1_fix":      [],
    "l2_river":    [],
    "l2_cross":    [],
    "l2_fill":     [],
    "l3_mountain": [],
    "l3_cross":    [],
}

VALID_KEYS = set(DEFAULT_HAMZA.keys())


def _read_hamza() -> dict:
    data = content_store.get("hamza_games", lambda: DEFAULT_HAMZA, seed_file=HAMZA_SEED_FILE)
    for k in VALID_KEYS:  # مفتاح ناقص لا يكسر الإضافة/التعديل
        data.setdefault(k, [])
    return data


def _write_hamza(data: dict):
    content_store.put("hamza_games", data)


@router.get("/hamza-games")
def get_hamza_games():
    return _read_hamza()


@router.post("/hamza-games/{key}", dependencies=TEACHER_ONLY)
def add_hamza_item(key: str, item: dict):
    if key not in VALID_KEYS:
        raise HTTPException(400, f"مفتاح غير صالح: {key}")
    data = _read_hamza()
    data[key].append(item)
    _write_hamza(data)
    return {"ok": True}


@router.put("/hamza-games/{key}/{idx}", dependencies=TEACHER_ONLY)
def update_hamza_item(key: str, idx: int, item: dict):
    if key not in VALID_KEYS:
        raise HTTPException(400, f"مفتاح غير صالح: {key}")
    data = _read_hamza()
    if idx >= len(data[key]):
        raise HTTPException(404, "العنصر غير موجود")
    data[key][idx] = item
    _write_hamza(data)
    return {"ok": True}


@router.delete("/hamza-games/{key}/{idx}", dependencies=TEACHER_ONLY)
def delete_hamza_item(key: str, idx: int):
    if key not in VALID_KEYS:
        raise HTTPException(400, f"مفتاح غير صالح: {key}")
    data = _read_hamza()
    if idx >= len(data[key]):
        raise HTTPException(404, "العنصر غير موجود")
    data[key].pop(idx)
    _write_hamza(data)
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════
# محتوى ألعاب الهمزة الحالية (الثلاث رحلات: رحلة المستكشف / الغواص
# وصائد اللآلئ / قائد المنطاد). يسمح للمعلم بتعديل الكلمات والخيارات
# والتعليلات وقاعدة كل رحلة، ويقرؤه الطالب مباشرة داخل صفحات الألعاب.
# محفوظ كـ JSON خام (بدون نموذج Pydantic صارم) لأن شكل الحقول يختلف
# بين الرحلات الثلاث (word pairs / نص مع صح-خطأ / إلخ).
# ══════════════════════════════════════════════════════════════════
DEFAULT_JOURNEYS = {
    "l1": {
        "rule": "تُكتب الهمزة المتوسطة على ياء إذا كانت مكسورة، أو كان الحرف الذي قبلها مكسورًا، أو سُبقت بياء ساكنة وكانت الهمزة مفتوحة أو مضمومة — لأن الكسرة أقوى الحركات.",
        "rock1Sets": [
            [{"label": "زَائِر", "correct": True}, {"label": "زَاءِر", "correct": False}],
            [{"label": "ذِئْب", "correct": True}, {"label": "ذِأْب", "correct": False}],
            [{"label": "مِئْذَنَة", "correct": True}, {"label": "مِأْذَنَة", "correct": False}],
        ],
        "rock1Explanations": [
            "حركة الهمزة في «زائر» كسرة، فتُكتب على ياء.",
            "الحرف الذي قبل الهمزة في «ذئب» (الذال) مكسور، فتُكتب على ياء.",
            "الحرف الذي قبل الهمزة في «مئذنة» (الميم) مكسور، فتُكتب على ياء.",
        ],
        "rock2Explanation": "الكسرة أقوى الحركات، تليها الضمة، ثم الفتحة، ثم السكون — وهذا الترتيب هو ما يحدد شكل الهمزة عند المقارنة بين حركتها وحركة ما قبلها.",
        "rock3Options": [
            {"text": "لأنَّ الْهَمْزَةَ سَاكِنَةٌ وَمَا قَبْلَهَا مَكْسُورٌ", "correct": False},
            {"text": "لأنَّ الْهَمْزَةَ مَكْسُورَةٌ وَمَا قَبْلَهَا مَفْتُوحٌ وَالْكَسْرَةُ أَقْوَى", "correct": True},
            {"text": "لأنَّ الْهَمْزَةَ مَفْتُوحَةٌ وَمَا قَبْلَهَا مَضْمُومٌ", "correct": False},
        ],
        "rock3Explanation": "همزة «مُطْمَئِن» مكسورة وما قبلها مفتوح، والكسرة أقوى من الفتحة، فكُتبت على ياء.",
        "rock4Options": [
            {"label": "بِئْرٍ", "correct": True},
            {"label": "بَأْرٍ", "correct": False},
            {"label": "بُؤْرٍ", "correct": False},
        ],
        "rock4Explanation": "الحرف الذي قبل الهمزة في «بئر» (الباء) مكسور، فتُكتب الهمزة على ياء: بِئْرٍ.",
    },
    "l2": {
        "rule": "تُكتب الهمزة المتوسطة منفردة على السطر إذا جاءت مفتوحة بعد ألف مدٍّ ساكنة، أو مفتوحة بعد واو مدٍّ ساكنة.",
        "oyster1Sets": [
            [{"label": "قِراءَة", "correct": True}, {"label": "قِراءية", "correct": False}],
            [{"label": "عَباءَة", "correct": True}, {"label": "عَبائة", "correct": False}],
            [{"label": "مُروءَة", "correct": True}, {"label": "مُروءةَ", "correct": False}],
        ],
        "oyster1Explanations": [
            "الهمزة في «قراءة» مفتوحة وسبقها ألف مد ساكنة، فتُكتب منفردة على السطر.",
            "الهمزة في «عباءة» مفتوحة وسبقها ألف مد ساكنة، فتُكتب منفردة على السطر.",
            "الهمزة في «مروءة» مفتوحة وسبقها واو مد ساكنة، فتُكتب منفردة على السطر.",
        ],
        "oyster2AlefOptions": [
            {"label": "سُكُون (مَدٌّ)", "correct": True},
            {"label": "فَتْحَة", "correct": False},
            {"label": "ضَمَّة", "correct": False},
        ],
        "oyster2HamzaOptions": [
            {"label": "ضَمَّة", "correct": False},
            {"label": "فَتْحَة", "correct": True},
            {"label": "كَسْرَة", "correct": False},
        ],
        "oyster2Explanation": "في «قراءة»: الألف قبل الهمزة ساكنة (حرف مد)، والهمزة نفسها مفتوحة — ولذلك كُتبت منفردة على السطر.",
        "oyster3Options": [
            {"text": "لأنَّ الْهَمْزَةَ مَكْسُورَةٌ بَعْدَ حَرْفٍ سَاكِنٍ", "correct": False},
            {"text": "لأنَّ الْهَمْزَةَ مَفْتُوحَةٌ وَجَاءَتْ بَعْدَ وَاوِ مَدٍّ سَاكِنَةٍ", "correct": True},
            {"text": "لأنَّ الْهَمْزَةَ مَضْمُومَةٌ بَعْدَ فَتْحٍ", "correct": False},
        ],
        "oyster3Explanation": "همزة «نبوءة» مفتوحة وجاءت بعد واو مد ساكنة، فتُكتب منفردة على السطر.",
        "oyster4Options": [
            {"label": "رَدَاءَه", "correct": False},
            {"label": "رَدَاءَة", "correct": True},
            {"label": "رَدَائِه", "correct": False},
        ],
        "oyster4Explanation": "الكلمة الصحيحة «رَدَاءَة»: الهمزة مفتوحة بعد ألف مد ساكنة، فتُكتب منفردة على السطر.",
    },
    "l3": {
        "rule": "تُكتب الهمزة المتطرفة بحسب حركة الحرف الذي يسبقها: على الألف إذا كان مفتوحًا، وعلى الواو إذا كان مضمومًا، وعلى الياء إذا كان مكسورًا، وعلى السطر إذا كان ساكنًا.",
        "cloud1Options": [
            {"text": "فِي أَوَّلِ الْكَلِمَةِ", "correct": False},
            {"text": "فِي وَسَطِ الْكَلِمَةِ", "correct": False},
            {"text": "فِي نِهَايَةِ الْكَلِمَةِ", "correct": True},
        ],
        "cloud1Explanation": "الهمزة المتطرفة هي الهمزة التي تقع دائمًا في آخر الكلمة، ومن هنا جاء اسمها «متطرفة».",
        "cloud2Options": [
            {"label": "فَتْحَة", "correct": False},
            {"label": "ضَمَّة", "correct": False},
            {"label": "كَسْرَة", "correct": True},
            {"label": "سُكُون", "correct": False},
        ],
        "cloud2Explanation": "حرف الطاء في «شاطئ» مكسور، ولذلك كُتبت الهمزة بعده على ياء.",
        "cloud3Options": [
            {"text": "لِأَنَّ الْحَرْفَ الَّذِي يَسْبِقُهَا مَضْمُومٌ، وَالضَّمَّةُ تُنَاسِبُهَا الْوَاوُ", "correct": True},
            {"text": "لِأَنَّ الْهَمْزَةَ نَفْسَهَا مَضْمُومَةٌ", "correct": False},
            {"text": "لِأَنَّ الْحَرْفَ الَّذِي يَسْبِقُهَا سَاكِنٌ", "correct": False},
        ],
        "cloud3Explanation": "الحرف الذي يسبق الهمزة في «يجرؤ» (الراء) مضموم، والضمة تناسبها الواو، فكُتبت الهمزة على واو.",
        "cloud4Options": [
            {"label": "دِفْء", "correct": True},
            {"label": "دَفُو", "correct": False},
            {"label": "دِفْئ", "correct": False},
        ],
        "cloud4Explanation": "الكلمة الصحيحة «دِفْء»: الحرف الذي يسبق الهمزة (الفاء) ساكن، فتُكتب الهمزة على السطر.",
    },
}


def _read_journeys() -> dict:
    data = content_store.get("hamza_journeys", lambda: DEFAULT_JOURNEYS)
    # دمج أي حقول ناقصة (مثلاً بعد تحديث الكود بحقول جديدة) مع الافتراضي
    for jid, defaults in DEFAULT_JOURNEYS.items():
        data.setdefault(jid, {})
        for k, v in defaults.items():
            data[jid].setdefault(k, copy.deepcopy(v))
    return data


def _write_journeys(data: dict):
    content_store.put("hamza_journeys", data)


@router.get("/hamza-journeys")
def get_hamza_journeys():
    return _read_journeys()


@router.put("/hamza-journeys/{journey_id}", dependencies=TEACHER_ONLY)
def update_hamza_journey(journey_id: str, data: dict):
    if journey_id not in DEFAULT_JOURNEYS:
        raise HTTPException(400, f"رحلة غير صالحة: {journey_id}")
    journeys = _read_journeys()
    journeys[journey_id].update(data)
    _write_journeys(journeys)
    return {"ok": True}


@router.put("/hamza-journeys/{journey_id}/reset", dependencies=TEACHER_ONLY)
def reset_hamza_journey(journey_id: str):
    if journey_id not in DEFAULT_JOURNEYS:
        raise HTTPException(400, f"رحلة غير صالحة: {journey_id}")
    journeys = _read_journeys()
    journeys[journey_id] = copy.deepcopy(DEFAULT_JOURNEYS[journey_id])
    _write_journeys(journeys)
    return {"ok": True}
