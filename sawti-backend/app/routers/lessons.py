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
