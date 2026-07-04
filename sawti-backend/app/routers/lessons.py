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
