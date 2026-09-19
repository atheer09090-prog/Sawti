import io
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── استيراد اختياري وآمن لمكتبتَي تشكيل النص العربي ──
# هاتان المكتبتان تُحسِّنان شكل النص العربي داخل الـ PDF فقط (ربط
# الحروف + الترتيب من اليمين لليسار)، وليستا ضروريتين لعمل بقية
# المنصة إطلاقًا. لذلك لا نجعل غيابهما (مثلاً بسبب عدم تحديث
# requirements.txt فعليًا على الخادم) يُسقط تشغيل الخادم بالكامل —
# نكتفي بإيقاف التشكيل والاعتماد على تسجيل الخط فقط في أسوأ الحالات.
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _RESHAPE_AVAILABLE = True
except ImportError:
    _RESHAPE_AVAILABLE = False

# ── تسجيل خط عربي حقيقي (Amiri — نفس خط العناوين في واجهة المنصة) ──
# دون هذا التسجيل يستخدم ReportLab خطوطًا أساسية (Helvetica) لا تحتوي
# حروفًا عربية إطلاقًا، فتظهر كل الكلمات العربية كمربعات فارغة في الـ PDF.
_FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "fonts")
_REGULAR_PATH = os.path.join(_FONTS_DIR, "Amiri-Regular.ttf")
_BOLD_PATH = os.path.join(_FONTS_DIR, "Amiri-Bold.ttf")

FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"

if os.path.exists(_REGULAR_PATH):
    pdfmetrics.registerFont(TTFont("Amiri", _REGULAR_PATH))
    FONT_REGULAR = "Amiri"
    if os.path.exists(_BOLD_PATH):
        pdfmetrics.registerFont(TTFont("Amiri-Bold", _BOLD_PATH))
        FONT_BOLD = "Amiri-Bold"
    else:
        FONT_BOLD = "Amiri"


def ar(text) -> str:
    """
    يُعيد تشكيل النص العربي (ربط الحروف ببعضها بشكلها الصحيح) ويرتّبه
    بصريًا من اليمين لليسار — بدون هذا تظهر الحروف منفصلة/بترتيب معكوس
    داخل الـ PDF حتى لو كان الخط يدعم العربية، لأن ReportLab لا يقوم
    بهذه المعالجة تلقائيًا كما يفعل المتصفح.
    """
    text = str(text) if text is not None else ""
    if not text or not _RESHAPE_AVAILABLE:
        return text
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


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
        "ArabicTitle",
        parent=styles["Title"],
        fontName=FONT_BOLD,
        fontSize=18,
        alignment=TA_RIGHT,
        spaceAfter=12,
    )
    normal_style = ParagraphStyle(
        "ArabicNormal",
        parent=styles["Normal"],
        fontName=FONT_REGULAR,
        fontSize=11,
        alignment=TA_RIGHT,
        leading=16,
    )
    heading_style = ParagraphStyle(
        "ArabicHeading",
        parent=styles["Heading2"],
        fontName=FONT_BOLD,
        fontSize=14,
        alignment=TA_RIGHT,
        spaceBefore=8,
        spaceAfter=6,
    )

    elements.append(Paragraph(ar("تقرير أداء الطالب"), title_style))
    elements.append(Paragraph(ar("برنامج صوتي قلمي — سلطنة عُمان"), normal_style))
    elements.append(Spacer(1, 0.5 * cm))

    # معلومات الطالب
    student_info = [
        [ar(student_data.get("name", "—")), ar("الاسم")],
        [ar(student_data.get("grade", "—")), ar("الصف")],
        [datetime.now().strftime("%Y-%m-%d"), ar("تاريخ التقرير")],
    ]

    info_table = Table(student_info, colWidths=[10 * cm, 4 * cm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (1, 0), (1, -1), colors.HexColor("#1a5c2a")),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
        ("FONTNAME", (1, 0), (1, -1), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.5 * cm))

    # جدول التقدم في المهارات
    elements.append(Paragraph(ar("تقدم المهارات"), heading_style))

    skills_data = [
        [ar("التقييم"), ar("التقدم"), ar("المهارة")],
        [
            ar(_get_grade(student_data.get("speaking_progress", 0))),
            f"{student_data.get('speaking_progress', 0):.0f}%",
            ar("التحدث"),
        ],
        [
            ar(_get_grade(student_data.get("writing_progress", 0))),
            f"{student_data.get('writing_progress', 0):.0f}%",
            ar("الكتابة"),
        ],
        [
            ar(_get_grade(student_data.get("self_learning_progress", 0))),
            f"{student_data.get('self_learning_progress', 0):.0f}%",
            ar("التعلم الذاتي"),
        ],
    ]

    skills_table = Table(skills_data, colWidths=[5 * cm, 4 * cm, 5 * cm])
    skills_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a5c2a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f7f0")]),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(skills_table)
    elements.append(Spacer(1, 0.5 * cm))

    # نقاط ونجوم
    stats_data = [[
        ar(f"{student_data.get('stars', 0)} نجمة"),
        ar(f"{student_data.get('points', 0)} نقطة"),
    ]]
    stats_table = Table(stats_data, colWidths=[7 * cm, 7 * cm])
    stats_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, -1), 13),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#b45309")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(stats_table)
    elements.append(Spacer(1, 0.5 * cm))

    # تعليق المعلم
    if student_data.get("teacher_comment"):
        elements.append(Paragraph(ar("تعليق المعلم:"), heading_style))
        elements.append(Paragraph(ar(student_data["teacher_comment"]), normal_style))

    doc.build(elements)
    return buffer.getvalue()


