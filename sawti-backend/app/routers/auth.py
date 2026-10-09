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
import secrets
import logging
import hmac
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, EmailStr, field_validator

from app.services import db
from app.services.security import (
    hash_password, verify_password, create_token, create_teacher_token,
    TEACHER_TOKEN_TTL_SECONDS,
)
from app.services.current_user import get_current_user_id
from app.services import rate_limit

router = APIRouter()
logger = logging.getLogger("sawti.auth")

# لا قيمة افتراضية إطلاقًا: إن لم يُضبَط TEACHER_ACCESS_CODE يُغلق دخول المعلم
# كليًا (انظر teacher_login). تُقرأ القيمة عند كل طلب لا عند الاستيراد.
def _teacher_code() -> str:
    return os.getenv("TEACHER_ACCESS_CODE", "").strip()


if not _teacher_code():
    logger.error(
        "Auth: TEACHER_ACCESS_CODE غير مضبوط — دخول المعلم معطَّل حتى تضبطه "
        "في متغيرات البيئة. لا يوجد رمز افتراضي."
    )

# حدود المحاولات: تخمين رمز المعلم (فشل) وإنشاء الحسابات
_TEACHER_FAIL_MAX, _TEACHER_FAIL_WINDOW = 5, 15 * 60

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
def teacher_login(payload: dict, request: Request):
    """
    يتحقق من رمز المعلم ويُصدر JWT خاصًا به (role=teacher، صالح 8 ساعات).
    كل مسارات لوحة المعلم الحساسة تتحقق من هذا الرمز عبر require_teacher.
    """
    expected = _teacher_code()
    if not expected:
        logger.error("Auth: محاولة دخول معلم لكن TEACHER_ACCESS_CODE غير مضبوط")
        raise HTTPException(503, "دخول المعلم غير مفعَّل على الخادم حاليًا")

    ip_key = f"teacher-fail:{rate_limit.client_ip(request)}"
    if rate_limit.is_blocked(ip_key, _TEACHER_FAIL_MAX, _TEACHER_FAIL_WINDOW):
        raise HTTPException(429, "محاولات خاطئة كثيرة، حاول مرة أخرى بعد قليل",
                            headers={"Retry-After": str(_TEACHER_FAIL_WINDOW)})

    code = str(payload.get("code", "")).strip()
    # مقارنة بزمن ثابت لتفادي تسريب معلومات عبر زمن الاستجابة
    if not code or not hmac.compare_digest(code.encode("utf-8"), expected.encode("utf-8")):
        rate_limit.record_hit(ip_key)
        raise HTTPException(401, "رمز الدخول غير صحيح")

    rate_limit.reset(ip_key)
    return {
        "ok": True,
        "token": create_teacher_token(),
        "expires_in": TEACHER_TOKEN_TTL_SECONDS,
        "name": "المعلم",
    }


@router.post("/guest-login")
def guest_login(request: Request):
    """
    دخول تجريبي فوري بلا بريد إلكتروني ولا كلمة مرور — مخصَّص لأعضاء
    لجنة التحكيم أو أي زائر يريد استكشاف البرنامج بسرعة. كل ضغطة على
    هذا الزر تُنشئ حسابًا معزولًا جديدًا (ببريد وكلمة مرور عشوائيين
    داخليًا لا يراهما أحد)، حتى لا يتشارك عدة أعضاء لجنة نفس الحساب
    ويكتب كل واحد فوق تقدّم الآخر.
    """
    _require_db()
    # حد سخي (لجنة التحكيم/مدرسة قد تتشارك IP واحدًا) لكنه يمنع إغراق الجدول بحسابات وهمية
    rate_limit.check_limit(f"guest:{rate_limit.client_ip(request)}", 60, 3600)
    db.ensure_table("users", _CREATE_USERS_TABLE_SQL)

    user_id = str(uuid.uuid4())
    guest_email = f"guest-{user_id[:8]}@sawti-qalami.local"
    guest_password_hash = hash_password(secrets.token_hex(16))

    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id, name, grade, avatar, email, password_hash, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, now())
                """,
                (user_id, "عُضْوُ لَجْنَةِ التَّحْكِيمِ", "زَائِرٌ تَجْرِيبِيٌّ", "boy1", guest_email, guest_password_hash),
            )
        conn.commit()
    except Exception:
        logger.exception("Auth: guest login failed")
        raise HTTPException(500, "تعذّر إنشاء دخول تجريبي، حاول مرة أخرى")
    finally:
        conn.close()

    token = create_token(user_id)
    return {
        "ok": True,
        "token": token,
        "user": {"id": user_id, "name": "عُضْوُ لَجْنَةِ التَّحْكِيمِ", "grade": "زَائِرٌ تَجْرِيبِيٌّ", "avatar": "boy1", "email": guest_email},
    }


@router.post("/register")
def register(payload: RegisterPayload, request: Request):
    """إنشاء حساب طالب جديد. يرجع رمز جلسة (token) فور النجاح."""
    _require_db()
    # 60/ساعة لكل IP: حصة دراسية كاملة قد تسجّل من شبكة مدرسة واحدة
    rate_limit.check_limit(f"register:{rate_limit.client_ip(request)}", 60, 3600)
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
def login(payload: LoginPayload, request: Request):
    _require_db()
    db.ensure_table("users", _CREATE_USERS_TABLE_SQL)
    email = _normalize_email(payload.email)

    # نحدّ المحاولات الفاشلة فقط (لا الناجحة) — لمنع تخمين كلمات المرور دون أن
    # نُعطّل صفًّا كاملًا يسجّل دخوله معًا من IP واحد.
    email_key = f"login-fail-email:{email}"
    ip_key = f"login-fail-ip:{rate_limit.client_ip(request)}"
    if rate_limit.is_blocked(email_key, 8, 15 * 60) or rate_limit.is_blocked(ip_key, 60, 15 * 60):
        raise HTTPException(429, "محاولات دخول خاطئة كثيرة. انتظر بضع دقائق ثم حاول مرة أخرى.",
                            headers={"Retry-After": str(15 * 60)})

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
        rate_limit.record_hit(ip_key)
        raise HTTPException(404, "لا يوجد حساب بهذا البريد الإلكتروني")
    if not verify_password(payload.password, row[4]):
        rate_limit.record_hit(email_key)
        rate_limit.record_hit(ip_key)
        raise HTTPException(401, "كلمة المرور غير صحيحة")

    rate_limit.reset(email_key)
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
