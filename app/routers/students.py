"""
تخزين سجلّ كل طالب على الخادم (بدل الاعتماد فقط على localStorage في
المتصفح)، بحيث يستعيد الطالب تقدُّمه (النقاط، النجوم، الدروس المكتملة،
الشارات...) عند الدخول بنفس الاسم والصف من أي جهاز أو متصفح.

المفتاح المستخدم لكل طالب هو مزيج (الاسم + الصف) بعد تطبيع المسافات،
لتفادي تعارض الأسماء المتكررة بين شعب مختلفة. يُخزَّن كل شيء كملف JSON
واحد على القرص، بنفس نمط بقية الملفات في هذا المشروع (لا قاعدة بيانات).
"""
import os
import re
import json
from fastapi import APIRouter, HTTPException

router = APIRouter()

STUDENTS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "students.json")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _key(name: str, grade: str) -> str:
    return f"{_normalize(name)}|{_normalize(grade)}"


def _read_all() -> dict:
    os.makedirs(os.path.dirname(STUDENTS_FILE), exist_ok=True)
    if not os.path.exists(STUDENTS_FILE):
        return {}
    with open(STUDENTS_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _write_all(data: dict):
    os.makedirs(os.path.dirname(STUDENTS_FILE), exist_ok=True)
    with open(STUDENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@router.get("")
def list_students():
    """قائمة كل الطلاب المحفوظين (لاستخدامها لاحقًا في لوحة المعلم)."""
    return list(_read_all().values())


@router.get("/{name}/{grade}")
def get_student(name: str, grade: str):
    students = _read_all()
    record = students.get(_key(name, grade))
    if not record:
        raise HTTPException(404, "لا يوجد سجل محفوظ لهذا الطالب بعد")
    return record


@router.put("/{name}/{grade}")
def save_student(name: str, grade: str, data: dict):
    students = _read_all()
    data = dict(data)
    data["name"] = _normalize(name)
    data["grade"] = _normalize(grade)
    students[_key(name, grade)] = data
    _write_all(students)
    return {"ok": True}