def generate_sus_report(rows: list, summary: dict) -> bytes:
    """
    تقرير PDF لنتائج استبيان SUS، يضم: ملخصًا رقميًا، مخطط دائري (Pie)
    لتوزيع المشاركين على تصنيفات SUS الثلاثة، ومخطط أعمدة (Bar) لمتوسط
    إجابة كل عبارة من العبارات العشر عبر كل المشاركين — وهو ما يفيد
    المعلم/الباحث في تحديد أي جوانب البرنامج الأضعف بدقة.
    """
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.legends import Legend

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm,
    )
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle("ArabicTitle", parent=styles["Title"], fontName=FONT_BOLD,
                                  fontSize=18, alignment=TA_RIGHT, spaceAfter=12)
    heading_style = ParagraphStyle("ArabicHeading", parent=styles["Heading2"], fontName=FONT_BOLD,
                                    fontSize=13, alignment=TA_RIGHT, spaceAfter=8, spaceBefore=14)
    normal_style = ParagraphStyle("ArabicNormal", parent=styles["Normal"], fontName=FONT_REGULAR,
                                   fontSize=11, alignment=TA_RIGHT)

    elements.append(Paragraph(ar("تقرير استبيان قابلية الاستخدام (SUS)"), title_style))
    elements.append(Paragraph(ar(f"برنامج صوتي قلمي — تاريخ التصدير: {datetime.now().strftime('%Y-%m-%d')}"), normal_style))
    elements.append(Spacer(1, 0.5 * cm))

    count = summary.get("count", 0)
    average = summary.get("average")
    bands = summary.get("bands", {"poor": 0, "ok": 0, "good": 0})

    if count == 0:
        elements.append(Paragraph(ar("لا توجد إجابات على الاستبيان بعد."), normal_style))
        doc.build(elements)
        return buffer.getvalue()

    # ── جدول الملخص ──
    summary_data = [
        [ar("القيمة"), ar("المؤشر")],
        [str(average), ar("متوسط درجة SUS (من 100)")],
        [str(count), ar("عدد المشاركين")],
        [str(bands.get("good", 0)), ar("جيد إلى ممتاز (70 فأكثر)")],
        [str(bands.get("ok", 0)), ar("مقبول / متوسط (50-70)")],
        [str(bands.get("poor", 0)), ar("يحتاج إلى تحسين (أقل من 50)")],
    ]
    summary_table = Table(summary_data, colWidths=[4 * cm, 10 * cm])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a5c2a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), FONT_BOLD),
        ("FONTNAME", (0, 1), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f4f6")]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(summary_table)

    # ── المخطط الدائري: توزيع المشاركين على التصنيفات ──
    elements.append(Paragraph(ar("توزيع المشاركين حسب التصنيف"), heading_style))
    pie_drawing = Drawing(400, 200)
    pie = Pie()
    pie.x, pie.y = 150, 20
    pie.width, pie.height = 160, 160
    pie_values = [bands.get("good", 0), bands.get("ok", 0), bands.get("poor", 0)]
    pie_labels = ["good", "ok", "poor"]
    # نستبعد التصنيفات بلا أي مشارك حتى لا يظهر قطاع بلا قيمة في الرسم
    nonzero = [(v, l) for v, l in zip(pie_values, pie_labels) if v > 0]
    pie.data = [v for v, _ in nonzero]
    pie.labels = [str(v) for v, _ in nonzero]
    pie_colors = {"good": colors.HexColor("#16a34a"), "ok": colors.HexColor("#f59e0b"), "poor": colors.HexColor("#dc2626")}
    for i, (_, label) in enumerate(nonzero):
        pie.slices[i].fillColor = pie_colors[label]
    pie_drawing.add(pie)

    legend = Legend()
    legend.x = 330
    legend.y = 140
    legend.dx = 8
    legend.dy = 8
    legend.fontName = FONT_REGULAR
    legend.fontSize = 9
    legend_labels = {"good": "جيد فأكثر", "ok": "متوسط", "poor": "يحتاج تحسينًا"}
    legend.colorNamePairs = [(pie_colors[label], ar(legend_labels[label])) for _, label in nonzero]
    pie_drawing.add(legend)
    elements.append(pie_drawing)

    # ── مخطط الأعمدة: متوسط كل عبارة من العبارات العشر ──
    elements.append(Paragraph(ar("متوسط الإجابة على كل عبارة (1-5)"), heading_style))
    item_count = 10
    item_sums = [0.0] * item_count
    valid_rows = [r for r in rows if isinstance(r.get("answers"), list) and len(r["answers"]) == item_count]
    for r in valid_rows:
        for i, a in enumerate(r["answers"]):
            item_sums[i] += a
    n = max(len(valid_rows), 1)
    item_avgs = [round(s / n, 2) for s in item_sums]

    bar_drawing = Drawing(460, 220)
    bar = VerticalBarChart()
    bar.x, bar.y = 40, 30
    bar.width, bar.height = 400, 160
    bar.data = [item_avgs]
    bar.categoryAxis.categoryNames = [str(i + 1) for i in range(item_count)]
    bar.categoryAxis.labels.fontName = FONT_REGULAR
    bar.valueAxis.valueMin = 0
    bar.valueAxis.valueMax = 5
    bar.valueAxis.valueStep = 1
    bar.bars[0].fillColor = colors.HexColor("#1a5c2a")
    bar_drawing.add(bar)
    bar_drawing.add(String(220, 205, ar("رقم العبارة"), fontName=FONT_REGULAR, fontSize=9, textAnchor="middle"))
    elements.append(bar_drawing)
    elements.append(Paragraph(
        ar("العبارات ذات الأرقام الزوجية (2، 4، 6، 8، 10) سلبية الصياغة، فانخفاض متوسطها مؤشر إيجابي."),
        ParagraphStyle("Note", parent=normal_style, fontSize=9, textColor=colors.grey),
    ))

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
