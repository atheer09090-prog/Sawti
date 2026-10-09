import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from pydantic import BaseModel
from app.services.ai_guard import ai_limit
from app.services.speech_eval import transcribe_arabic_audio_detailed, evaluate_speaking, correct_stt_errors
from app.services.writing_eval import evaluate_writing
from app.services.diacritize import diacritize_text
from app.services.context_eval import evaluate_context
from app.services.spell_check import check_spelling
from app.services.ask_teacher import answer_student_question, TeacherUnavailable

router = APIRouter()
logger = logging.getLogger("sawti.evaluation")

# صيغة الصوت الحقيقية تُشتق أولاً من الـContent-Type الذي يضعه المتصفح على
# الملف (وهو دقيق دائماً لأنه مأخوذ من نوع الـBlob الفعلي)، وليس من امتداد
# اسم الملف فقط — كان هذا الاعتماد على الاسم فقط سبباً محتملاً لإرسال صوت
# WebM إلى Whisper API باسم/امتداد "wav" خاطئ (المحتوى الفعلي يبقى WebM
# صحيحاً، لكن الامتداد المُرسَل معه لِـ Groq API كان مضلِّلاً).
_CONTENT_TYPE_TO_EXT = {
    "audio/webm": "webm", "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
    "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/ogg": "ogg", "audio/mp4": "mp4",
    "audio/x-m4a": "m4a", "audio/m4a": "m4a",
}


# ── حدود الإدخال (حماية حصة Groq/Gemini من الاستنزاف) ──
MAX_TEXT_CHARS = 5000        # نص كتابة/تشكيل/تدقيق (≈ 800 كلمة — أطول بكثير من نشاط طالب)
MAX_QUESTION_CHARS = 500     # سؤال "اسأل بذكاء"
MAX_REFERENCE_CHARS = 500    # عنوان/موضوع النشاط المرفق مع التسجيل
MAX_AUDIO_BYTES = 10 * 1024 * 1024   # 10 ميغابايت (≈ 30 دقيقة WebM/Opus، وحدّ Groq 25MB)
MIN_AUDIO_BYTES = 1000


def _check_len(value: str, limit: int, what: str):
    if value and len(value) > limit:
        raise HTTPException(413, f"{what} أطول من المسموح (الحد الأقصى {limit} حرف). اختصره وحاول مرة أخرى.")


async def _read_audio_limited(upload: UploadFile) -> bytes:
    """يقرأ الملف على دفعات ويتوقف فور تجاوز الحد، بدل تحميل ملف ضخم كاملًا في الذاكرة."""
    chunks, total = [], 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_AUDIO_BYTES:
            raise HTTPException(
                413, f"التسجيل أكبر من المسموح ({MAX_AUDIO_BYTES // (1024 * 1024)} ميغابايت). سجّل مقطعًا أقصر وحاول مرة أخرى.")
        chunks.append(chunk)
    return b"".join(chunks)


def _looks_like_audio(b: bytes) -> bool:
    """فحص بسيط لبداية الملف (magic bytes) حتى لا يكفي تزوير Content-Type لتمرير ملف غير صوتي."""
    if len(b) < 12:
        return False
    if b[:4] == b"\x1a\x45\xdf\xa3":                 # WebM / Matroska
        return True
    if b[:4] == b"OggS":                                  # Ogg
        return True
    if b[:4] == b"RIFF" and b[8:12] == b"WAVE":          # WAV
        return True
    if b[4:8] == b"ftyp":                                 # MP4 / M4A
        return True
    if b[:3] == b"ID3":                                   # MP3 مع وسم ID3
        return True
    if b[0] == 0xFF and (b[1] & 0xE0) == 0xE0:           # إطار MP3/AAC خام
        return True
    return False


def _fail(log_msg: str, user_msg: str, status: int = 500):
    """يسجّل الاستثناء كاملًا في اللوقز، ويرجع للعميل رسالة عربية عامة بلا تفاصيل داخلية."""
    logger.exception(log_msg)
    raise HTTPException(status, user_msg)


