from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from app.services.speech_eval import transcribe_arabic_audio, evaluate_speaking
from app.services.writing_eval import evaluate_writing
from app.services.diacritize import diacritize_text
from app.services.context_eval import evaluate_context
from app.services.spell_check import check_spelling

router = APIRouter()


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


@router.post("/diacritize")
def diacritize_endpoint(request: DiacritizeRequest):
    """إضافة التشكيل وعلامات الترقيم للنص العربي"""
    try:
        result = diacritize_text(request.text)
        return {"result": result}
    except Exception as e:
        raise HTTPException(500, f"خطأ في التشكيل: {str(e)}")


@router.post("/spellcheck")
def spellcheck_endpoint(request: SpellCheckRequest):
    """
    تدقيق إملائي/نحوي متقدم: يعيد قائمة الأخطاء مع موقعها الحرفي
    (start/end) في النص لإبرازها في الواجهة، والتصحيح المقترح.
    """
    try:
        return check_spelling(request.text, use_ai=request.use_ai)
    except Exception as e:
        raise HTTPException(500, f"خطأ في التدقيق الإملائي: {str(e)}")


@router.post("/speech")
async def evaluate_speech_endpoint(
    student_id: int = 0,
    lesson_id: str = "",
    reference_text: str = "",
    audio_file: UploadFile = File(...),
):
    allowed_types = ["audio/wav", "audio/mp3", "audio/webm", "audio/mpeg", "audio/ogg"]
    if audio_file.content_type not in allowed_types:
        raise HTTPException(400, "صيغة الملف غير مدعومة")

    audio_bytes = await audio_file.read()
    filename = audio_file.filename or "recording.wav"
    audio_format = filename.split(".")[-1] if "." in filename else "wav"

    try:
        transcript = transcribe_arabic_audio(audio_bytes, audio_format)
        result = evaluate_speaking(transcript, reference_text or None, lesson_id)
        result["student_id"] = student_id
        result["lesson_id"] = lesson_id
        return result
    except Exception as e:
        raise HTTPException(500, f"خطأ في معالجة الصوت: {str(e)}")


@router.post("/context")
def context_eval_endpoint(request: DiacritizeRequest):
    """تقييم سياق الجمل واقتراح تحسينات أسلوبية"""
    try:
        suggestions = evaluate_context(request.text)
        return {"suggestions": suggestions}
    except Exception as e:
        raise HTTPException(500, f"خطأ في تقييم السياق: {str(e)}")


@router.post("/writing")
def evaluate_writing_endpoint(request: WritingEvalRequest):
    try:
        result = evaluate_writing(request.text, request.min_words)
        result["student_id"] = request.student_id
        result["lesson_id"] = request.lesson_id
        return result
    except Exception as e:
        raise HTTPException(500, f"خطأ في تقييم الكتابة: {str(e)}")
