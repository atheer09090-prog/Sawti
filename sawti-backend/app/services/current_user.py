"""
اعتمادية (dependency) مشتركة تُستخدم في أي مسار يحتاج معرفة هوية الطالب
المسجّل دخوله حاليًا، عبر ترويسة Authorization: Bearer <token>.
"""
from fastapi import Header, HTTPException
from app.services.security import decode_token


def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "يجب تسجيل الدخول أولًا")
    token = authorization.split(" ", 1)[1].strip()
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(401, "انتهت صلاحية الجلسة، يرجى تسجيل الدخول مرة أخرى")
    return user_id
