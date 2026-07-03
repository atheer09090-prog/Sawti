import os
import re
import tempfile
from typing import Optional
from groq import Groq

# كلمات شائعة تساعد Whisper على التعرف الصحيح
ARABIC_PROMPT = (
    "هذا تسجيل صوتي لطالب يتحدث باللغة العربية الفصحى. "
    "الكلمات الشائعة: رحلة، بحرية، جبلية، جوية، تجوال، استمتعنا، "
    "الأشجار، الشلال، الطائرة، المطار، الشاطئ، القوارب، الأسماك، "
    "الصيد، المدرسة، المعلم، الطالب، ذهبنا، قمنا، رأينا، شاهدنا، "
    "جميلة، رائعة، ممتعة، كثيراً، أيضاً، لقد، وقد، فقد."
)

def transcribe_arabic_audio(audio_bytes: bytes, audio_format: str = "wav") -> str:
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                file=(f"recording.{audio_format}", audio_file.read()),
                model="whisper-large-v3",
                language="ar",
                response_format="text",
                prompt=ARABIC_PROMPT,
                temperature=0.0,  # أقل عشوائية = أدق
            )
        return transcription.strip() if isinstance(transcription, str) else transcription.text.strip()
    finally:
        os.unlink(tmp_path)


def evaluate_speaking(transcript: str, reference_text: Optional[str] = None) -> dict:
    if not transcript or len(transcript.strip()) < 5:
        return {
            "pronunciation": 0, "sentence_structure": 0,
            "diacritics": 0, "grammar": 0, "overall": 0,
            "feedback": "لم يتم التعرف على الكلام. يرجى المحاولة مجدداً.",
            "word_count": 0, "transcript": transcript,
        }

    words = transcript.split()
    word_count = len(words)

    pronunciation_score = _evaluate_pronunciation(transcript, reference_text)
    sentence_score      = _evaluate_sentence_structure(transcript, word_count)
    diacritics_score    = _evaluate_diacritics(transcript)
    grammar_score       = _evaluate_grammar(transcript)

    overall = round(
        (pronunciation_score * 0.35) +
        (sentence_score      * 0.25) +
        (diacritics_score    * 0.20) +
        (grammar_score       * 0.20)
    )

    return {
        "pronunciation": pronunciation_score,
        "sentence_structure": sentence_score,
        "diacritics": diacritics_score,
        "grammar": grammar_score,
        "overall": overall,
        "word_count": word_count,
        "transcript": transcript,
        "feedback": _generate_feedback(overall, pronunciation_score, sentence_score),
    }


def _evaluate_pronunciation(transcript: str, reference: Optional[str]) -> int:
    if not reference:
        arabic_chars = len(re.findall(r'[\u0600-\u06FF]', transcript))
        total_chars  = max(len(transcript.replace(" ", "")), 1)
        return min(100, int((arabic_chars / total_chars) * 100))
    ref_words   = set(reference.split())
    trans_words = set(transcript.split())
    if not ref_words:
        return 70
    overlap = len(ref_words & trans_words) / len(ref_words)
    return min(100, int(overlap * 100))


def _evaluate_sentence_structure(transcript: str, word_count: int) -> int:
    score = 50
    if word_count >= 20:   score += 20
    elif word_count >= 10: score += 10
    connectors = ['ثم','لأن','لذلك','أما','بينما','حيث','كما','أيضاً','و','لكن']
    found = sum(1 for c in connectors if c in transcript)
    score += min(20, found * 5)
    if '.' in transcript or '،' in transcript:
        score += 10
    return min(100, score)


def _evaluate_diacritics(transcript: str) -> int:
    total_chars = len(re.findall(r'[\u0600-\u06FF]', transcript))
    diacritics  = len(re.findall(r'[\u064B-\u065F]', transcript))
    if total_chars == 0:
        return 50
    return min(100, int((diacritics / total_chars) * 200))


def _evaluate_grammar(transcript: str) -> int:
    score = 60
    verb_patterns = ['يعمل','يذهب','يقول','يكتب','يقرأ','كان','أصبح']
    if any(v in transcript for v in verb_patterns):
        score += 15
    al_count = len(re.findall(r'\bال\w+', transcript))
    score += min(15, al_count * 3)
    common_errors = ['هاذا','هاذه','ذالك']
    score -= sum(1 for e in common_errors if e in transcript) * 5
    return max(0, min(100, score))


def _generate_feedback(overall: int, pronunciation: int, structure: int) -> str:
    if overall >= 85: return "ممتاز! أداؤك رائع في التحدث باللغة العربية."
    elif overall >= 70: return "جيد جداً! يمكنك تحسين النطق أكثر بالتدريب المستمر."
    elif overall >= 55: return "جيد! ركّز على بناء الجمل الكاملة وإضافة أدوات الربط."
    else: return "استمر في التدريب! حاول التحدث بجمل أطول وأكثر وضوحاً."
