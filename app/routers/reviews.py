"""
تقييمات الطلاب لتجربة استخدام المنصة (وليس تقييمات الدروس). يُقدّمها
الطالب اختياريًا عبر زر "⭐ قيّم المنصة" في صفحته الرئيسية، ويراها
المعلم في تبويب "التقييمات" بلوحة التحكم. محفوظة كملف JSON على القرص
بنفس نمط بقية الملفات في هذا المشروع (لا قاعدة بيانات).
"""
import os
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException

router = APIRouter()

REVIEWS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "reviews.json")


def _read_reviews() -> list:
    os.makedirs(os.path.dirname(REVIEWS_FILE), exist_ok=True)
    if not os.path.exists(REVIEWS_FILE):
        return []
    with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _write_reviews(data: list):
    os.makedirs(os.path.dirname(REVIEWS_FILE), exist_ok=True)
    with open(REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@router.get("")
def list_reviews():
    return _read_reviews()


@router.post("")
def add_review(review: dict):
    try:
        quality = int(review.get("quality", 0))
        ease = int(review.get("ease", 0))
        benefit = int(review.get("benefit", 0))
    except (TypeError, ValueError):
        raise HTTPException(400, "التقييمات يجب أن تكون أرقامًا")

    if not (1 <= quality <= 5 and 1 <= ease <= 5 and 1 <= benefit <= 5):
        raise HTTPException(400, "التقييمات يجب أن تكون بين 1 و5")

    data = _read_reviews()
    data.append({
        "id": (data[-1]["id"] + 1) if data else 1,
        "student": str(review.get("student", "")).strip() or "طَالِبٌ",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "quality": quality,
        "ease": ease,
        "benefit": benefit,
        "comment": str(review.get("comment", "")).strip(),
    })
    _write_reviews(data)
    return {"ok": True}
