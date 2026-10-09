"""
حماية مسارات الذكاء الاصطناعي (Groq/Gemini) من الاستنزاف وسوء الاستخدام:

1) مصادقة: طالب (بما فيهم الحساب التجريبي guest لأنه يحمل JWT فعلًا) أو معلم.
2) حدّ معدّل لكل مستخدم (وليس لكل IP، لأن مدرسة كاملة قد تتشارك IP واحدًا).

الأرقام أدناه سخيّة عمدًا: لا تُزعج الاستخدام الطبيعي (طالب يسجّل/يكتب
ويُعاد التقييم) لكنها تقطع السكربتات التي تحرق الحصة.
"""
from fastapi import Depends
from app.services.current_user import get_student_or_teacher
from app.services import rate_limit

_MSG = "طلبات كثيرة خلال وقت قصير. انتظر قليلًا ثم حاول مرة أخرى."


def ai_limit(bucket: str, max_hits: int, window_seconds: int = 600):
    """يرجع dependency تتحقق من الدخول ثم تطبّق حدًّا لكل مستخدم داخل الفئة bucket."""
    def _dep(identity: str = Depends(get_student_or_teacher)) -> str:
        rate_limit.check_limit(f"ai:{bucket}:{identity}", max_hits, window_seconds, message=_MSG)
        return identity
    return _dep
