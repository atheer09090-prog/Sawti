"""
إدارة الدروس والمواضيع — يحفظ في ملف JSON على السيرفر
"""
import json
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "lessons.json")

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
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    if not os.path.exists(DATA_FILE):
        _write(DEFAULT_DATA)
        return DEFAULT_DATA
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write(data: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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

@router.post("/speaking")
def add_speaking_lesson(lesson: SpeakingLesson):
    data = _read()
    # تحقق من عدم تكرار الـ id
    if any(l["id"] == lesson.id for l in data["speaking"]):
        raise HTTPException(400, "معرّف الدرس موجود مسبقاً")
    data["speaking"].append(lesson.dict())
    _write(data)
    return {"ok": True}

@router.post("/writing")
def add_writing_topic(topic: WritingTopic):
    data = _read()
    if any(t["id"] == topic.id for t in data["writing"]):
        raise HTTPException(400, "معرّف الموضوع موجود مسبقاً")
    data["writing"].append(topic.dict())
    _write(data)
    return {"ok": True}

@router.put("/speaking/{lesson_id}")
def update_speaking_lesson(lesson_id: str, lesson: SpeakingLesson):
    data = _read()
    for i, l in enumerate(data["speaking"]):
        if l["id"] == lesson_id:
            data["speaking"][i] = lesson.dict()
            _write(data)
            return {"ok": True}
    raise HTTPException(404, "الدرس غير موجود")

@router.put("/writing/{topic_id}")
def update_writing_topic(topic_id: str, topic: WritingTopic):
    data = _read()
    for i, t in enumerate(data["writing"]):
        if t["id"] == topic_id:
            data["writing"][i] = topic.dict()
            _write(data)
            return {"ok": True}
    raise HTTPException(404, "الموضوع غير موجود")

@router.delete("/speaking/{lesson_id}")
def delete_speaking_lesson(lesson_id: str):
    data = _read()
    data["speaking"] = [l for l in data["speaking"] if l["id"] != lesson_id]
    _write(data)
    return {"ok": True}

@router.delete("/writing/{topic_id}")
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

SL_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "self_learning.json")

