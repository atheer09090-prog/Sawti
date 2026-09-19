"""
أداة تقييم علمية لتجربة استخدام المنصة: مقياس System Usability Scale (SUS)
— أحد أكثر أدوات قياس قابلية الاستخدام اعتمادًا أكاديميًا (Brooke, 1996)،
اختير هنا (بدل اختراع مقياس جديد) لأنه:
  • مقياس موحّد ومختصر (10 عبارات فقط) لا يُرهق الطالب.
  • له طريقة حساب معيارية وموثّقة (Sauro & Lewis)، فتكون النتيجة قابلة
    للمقارنة بأبحاث أخرى ومناسبة للاستشهاد بها في فصل Evaluation بالبحث.
  • يقيس فعليًا أغلب المحاور التي طلبتَ تغطيتها (سهولة الاستخدام،
    التعلّم، الاتساق، الثقة أثناء الاستخدام) ضمن أداة واحدة محكّمة، بدل
    تجميع عشرة معايير منفصلة غير مرتبطة ببعضها إحصائيًا.

طريقة الحساب (المعيار الرسمي):
  - العبارات الفردية (1,3,5,7,9) إيجابية الصياغة: النتيجة = الإجابة - 1
  - العبارات الزوجية (2,4,6,8,10) سلبية الصياغة: النتيجة = 5 - الإجابة
  - المجموع (0-40) × 2.5 = درجة SUS النهائية من 100

كل حساب طالب له إجابة واحدة محفوظة (تُحدَّث إن أعاد التقييم بدل إنشاء
سجل جديد في كل مرة) لمنع التكرار غير المقصود، مع الاحتفاظ بتاريخ آخر
تحديث — وهذا "التعامل المنطقي" المطلوب مع إعادة التقييم.
"""
import os
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator

from app.services import db
from app.services.current_user import get_current_user_id

router = APIRouter()
logger = logging.getLogger("sawti.sus")

_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS sus_responses (
        user_id TEXT PRIMARY KEY,
        student_name TEXT,
        grade TEXT,
        answers JSONB NOT NULL,
        sus_score REAL NOT NULL,
        comment TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""

# ── احتياطي مؤقت (ملف JSON) لبيئة التطوير المحلي بلا قاعدة بيانات ──
_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "sus_responses.json")


