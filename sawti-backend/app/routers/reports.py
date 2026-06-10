from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel
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
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{student.name}.pdf"}
    )
