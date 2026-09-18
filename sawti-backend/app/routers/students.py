"""
تخزين سجلّ كل طالب على الخادم (بدل الاعتماد فقط على localStorage في
المتصفح)، بحيث يستعيد الطالب تقدُّمه (النقاط، النجوم، الدروس المكتملة،
الشارات...) عند الدخول بنفس الاسم والصف من أي جهاز أو متصفح.

يُخزَّن كل شيء الآن في قاعدة بيانات Postgres دائمة (مثل Supabase) عبر
app/services/db.py، بدل ملف JSON على قرص خادم Render — الملف كان يُمحى
بالكامل مع كل عملية نشر جديدة (القرص المحلي هناك غير دائم)، وهذا كان
السبب الحقيقي في فقدان بيانات الطلاب بعد كل تحديث للكود.

إن لم يكن DATABASE_URL مضبوطًا بعد في متغيرات البيئة، يعمل هذا الملف على
التخزين القديم (ملف JSON) كحل احتياطي مؤقت فقط ريثما تُضبَط القاعدة، مع
تحذير واضح ومتكرر في السجلات — هذا الاحتياطي نفسه عرضة لنفس مشكلة فقدان
البيانات، فلا يجوز الاعتماد عليه طويلًا.

المفتاح المستخدم لكل طالب هو مزيج (الاسم + الصف) بعد تطبيع المسافات،
لتفادي تعارض الأسماء المتكررة بين شعب مختلفة.
"""
import os
import re
import json
import logging
from fastapi import APIRouter, HTTPException, Depends
from app.services import db
from app.services.current_user import get_current_user_id

router = APIRouter()
logger = logging.getLogger("sawti.students")

_CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS students (
        key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        grade TEXT NOT NULL,
        data JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""

# ── احتياطي مؤقت (ملف JSON) — يُستخدَم فقط إن لم تُضبَط DATABASE_URL بعد ──
STUDENTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "students.json")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _key(name: str, grade: str) -> str:
    return f"{_normalize(name)}|{_normalize(grade)}"


