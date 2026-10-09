"""
تقييمات الطلاب القديمة لتجربة استخدام المنصة (النجوم 1-5). يُقدّمها الطالب
المسجَّل، ويراها المعلم فقط في تبويب "التقييمات" بلوحة التحكم.

تُحفَظ في PostgreSQL ضمن جدول content_store (المفتاح reviews) مثل بقية محتوى
المعلم، فلا تضيع عند إعادة نشر Render. (استبيان SUS هو التقييم الحالي في الواجهة.)
"""
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from app.services.current_user import get_current_user_id, require_teacher
from app.services import content_store
from app.services.write_lock import serialize_writes

router = APIRouter()

MAX_REVIEWS = 5000      # سقف أمان: لا ينمو الجدول بلا حدّ
MAX_COMMENT_CHARS = 1000


def _read_reviews() -> list:
    return content_store.get("reviews", lambda: [])


@router.get("", dependencies=[Depends(require_teacher)])
def list_reviews():
    return _read_reviews()


@router.post("", dependencies=[Depends(serialize_writes)])
def add_review(review: dict, user_id: str = Depends(get_current_user_id)):
    try:
        quality = int(review.get("quality", 0))
        ease = int(review.get("ease", 0))
        benefit = int(review.get("benefit", 0))
    except (TypeError, ValueError):
        raise HTTPException(400, "التقييمات يجب أن تكون أرقامًا")

    if not (1 <= quality <= 5 and 1 <= ease <= 5 and 1 <= benefit <= 5):
        raise HTTPException(400, "التقييمات يجب أن تكون بين 1 و5")

    comment = str(review.get("comment", "")).strip()
    if len(comment) > MAX_COMMENT_CHARS:
        raise HTTPException(413, f"التعليق أطول من المسموح ({MAX_COMMENT_CHARS} حرف)")

    data = _read_reviews()
    if len(data) >= MAX_REVIEWS:
        raise HTTPException(503, "تعذّر حفظ التقييم الآن")
    data.append({
        "id": (data[-1]["id"] + 1) if data else 1,
        "student": str(review.get("student", "")).strip()[:100] or "طَالِبٌ",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "quality": quality,
        "ease": ease,
        "benefit": benefit,
        "comment": comment,
    })
    content_store.put("reviews", data)
    return {"ok": True}
