from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib import colors
from reportlab.lib.units import cm
import io
from datetime import datetime


def generate_student_report(student_data: dict) -> bytes:
    """
    توليد تقرير PDF لأداء الطالب
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    elements = []
    styles = getSampleStyleSheet()

    # العنوان
    title_style = ParagraphStyle(
        'ArabicTitle',
        parent=styles['Title'],
        fontSize=18,
        spaceAfter=12,
    )
    elements.append(Paragraph("تقرير أداء الطالب", title_style))
    elements.append(Paragraph("منصة صوتي قلمي — سلطنة عُمان", styles["Normal"]))
    elements.append(Spacer(1, 0.5 * cm))

    # معلومات الطالب
    student_info = [
        ["الاسم", student_data.get("name", "—")],
        ["الصف", student_data.get("grade", "—")],
        ["تاريخ التقرير", datetime.now().strftime("%Y-%m-%d")],
    ]

    info_table = Table(student_info, colWidths=[4 * cm, 10 * cm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#1a5c2a")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.5 * cm))

    # جدول التقدم في المهارات
    elements.append(Paragraph("تقدم المهارات", styles["Heading2"]))

    skills_data = [
        ["المهارة", "التقدم", "التقييم"],
        ["التحدث", f"{student_data.get('speaking_progress', 0):.0f}%",
         _get_grade(student_data.get('speaking_progress', 0))],
        ["الكتابة", f"{student_data.get('writing_progress', 0):.0f}%",
         _get_grade(student_data.get('writing_progress', 0))],
        ["التعلم الذاتي", f"{student_data.get('self_learning_progress', 0):.0f}%",
         _get_grade(student_data.get('self_learning_progress', 0))],
    ]

    skills_table = Table(skills_data, colWidths=[5 * cm, 4 * cm, 5 * cm])
    skills_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a5c2a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f7f0")]),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(skills_table)
    elements.append(Spacer(1, 0.5 * cm))

    # تعليق المعلم
    if student_data.get("teacher_comment"):
        elements.append(Paragraph("تعليق المعلم:", styles["Heading2"]))
        elements.append(Paragraph(student_data["teacher_comment"], styles["Normal"]))

    doc.build(elements)
    return buffer.getvalue()


def _get_grade(score: float) -> str:
    if score >= 90:
        return "ممتاز"
    elif score >= 80:
        return "جيد جداً"
    elif score >= 70:
        return "جيد"
    elif score >= 60:
        return "مقبول"
    else:
        return "يحتاج تطوير"
