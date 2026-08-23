"""
مصادقة بسيطة لدخول المعلم عبر رمز وصول واحد (بدون قاعدة بيانات مستخدمين).
الرمز يُقرأ من متغيّر البيئة TEACHER_ACCESS_CODE، وإن لم يُعرَّف يُستخدم
رمز افتراضي — يُفضَّل ضبط هذا المتغيّر فعليًا في بيئة الإنتاج (Render).
"""
import os
from fastapi import APIRouter, HTTPException

router = APIRouter()

TEACHER_ACCESS_CODE = os.getenv("TEACHER_ACCESS_CODE", "sawti2026")


@router.post("/teacher-login")
def teacher_login(payload: dict):
    code = str(payload.get("code", "")).strip()
    if not code or code != TEACHER_ACCESS_CODE:
        raise HTTPException(401, "رمز الدخول غير صحيح")
    return {"ok": True}