def _read_all_file() -> dict:
    os.makedirs(os.path.dirname(STUDENTS_FILE), exist_ok=True)
    if not os.path.exists(STUDENTS_FILE):
        return {}
    with open(STUDENTS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _write_all_file(data: dict):
    os.makedirs(os.path.dirname(STUDENTS_FILE), exist_ok=True)
    with open(STUDENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _warn_temp_storage():
    logger.warning("Students: DATABASE_URL غير مضبوط — يُستخدَم تخزين مؤقت (ملف JSON) "
                    "لن يبقى بعد أي عملية نشر جديدة على Render")


@router.get("")
def list_students():
    """
    قائمة كل الطلاب المحفوظين (لاستخدامها في لوحة المعلم). كل عنصر يحمل
    أيضًا "_key" — المفتاح الحقيقي لصفّه في قاعدة البيانات (قد يكون
    user_id لحساب جديد، أو "الاسم|الصف" لسجل قديم قبل ميزة الحسابات) —
    ليستخدمه المعلم عند تعديل سجل الطالب بدل إعادة بناء مفتاح جديد قد
    لا يطابق السجل الفعلي.
    """
    if db.is_configured():
        db.ensure_table("students", _CREATE_TABLE_SQL)
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT key, data FROM students ORDER BY updated_at DESC")
                return [{**row[1], "_key": row[0]} for row in cur.fetchall()]
        finally:
            conn.close()

    _warn_temp_storage()
    return [{**v, "_key": k} for k, v in _read_all_file().items()]

    _warn_temp_storage()
    return list(_read_all_file().values())


@router.get("/me")
def get_my_record(user_id: str = Depends(get_current_user_id)):
    """سجل تقدّم الطالب صاحب الحساب الحالي (بحسب رمز الجلسة)."""
    if db.is_configured():
        db.ensure_table("students", _CREATE_TABLE_SQL)
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM students WHERE key = %s", (user_id,))
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            # حساب جديد بلا نشاط بعد — ليس خطأً، فقط لا يوجد شيء لاسترجاعه
            return None
        return row[0]

    raise HTTPException(503, "خدمة الحسابات تتطلب قاعدة بيانات مضبوطة")


@router.put("/me")
def save_my_record(data: dict, user_id: str = Depends(get_current_user_id)):
    """يحفظ تقدّم الطالب صاحب الحساب الحالي تلقائيًا (بدون زر حفظ)."""
    if not db.is_configured():
        raise HTTPException(503, "خدمة الحسابات تتطلب قاعدة بيانات مضبوطة")

    db.ensure_table("students", _CREATE_TABLE_SQL)
    data = dict(data)
    name = _normalize(data.get("name", ""))
    grade = _normalize(data.get("grade", ""))
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO students (key, name, grade, data, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (key) DO UPDATE
                SET data = EXCLUDED.data, name = EXCLUDED.name,
                    grade = EXCLUDED.grade, updated_at = now()
                """,
                (user_id, name, grade, json.dumps(data, ensure_ascii=False)),
            )
        conn.commit()
        return {"ok": True}
    finally:
        conn.close()


@router.put("/by-key")
def save_by_key(payload: dict):
    """
    يحدّث سجل طالب بعينه عبر مفتاحه الحقيقي في قاعدة البيانات مباشرةً
    (كما تُرجعه list_students في حقل "_key")، بدل إعادة بنائه من
    الاسم والصف — وهو ما قد لا يطابق سجل حساب حديث مفتاحه user_id.
    تستخدمه لوحة المعلم عند حفظ ملاحظة على طالب.
    """
    key = str(payload.get("key", "")).strip()
    data = payload.get("data")
    if not key or not isinstance(data, dict):
        raise HTTPException(400, "بيانات ناقصة: يلزم key و data")

    name = _normalize(data.get("name", ""))
    grade = _normalize(data.get("grade", ""))

    if db.is_configured():
        db.ensure_table("students", _CREATE_TABLE_SQL)
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE students SET data = %s, name = %s, grade = %s, updated_at = now() WHERE key = %s",
                    (json.dumps(data, ensure_ascii=False), name, grade, key),
                )
                if cur.rowcount == 0:
                    raise HTTPException(404, "لم يُعثَر على سجل بهذا المفتاح")
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    _warn_temp_storage()
    students = _read_all_file()
    if key not in students:
        raise HTTPException(404, "لم يُعثَر على سجل بهذا المفتاح")
    students[key] = data
    _write_all_file(students)
    return {"ok": True}


@router.get("/{name}/{grade}")
def get_student(name: str, grade: str):
    key = _key(name, grade)

    if db.is_configured():
        db.ensure_table("students", _CREATE_TABLE_SQL)
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM students WHERE key = %s", (key,))
                row = cur.fetchone()
        finally:
            conn.close()
        if not row:
            raise HTTPException(404, "لا يوجد سجل محفوظ لهذا الطالب بعد")
        return row[0]

    _warn_temp_storage()
    record = _read_all_file().get(key)
    if not record:
        raise HTTPException(404, "لا يوجد سجل محفوظ لهذا الطالب بعد")
    return record


@router.put("/{name}/{grade}")
def save_student(name: str, grade: str, data: dict):
    key = _key(name, grade)
    data = dict(data)
    data["name"] = _normalize(name)
    data["grade"] = _normalize(grade)

    if db.is_configured():
        db.ensure_table("students", _CREATE_TABLE_SQL)
        conn = db.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO students (key, name, grade, data, updated_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (key) DO UPDATE
                    SET data = EXCLUDED.data, name = EXCLUDED.name,
                        grade = EXCLUDED.grade, updated_at = now()
                    """,
                    (key, data["name"], data["grade"], json.dumps(data, ensure_ascii=False)),
                )
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    _warn_temp_storage()
    students = _read_all_file()
    students[key] = data
    _write_all_file(students)
    return {"ok": True}