def _read_sl() -> dict:
    os.makedirs(os.path.dirname(SL_FILE), exist_ok=True)
    if not os.path.exists(SL_FILE):
        _write_sl(DEFAULT_SELF_LEARNING)
        return DEFAULT_SELF_LEARNING
    with open(SL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _write_sl(data: dict):
    os.makedirs(os.path.dirname(SL_FILE), exist_ok=True)
    with open(SL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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

@router.post("/self-learning/quiz")
def add_quiz_question(q: QuizQuestion):
    data = _read_sl()
    data["quiz"].append(q.dict())
    _write_sl(data)
    return {"ok": True}

@router.put("/self-learning/quiz/{idx}")
def update_quiz_question(idx: int, q: QuizQuestion):
    data = _read_sl()
    if idx >= len(data["quiz"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["quiz"][idx] = q.dict()
    _write_sl(data)
    return {"ok": True}

@router.delete("/self-learning/quiz/{idx}")
def delete_quiz_question(idx: int):
    data = _read_sl()
    if idx >= len(data["quiz"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["quiz"].pop(idx)
    _write_sl(data)
    return {"ok": True}

@router.post("/self-learning/word-order")
def add_word_order(q: WordOrderQuestion):
    data = _read_sl()
    data["word_order"].append(q.dict())
    _write_sl(data)
    return {"ok": True}

@router.put("/self-learning/word-order/{idx}")
def update_word_order(idx: int, q: WordOrderQuestion):
    data = _read_sl()
    if idx >= len(data["word_order"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["word_order"][idx] = q.dict()
    _write_sl(data)
    return {"ok": True}

@router.delete("/self-learning/word-order/{idx}")
def delete_word_order(idx: int):
    data = _read_sl()
    if idx >= len(data["word_order"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["word_order"].pop(idx)
    _write_sl(data)
    return {"ok": True}

@router.post("/self-learning/fill-in")
def add_fill_in(q: FillInQuestion):
    data = _read_sl()
    data["fill_in"].append(q.dict())
    _write_sl(data)
    return {"ok": True}

@router.put("/self-learning/fill-in/{idx}")
def update_fill_in(idx: int, q: FillInQuestion):
    data = _read_sl()
    if idx >= len(data["fill_in"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["fill_in"][idx] = q.dict()
    _write_sl(data)
    return {"ok": True}

@router.delete("/self-learning/fill-in/{idx}")
def delete_fill_in(idx: int):
    data = _read_sl()
    if idx >= len(data["fill_in"]):
        raise HTTPException(404, "السؤال غير موجود")
    data["fill_in"].pop(idx)
    _write_sl(data)
    return {"ok": True}


# ── Writing Games ──

GAMES_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "writing_games.json")

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
    os.makedirs(os.path.dirname(GAMES_FILE), exist_ok=True)
    if not os.path.exists(GAMES_FILE):
        _write_games(DEFAULT_GAMES)
        return DEFAULT_GAMES
    with open(GAMES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_games(data: dict):
    os.makedirs(os.path.dirname(GAMES_FILE), exist_ok=True)
    with open(GAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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
@router.post("/games/middle-hamza")
def add_middle_hamza(q: MiddleHamzaQ):
    data = _read_games()
    data["middle_hamza"].append(q.dict())
    _write_games(data)
    return {"ok": True}

@router.put("/games/middle-hamza/{idx}")
def update_middle_hamza(idx: int, q: MiddleHamzaQ):
    data = _read_games()
    if idx >= len(data["middle_hamza"]): raise HTTPException(404, "غير موجود")
    data["middle_hamza"][idx] = q.dict()
    _write_games(data)
    return {"ok": True}

@router.delete("/games/middle-hamza/{idx}")
def delete_middle_hamza(idx: int):
    data = _read_games()
    data["middle_hamza"].pop(idx)
    _write_games(data)
    return {"ok": True}

# End Hamza
@router.post("/games/end-hamza")
def add_end_hamza(q: EndHamzaQ):
    data = _read_games()
    data["end_hamza"].append(q.dict())
    _write_games(data)
    return {"ok": True}

@router.put("/games/end-hamza/{idx}")
def update_end_hamza(idx: int, q: EndHamzaQ):
    data = _read_games()
    if idx >= len(data["end_hamza"]): raise HTTPException(404, "غير موجود")
    data["end_hamza"][idx] = q.dict()
    _write_games(data)
    return {"ok": True}

@router.delete("/games/end-hamza/{idx}")
def delete_end_hamza(idx: int):
    data = _read_games()
    data["end_hamza"].pop(idx)
    _write_games(data)
    return {"ok": True}

# Quick Quiz
@router.post("/games/quick-quiz")
def add_quick_quiz(q: QuickQuizQ):
    data = _read_games()
    data["quick_quiz"].append(q.dict())
    _write_games(data)
    return {"ok": True}

@router.put("/games/quick-quiz/{idx}")
def update_quick_quiz(idx: int, q: QuickQuizQ):
    data = _read_games()
    if idx >= len(data["quick_quiz"]): raise HTTPException(404, "غير موجود")
    data["quick_quiz"][idx] = q.dict()
    _write_games(data)
    return {"ok": True}

@router.delete("/games/quick-quiz/{idx}")
def delete_quick_quiz(idx: int):
    data = _read_games()
    data["quick_quiz"].pop(idx)
    _write_games(data)
    return {"ok": True}


# ── Dictation Journey ──

DICTATION_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "dictation.json")

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
    os.makedirs(os.path.dirname(DICTATION_FILE), exist_ok=True)
    if not os.path.exists(DICTATION_FILE):
        _write_dictation(DEFAULT_DICTATION)
        return DEFAULT_DICTATION
    with open(DICTATION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_dictation(data: list):
    os.makedirs(os.path.dirname(DICTATION_FILE), exist_ok=True)
    with open(DICTATION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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

@router.post("/dictation")
def add_dictation(q: DictationQuestion):
    data = _read_dictation()
    data.append(q.dict())
    _write_dictation(data)
    return {"ok": True}

@router.put("/dictation/{idx}")
def update_dictation(idx: int, q: DictationQuestion):
    data = _read_dictation()
    if idx >= len(data): raise HTTPException(404, "غير موجود")
    data[idx] = q.dict()
    _write_dictation(data)
    return {"ok": True}

@router.delete("/dictation/{idx}")
def delete_dictation(idx: int):
    data = _read_dictation()
    data.pop(idx)
    _write_dictation(data)
    return {"ok": True}


# ── Hamza Games (WritingGames) ──

HAMZA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "hamza_games.json")

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
    os.makedirs(os.path.dirname(HAMZA_FILE), exist_ok=True)
    if not os.path.exists(HAMZA_FILE):
        _write_hamza(DEFAULT_HAMZA)
        return DEFAULT_HAMZA
    with open(HAMZA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_hamza(data: dict):
    os.makedirs(os.path.dirname(HAMZA_FILE), exist_ok=True)
    with open(HAMZA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@router.get("/hamza-games")
def get_hamza_games():
    return _read_hamza()


@router.post("/hamza-games/{key}")
def add_hamza_item(key: str, item: dict):
    if key not in VALID_KEYS:
        raise HTTPException(400, f"مفتاح غير صالح: {key}")
    data = _read_hamza()
    data[key].append(item)
    _write_hamza(data)
    return {"ok": True}


@router.put("/hamza-games/{key}/{idx}")
def update_hamza_item(key: str, idx: int, item: dict):
    if key not in VALID_KEYS:
        raise HTTPException(400, f"مفتاح غير صالح: {key}")
    data = _read_hamza()
    if idx >= len(data[key]):
        raise HTTPException(404, "العنصر غير موجود")
    data[key][idx] = item
    _write_hamza(data)
    return {"ok": True}


@router.delete("/hamza-games/{key}/{idx}")
def delete_hamza_item(key: str, idx: int):
    if key not in VALID_KEYS:
        raise HTTPException(400, f"مفتاح غير صالح: {key}")
    data = _read_hamza()
    if idx >= len(data[key]):
        raise HTTPException(404, "العنصر غير موجود")
    data[key].pop(idx)
    _write_hamza(data)
    return {"ok": True}
