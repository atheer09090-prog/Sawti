from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from app.services.speech_eval import transcribe_arabic_audio, evaluate_speaking
from app.services.writing_eval import evaluate_writing

router = APIRouter()


class WritingEvalRequest(BaseModel):
    student_id: int = 0
    lesson_id: str = ""
    text: str
    min_words: int = 20


@router.post("/speech")
async def evaluate_speech_endpoint(
    student_id: int = 0,
    lesson_id: str = "",
    reference_text: str = "",
    audio_file: UploadFile = File(...),
):
    """
    تقييم التحدث: رفع ملف صوتي والحصول على التقييم
    - **audio_file**: ملف صوتي (wav/mp3/webm)
    - **reference_text**: النص المرجعي للمقارنة (اختياري)
    """
    allowed_types = ["audio/wav", "audio/mp3", "audio/webm", "audio/mpeg", "audio/ogg"]
    if audio_file.content_type not in allowed_types:
        raise HTTPException(400, "صيغة الملف غير مدعومة")

    audio_bytes = await audio_file.read()
    filename = audio_file.filename or "recording.wav"
    audio_format = filename.split(".")[-1] if "." in filename else "wav"

    try:
        transcript = transcribe_arabic_audio(audio_bytes, audio_format)
        result = evaluate_speaking(transcript, reference_text or None)
        result["student_id"] = student_id
        result["lesson_id"] = lesson_id
        return result
    except Exception as e:
        raise HTTPException(500, f"خطأ في معالجة الصوت: {str(e)}")


@router.post("/writing")
def evaluate_writing_endpoint(request: WritingEvalRequest):
    """
    تقييم الكتابة: إرسال النص والحصول على التقييم
    """
    try:
        result = evaluate_writing(request.text, request.min_words)
        result["student_id"] = request.student_id
        result["lesson_id"] = request.lesson_id
        return result
    except Exception as e:
        raise HTTPException(500, f"خطأ في تقييم الكتابة: {str(e)}")
