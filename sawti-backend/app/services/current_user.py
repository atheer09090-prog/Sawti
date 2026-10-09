"""
اعتماديات (dependencies) مشتركة لمعرفة هوية المستخدم عبر الترويسة
Authorization: Bearer <token>:

- get_current_user_id: طالب مسجّل (رمز role=student). رمز المعلم لا يُقبل هنا.
- require_teacher: معلم فقط (رمز role=teacher صادر عن /api/auth/teacher-login).
  الخادم يتحقق من التوقيع والانتهاء بنفسه — لا يُعتمد على أي علَم في الواجهة.
"""
from fastapi import Header, HTTPException
from app.services.security import decode_payload, decode_token, ROLE_TEACHER


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    token = _bearer(authorization)
    if not token:
        raise HTTPException(401, "يجب تسجيل الدخول أولًا")
    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(401, "انتهت صلاحية الجلسة، يرجى تسجيل الدخول مرة أخرى")
    return user_id


def require_teacher(authorization: str | None = Header(default=None)) -> str:
    token = _bearer(authorization)
    if not token:
        raise HTTPException(401, "يجب تسجيل دخول المعلم أولًا")
    payload = decode_payload(token)
    if not payload:
        raise HTTPException(401, "انتهت جلسة المعلم، يرجى إدخال رمز الدخول مرة أخرى")
    if payload["role"] != ROLE_TEACHER:
        raise HTTPException(403, "هذه الصلاحية للمعلم فقط")
    return payload["sub"]


def get_student_or_teacher(authorization: str | None = Header(default=None)) -> str:
    """هوية صاحب الرمز أيًّا كان دوره: user_id للطالب، أو "teacher" للمعلم."""
    token = _bearer(authorization)
    if not token:
        raise HTTPException(401, "يجب تسجيل الدخول أولًا")
    payload = decode_payload(token)
    if not payload:
        raise HTTPException(401, "انتهت صلاحية الجلسة، يرجى تسجيل الدخول مرة أخرى")
    return payload["sub"]
