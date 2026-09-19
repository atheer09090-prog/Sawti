"""
مصادقة المنصة، وفيها نوعان مختلفان تمامًا من الدخول:

1) دخول المعلم: رمز وصول واحد مشترك (كما كان)، بدون حساب فردي.
2) حسابات الطلاب: تسجيل/دخول حقيقي بالبريد وكلمة المرور، لكل طالب حساب
   خاص به (User ID + بريد + كلمة مرور مُجزَّأة)، حتى يستعيد بياناته من
   أي جهاز بعد تسجيل الدخول، بدل الاعتماد فقط على تخمين الاسم والصف.

هوية الطالب في جدول "students" (app/routers/students.py) أصبحت الآن
مبنية على user_id بدل الاسم+الصف. جدول "students" نفسه لم يتغيّر
(العمود key TEXT ما زال كما هو) — فقط القيمة التي تُخزَّن فيه الآن هي
user_id، ما يبقي هذا الترحيل بسيطًا وآمنًا دون تعديل بنية الجداول.
"""
import os
import re
import uuid
import json
import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, field_validator

from app.services import db
from app.services.security import hash_password, verify_password, create_token
from app.services.current_user import get_current_user_id

router = APIRouter()
logger = logging.getLogger("sawti.auth")

TEACHER_ACCESS_CODE = os.getenv("TEACHER_ACCESS_CODE", "sawti2026")

_CREATE_USERS_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        grade TEXT NOT NULL,
        avatar TEXT NOT NULL DEFAULT 'boy1',
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
"""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class RegisterPayload(BaseModel):
    name: str
    grade: str
    avatar: str = "boy1"
    email: EmailStr
    password: str
    legacy_name: str | None = None
    legacy_grade: str | None = None

    @field_validator("password")
    @classmethod
    def _password_len(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("كلمة المرور يجب ألا تقل عن 6 أحرف")
        return v

    @field_validator("name", "grade")
    @classmethod
    def _not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("هذا الحقل مطلوب")
        return v


class LoginPayload(BaseModel):
    email: EmailStr
    password: str


def _require_db():
    if not db.is_configured():
        raise HTTPException(503, "خدمة الحسابات غير متاحة حاليًا، يرجى المحاولة لاحقًا")


@router.post("/teacher-login")
def teacher_login(payload: dict):
    code = str(payload.get("code", "")).strip()
    if not code or code != TEACHER_ACCESS_CODE:
        raise HTTPException(401, "رمز الدخول غير صحيح")
    return {"ok": True}


@router.post("/register")
def register(payload: RegisterPayload):
    """إنشاء حساب طالب جديد. يرجع رمز جلسة (token) فور النجاح."""
    _require_db()
    db.ensure_table("users", _CREATE_USERS_TABLE_SQL)

    email = _normalize_email(payload.email)
    user_id = str(uuid.uuid4())
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                raise HTTPException(409, "هذا البريد الإلكتروني مُسجَّل مسبقًا. جرّب تسجيل الدخول بدلًا من ذلك.")

            cur.execute(
                """
                INSERT INTO users (id, name, grade, avatar, email, password_hash, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
                """,
                (user_id, _normalize(payload.name), _normalize(payload.grade),
                 payload.avatar, email, hash_password(payload.password)),
            )
        conn.commit()
    except HTTPException:
        raise
    except Exception:
        logger.exception("Auth: register failed")
        raise HTTPException(500, "تعذّر إنشاء الحساب، حاول مرة أخرى")
    finally:
        conn.close()

    migrated_data = None
    if payload.legacy_name and payload.legacy_grade:
        migrated_data = _try_migrate_legacy_record(
            user_id, payload.legacy_name, payload.legacy_grade,
            payload.name, payload.grade, payload.avatar,
        )

    token = create_token(user_id)
    return {
        "ok": True,
        "token": token,
        "user": {"id": user_id, "name": payload.name, "grade": payload.grade, "avatar": payload.avatar, "email": email},
        "migrated": migrated_data is not None,
    }


@router.post("/login")
def login(payload: LoginPayload):
    _require_db()
    db.ensure_table("users", _CREATE_USERS_TABLE_SQL)
    email = _normalize_email(payload.email)

    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, grade, avatar, password_hash FROM users WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        # 404 (لا 401) لأن السبب هنا مختلف تمامًا: لا يوجد حساب أصلًا،
        # وليس أن كلمة المرور خاطئة — الواجهة تستخدم هذا الفرق لتوجيه
        # الطالب مباشرة لإنشاء حساب جديد بدل تكرار محاولة الدخول.
        raise HTTPException(404, "لا يوجد حساب بهذا البريد الإلكتروني")
    if not verify_password(payload.password, row[4]):
        raise HTTPException(401, "كلمة المرور غير صحيحة")

    user_id, name, grade, avatar, _ = row
    token = create_token(user_id)
    return {"ok": True, "token": token, "user": {"id": user_id, "name": name, "grade": grade, "avatar": avatar, "email": email}}


@router.get("/me")
def me(user_id: str = Depends(get_current_user_id)):
    _require_db()
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, grade, avatar, email FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "الحساب غير موجود")
    return {"id": row[0], "name": row[1], "grade": row[2], "avatar": row[3], "email": row[4]}


def _try_migrate_legacy_record(user_id, legacy_name, legacy_grade, name, grade, avatar):
    """
    ينسخ سجل تقدّم قديم (محفوظ سابقًا بمفتاح الاسم+الصف قبل وجود
    الحسابات) إلى سجل الحساب الجديد (بمفتاح user_id)، حتى لا يفقد
    الطالب نقاطه وشاراته السابقة عند إنشاء حساب لأول مرة. لا يفشل
    التسجيل إن لم يوجد سجل قديم مطابق أو حدث أي خطأ هنا.
    """
    from app.routers import students as students_router
    try:
        legacy_key = students_router._key(legacy_name, legacy_grade)
        conn = db.get_conn()
        try:
            db.ensure_table("students", students_router._CREATE_TABLE_SQL)
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM students WHERE key = %s", (legacy_key,))
                row = cur.fetchone()
                if not row:
                    return None
                data = dict(row[0])
                data["name"] = _normalize(name)
                data["grade"] = _normalize(grade)
                data["avatar"] = avatar
                cur.execute(
                    """
                    INSERT INTO students (key, name, grade, data, updated_at)
                    VALUES (%s, %s, %s, %s, now())
                    ON CONFLICT (key) DO UPDATE
                    SET data = EXCLUDED.data, name = EXCLUDED.name,
                        grade = EXCLUDED.grade, updated_at = now()
                    """,
                    (user_id, data["name"], data["grade"], json.dumps(data, ensure_ascii=False)),
                )
            conn.commit()
            return data
        finally:
            conn.close()
    except Exception:
        logger.exception("Auth: legacy migration failed (non-fatal)")
        return None