class WritingEvalRequest(BaseModel):
    student_id: int = 0
    lesson_id: str = ""
    text: str
    min_words: int = 20


class DiacritizeRequest(BaseModel):
    text: str


class SpellCheckRequest(BaseModel):
    text: str
    use_ai: bool = True  # عطّلها لفحص فوري بدون استدعاء Gemini


class AskQuestionRequest(BaseModel):
    question: str


@router.post("/diacritize", dependencies=[Depends(ai_limit("text", 60))])
def diacritize_endpoint(request: DiacritizeRequest):
    """إضافة التشكيل وعلامات الترقيم للنص العربي"""
    _check_len(request.text, MAX_TEXT_CHARS, "النص")
    try:
        result = diacritize_text(request.text)
        return {"result": result}
    except Exception:
        _fail("Diacritize failed", "تعذّر تشكيل النص الآن. حاول مرة أخرى.")


@router.post("/spellcheck", dependencies=[Depends(ai_limit("text", 60))])
def spellcheck_endpoint(request: SpellCheckRequest):
    """
    تدقيق إملائي/نحوي متقدم: يعيد قائمة الأخطاء مع موقعها الحرفي
    (start/end) في النص لإبرازها في الواجهة، والتصحيح المقترح.
    """
    _check_len(request.text, MAX_TEXT_CHARS, "النص")
    try:
        return check_spelling(request.text, use_ai=request.use_ai)
    except Exception:
        _fail("Spellcheck failed", "تعذّر التدقيق الإملائي الآن. حاول مرة أخرى.")


@router.post("/speech", dependencies=[Depends(ai_limit("speech", 15))])
async def evaluate_speech_endpoint(
    student_id: int = 0,
    lesson_id: str = "",
    reference_text: str = "",
    audio_file: UploadFile = File(...),
):
    content_type = (audio_file.content_type or "").split(";")[0].strip().lower()
    allowed_types = ["audio/wav", "audio/mp3", "audio/webm", "audio/mpeg", "audio/ogg",
                      "audio/x-wav", "audio/wave", "audio/mp4", "audio/x-m4a", "audio/m4a"]
    if content_type not in allowed_types:
        raise HTTPException(400, "صيغة الملف غير مدعومة")
    _check_len(reference_text, MAX_REFERENCE_CHARS, "عنوان النشاط")
    _check_len(lesson_id, 100, "معرّف الدرس")

    audio_bytes = await _read_audio_limited(audio_file)
    if len(audio_bytes) < MIN_AUDIO_BYTES:
        raise HTTPException(400, "التسجيل قصير جدًا أو فارغ. سجّل مرة أخرى وتحدّث لثوانٍ.")
    if not _looks_like_audio(audio_bytes):
        raise HTTPException(400, "الملف المرفوع ليس تسجيلًا صوتيًا صالحًا")

    # الصيغة الحقيقية: أولاً من الـContent-Type الفعلي للملف (الأدق دائماً)،
    # وفقط إن تعذّر ذلك نرجع لامتداد اسم الملف كحل احتياطي.
    audio_format = _CONTENT_TYPE_TO_EXT.get(content_type)
    if not audio_format:
        filename = audio_file.filename or "recording.wav"
        audio_format = filename.split(".")[-1].lower() if "." in filename else "wav"

    logger.info("Speech eval request: lesson_id=%s content_type=%s resolved_format=%s size_bytes=%d",
                lesson_id, content_type or "unknown", audio_format, len(audio_bytes))

    try:
        stt = transcribe_arabic_audio_detailed(audio_bytes, audio_format, topic_hint=reference_text)
        whisper_text = stt["whisper_text"]   # ما قاله Whisper حرفيًا
        transcript = stt["rules_text"]       # بعد طبقة القواعد الصوتية (المدخل لتصحيح Gemini)

        # مرحلة مستقلة: تصحيح أخطاء التعرف الآلي على الكلام فقط (وليست أخطاء
        # الطالب اللغوية) — التقييم يعتمد بعدها على النص المُصحَّح (canonical
        # transcript) حصرياً، وبذلك لا يُعاقَب الطالب على خطأ Whisper.
        stt_fix = correct_stt_errors(transcript, topic_hint=reference_text)
        corrected_transcript = stt_fix["correctedText"]

        result = evaluate_speaking(corrected_transcript, reference_text or None, lesson_id)
        result["student_id"] = student_id
        result["lesson_id"] = lesson_id
        # الحقول التالية كانت موجودة سابقاً ولم تتغير أسماؤها أو معانيها (توافق خلفي):
        result["raw_transcript"] = whisper_text               # ما قاله Whisper حرفيًا قبل أي تصحيح (للشفافية فقط)
        result["stt_corrections"] = stt_fix["corrections"]    # الأخطاء التي صُحِّحت ولم تُحتسَب على الطالب
        # حقل جديد إضافي (لا يُلغي "transcript" الموجود، فقط اسم أوضح لنفس القيمة):
        result["canonical_transcript"] = corrected_transcript  # النص المعتمد نهائياً للتقييم والعرض
        # شفافية خط التصحيح (حقل جديد إضافي): هل طُبِّقت طبقة القواعد؟ وماذا حدث لتصحيح Gemini؟
        # عند فشل Gemini أو غيابه يُستخدم النص الأصلي، وهذا الحقل يوضح أن التصحيح لم يُطبَّق.
        ai_status = stt_fix.get("status", "unknown")
        result["stt_pipeline"] = {
            "phonetic_rules_changed_text": whisper_text != transcript,
            "ai_correction_status": ai_status,
            "ai_correction_applied": ai_status == "applied",
        }
        logger.info("Speech eval done: word_count=%d corrections_applied=%d overall=%s",
                    len(corrected_transcript.split()), len(stt_fix["corrections"]), result.get("overall"))
        return result
    except Exception:
        _fail("Speech evaluation failed", "تعذّر تقييم التسجيل الآن. لم تُحتسب نتيجة لهذه المحاولة، حاول مرة أخرى.")


