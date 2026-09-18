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

JWT_SECRET = os.getenv("JWT_SECRET", "")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_hex(32)
    logger.warning(
        "Security: JWT_SECRET غير مضبوط في متغيرات البيئة — تم توليد مفتاح "
        "مؤقت عشوائي. كل جلسات الدخول الحالية ستُلغى عند أي إعادة تشغيل "
        "للخادم. يجب ضبط JWT_SECRET في بيئة الإنتاج (Render) فورًا."
    )

JWT_ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 60 * 60 * 24 * 90  # 90 يومًا — طالب لا يريد تسجيل الدخول كل يوم


def hash_password(plain: str) -> str:
    """يجزّئ كلمة المرور بـ bcrypt (salt عشوائي مدمج تلقائيًا في الناتج)."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> str | None:
    """يرجع user_id إن كان الرمز صالحًا وغير منتهٍ، وإلا None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