def _read_file() -> dict:
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    if not os.path.exists(_FILE):
        return {}
    with open(_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _write_file(data: dict):
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class SusPayload(BaseModel):
    answers: list[int]
    comment: str = ""

    @field_validator("answers")
    @classmethod
    def _validate_answers(cls, v: list[int]) -> list[int]:
        if len(v) != 10:
            raise ValueError("يجب الإجابة على العبارات العشر جميعها")
        if any(a < 1 or a > 5 for a in v):
            raise ValueError("كل إجابة يجب أن تكون بين 1 و5")
        return v


def compute_sus_score(answers: list[int]) -> float:
    """answers[i] بترقيم يبدأ من صفر يقابل العبارة رقم i+1، على مقياس 1-5
    حيث 1 = لا أوافق بشدة و5 = أوافق بشدة (الاتجاه المعياري الرسمي لـ SUS)."""
    total = 0
    for idx, ans in enumerate(answers):
        position = idx + 1
        if position % 2 == 1:  # عبارة فردية (إيجابية الصياغة)
            total += ans - 1
        else:  # عبارة زوجية (سلبية الصياغة)
            total += 5 - ans
    return round(total * 2.5, 1)


def score_band(score: float) -> dict:
    if score < 50:
        return {"key": "poor", "label": "يحتاج إلى تحسين", "color": "#dc2626"}
    if score < 70:
        return {"key": "ok", "label": "مقبول / متوسط", "color": "#f59e0b"}
    return {"key": "good", "label": "جيد إلى ممتاز", "color": "#16a34a"}


@router.post("")
def submit_sus(payload: SusPayload, user_id: str = Depends(get_current_user_id)):
    score = compute_sus_score(payload.answers)
    now = datetime.now(timezone.utc).isoformat()

    if db.is_configured():
        db.ensure_table("sus_responses", _CREATE_TABLE_SQL)
        # نجلب اسم/صف الطالب من جدول المستخدمين لإثراء بيانات التصدير البحثي
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT name, grade FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
                name, grade = (row[0], row[1]) if row else (None, None)
                cur.execute(
                    """
                    INSERT INTO sus_responses (user_id, student_name, grade, answers, sus_score, comment, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (user_id) DO UPDATE
                    SET answers = EXCLUDED.answers, sus_score = EXCLUDED.sus_score,
                        comment = EXCLUDED.comment, student_name = EXCLUDED.student_name,
                        grade = EXCLUDED.grade, updated_at = now()
                    """,
                    (user_id, name, grade, json.dumps(payload.answers), score, payload.comment.strip()),
                )
            conn.commit()
        finally:
            conn.close()
    else:
        logger.warning("SUS: DATABASE_URL غير مضبوط — يُستخدَم تخزين مؤقت (ملف JSON)")
        data = _read_file()
        existing = data.get(user_id, {})
        data[user_id] = {
            "student_name": existing.get("student_name"), "grade": existing.get("grade"),
            "answers": payload.answers, "sus_score": score, "comment": payload.comment.strip(),
            "created_at": existing.get("created_at", now), "updated_at": now,
        }
        _write_file(data)

    return {"ok": True, "score": score, "band": score_band(score)}


@router.get("/me")
def get_my_sus(user_id: str = Depends(get_current_user_id)):
    """يخبر الواجهة إن كان الطالب قيَّم من قبل، لعرض نتيجته أو دعوته للتحديث بدل تكرار العرض بلا داعٍ."""
    if db.is_configured():
        db.ensure_table("sus_responses", _CREATE_TABLE_SQL)
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT sus_score, updated_at FROM sus_responses WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return {"score": row[0], "band": score_band(row[0]), "updated_at": row[1].isoformat()}

    data = _read_file().get(user_id)
    if not data:
        return None
    return {"score": data["sus_score"], "band": score_band(data["sus_score"]), "updated_at": data["updated_at"]}


@router.get("/export")
def export_sus():
    """
    كل إجابات الاستبيان مفصّلة (لكل طالب إجاباته العشر + درجته) لأغراض
    التحليل الإحصائي اللاحق في فصل Evaluation بالبحث. يستخدمها المعلم/
    الباحث لتصدير البيانات (مثلًا نسخها إلى Excel/SPSS).
    """
    if db.is_configured():
        db.ensure_table("sus_responses", _CREATE_TABLE_SQL)
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id, student_name, grade, answers, sus_score, comment, created_at, updated_at "
                    "FROM sus_responses ORDER BY updated_at DESC"
                )
                cols = ["user_id", "student_name", "grade", "answers", "sus_score", "comment", "created_at", "updated_at"]
                return [
                    {**dict(zip(cols, row)),
                     "created_at": row[6].isoformat(), "updated_at": row[7].isoformat()}
                    for row in cur.fetchall()
                ]
        finally:
            conn.close()

    return [{"user_id": k, **v} for k, v in _read_file().items()]


@router.get("/report")
def sus_report():
    """تقرير PDF مرئي (رسوم بيانية) لنتائج استبيان SUS، لاستخدام المعلم/الباحث."""
    from fastapi.responses import Response
    from app.services.pdf_gen import generate_sus_report

    rows = export_sus()
    summary = sus_summary()
    pdf_bytes = generate_sus_report(rows, summary)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=sus_report.pdf"},
    )


@router.get("/summary")
def sus_summary():
    """ملخص سريع (للوحة المعلم): عدد المشاركين، متوسط الدرجة، وتوزيعهم على التصنيفات الثلاثة."""
    rows = export_sus()
    if not rows:
        return {"count": 0, "average": None, "bands": {"poor": 0, "ok": 0, "good": 0}}

    scores = [r["sus_score"] for r in rows]
    bands = {"poor": 0, "ok": 0, "good": 0}
    for s in scores:
        bands[score_band(s)["key"]] += 1

    return {
        "count": len(scores),
        "average": round(sum(scores) / len(scores), 1),
        "bands": bands,
    }