@router.post("/context", dependencies=[Depends(ai_limit("text", 60))])
def context_eval_endpoint(request: DiacritizeRequest):
    """تقييم سياق الجمل واقتراح تحسينات أسلوبية"""
    _check_len(request.text, MAX_TEXT_CHARS, "النص")
    try:
        suggestions = evaluate_context(request.text)
        return {"suggestions": suggestions}
    except Exception:
        _fail("Context eval failed", "تعذّر تقييم السياق الآن. حاول مرة أخرى.")


@router.post("/writing", dependencies=[Depends(ai_limit("writing", 30))])
def evaluate_writing_endpoint(request: WritingEvalRequest):
    _check_len(request.text, MAX_TEXT_CHARS, "النص")
    _check_len(request.lesson_id, 100, "معرّف الدرس")
    try:
        result = evaluate_writing(request.text, request.min_words)
        result["student_id"] = request.student_id
        result["lesson_id"] = request.lesson_id
        return result
    except Exception:
        _fail("Writing evaluation failed", "تعذّر تقييم الكتابة الآن. لم تُحتسب نتيجة لهذه المحاولة، حاول مرة أخرى.")


@router.post("/ask", dependencies=[Depends(ai_limit("ask", 20))])
def ask_smart_teacher_endpoint(request: AskQuestionRequest):
    """يُجيب عن سؤال يصوغه الطالب بنفسه — نشاط "🤖 اسأل بذكاء"."""
    _check_len(request.question, MAX_QUESTION_CHARS, "السؤال")
    try:
        answer = answer_student_question(request.question)
        return {"answer": answer}
    except TeacherUnavailable:
        # لا نُرجع اعتذارًا كأنه "إجابة" بحالة 200 (كان يُحتسب للطالب كسؤال ناجح)
        raise HTTPException(503, "المعلم الذكي غير متاح الآن. حاول مرة أخرى بعد قليل.")
    except Exception:
        _fail("Ask teacher failed", "تعذّرت الإجابة عن السؤال الآن. حاول مرة أخرى.")
