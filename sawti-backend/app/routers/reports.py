from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel
from urllib.parse import quote
from app.services.pdf_gen import generate_student_report

router = APIRouter()


class StudentReportRequest(BaseModel):
    name: str
    grade: str
    speaking_progress: float = 0
    writing_progress: float = 0
    self_learning_progress: float = 0
    teacher_comment: str = ""
    points: int = 0
    stars: int = 0


@router.post("/student")
def generate_report(student: StudentReportRequest):
    """
    توليد تقرير PDF لأداء الطالب
    """
    pdf_bytes = generate_student_report(student.model_dump())
    # ملاحظة مهمة: رؤوس HTTP (headers) يجب أن تكون قابلة للترميز بـ
    # latin-1 فقط، واسم الطالب عربي غالبًا — لذلك لا يصح وضعه مباشرة
    # داخل filename=. نستخدم اسم ملف إنجليزي ثابت (ASCII) في filename،
    # مع filename* بترميز UTF-8 (RFC 5987) ليظهر المتصفح الاسم العربي
    # الصحيح عند الحفظ فعليًا.
    encoded_name = quote(f"تقرير_{student.name}.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=report.pdf; filename*=UTF-8''{encoded_name}"
        },
    )
