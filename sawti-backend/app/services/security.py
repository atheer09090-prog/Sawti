"""
أدوات أمان حسابات الطلاب: تجزئة (hash) كلمات المرور بدل تخزينها كنص
عادي، وإصدار/التحقق من رموز الجلسة (JWT) حتى لا يُضطر الطالب لإرسال
بريده وكلمة مروره مع كل طلب.

المفتاح السري لتوقيع الرموز يُقرأ من متغيّر البيئة JWT_SECRET. إن لم
يُضبَط بعد (مرحلة تطوير محلي فقط)، نولّد قيمة عشوائية عند إقلاع الخادم
مع تحذير واضح في اللوقز — لأن هذا يعني أن كل الجلسات ستُلغى عند إعادة
تشغيل الخادم، وهذا غير مقبول في بيئة الإنتاج (Render)، لذا يجب ضبط
JWT_SECRET فعليًا هناك.
"""
import os
import time
import logging
import secrets
import bcrypt
import jwt

logger = logging.getLogger("sawti.security")

def is_production() -> bool:
    """يُعدّ التشغيل إنتاجًا إن كان ENV أو ENVIRONMENT مساويًا production/prod."""
    for name in ("ENV", "ENVIRONMENT"):
        if os.getenv(name, "").strip().lower() in ("production", "prod"):
            return True
    return False


JWT_SECRET = os.getenv("JWT_SECRET", "").strip()
if not JWT_SECRET:
    if is_production():
        # في الإنتاج لا نشغّل نظام جلسات غير مستقر: الإقلاع يفشل برسالة واضحة.
        raise RuntimeError(
            "JWT_SECRET غير مضبوط في بيئة الإنتاج. اضبطه كمتغيّر بيئة "
            "(قيمة عشوائية طويلة، مثلًا: python -c \"import secrets; print(secrets.token_hex(32))\") "
            "ثم أعد تشغيل الخادم."
        )
    JWT_SECRET = secrets.token_hex(32)
    logger.warning(
        "Security: JWT_SECRET غير مضبوط — تم توليد مفتاح مؤقت عشوائي (للتطوير المحلي فقط). "
        "كل جلسات الدخول ستُلغى عند أي إعادة تشغيل للخادم."
    )

JWT_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 90  # 90 يومًا — طالب لا يريد تسجيل الدخول كل يوم
TEACHER_TOKEN_TTL_SECONDS = 60 * 60 * 8  # 8 ساعات — جلسة معلم أقصر لأنها أكثر حساسية

ROLE_STUDENT = "student"
ROLE_TEACHER = "teacher"


def hash_password(plain: str) -> str:
    """يجزّئ كلمة المرور بـ bcrypt (salt عشوائي مدمج تلقائيًا في الناتج)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_token(user_id: str) -> str:
    """رمز طالب. الدور student صريح في الرمز (الرموز القديمة بلا دور تُعامَل كطالب)."""
    payload = {"sub": user_id, "role": ROLE_STUDENT, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_teacher_token() -> str:
    """رمز معلم (role=teacher) صالح 8 ساعات."""
    payload = {"sub": "teacher", "role": ROLE_TEACHER, "exp": int(time.time()) + TEACHER_TOKEN_TTL_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_payload(token: str) -> dict | None:
    """يرجع محتوى الرمز إن كان التوقيع صالحًا وغير منتهٍ، وإلا None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if not payload.get("sub"):
        return None
    # رموز الطلاب الصادرة قبل إضافة حقل الدور لا تحمل role → طالب (توافق خلفي)
    payload.setdefault("role", ROLE_STUDENT)
    return payload


def decode_token(token: str) -> str | None:
    """يرجع user_id إن كان الرمز رمز طالب صالحًا وغير منتهٍ، وإلا None."""
    payload = decode_payload(token)
    if not payload or payload["role"] != ROLE_STUDENT:
        return None
    return payload["sub"]
