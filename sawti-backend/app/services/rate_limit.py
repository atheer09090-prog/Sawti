"""
تحديد معدّل الطلبات (rate limiting) بسيط داخل الذاكرة — بلا خدمة خارجية
ولا اشتراك جديد.

حدود هذا الحل (مقصودة لبساطته): العدّادات في ذاكرة العملية الواحدة، فتُصفَّر
عند إعادة تشغيل الخادم، ولا تُشارَك بين عدة نسخ (instances). كافٍ لخادم
Render واحد ويحمي من الاستنزاف العرَضي ومن تخمين رمز المعلم؛ وليس بديلًا
عن حماية على مستوى البنية التحتية إن كبر الاستخدام لاحقًا.
"""
import time
import threading
from collections import defaultdict, deque
from fastapi import HTTPException, Request

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def client_ip(request: Request) -> str:
    """
    عنوان العميل. خلف وسيط (Render) نأخذ آخر عنصر في X-Forwarded-For لأنه
    الذي يضيفه الوسيط نفسه؛ العناصر الأولى يستطيع العميل تزويرها.
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        last = xff.split(",")[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "unknown"


def _prune(q: deque, window: float, now: float):
    while q and now - q[0] > window:
        q.popleft()


def check_limit(key: str, max_hits: int, window_seconds: float,
                message: str = "طلبات كثيرة خلال وقت قصير، انتظر قليلًا ثم حاول مرة أخرى."):
    """يسجّل محاولة ويرفع 429 إن تجاوز المفتاح الحد داخل النافذة الزمنية."""
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        _prune(q, window_seconds, now)
        if len(q) >= max_hits:
            retry = int(window_seconds - (now - q[0])) + 1
            raise HTTPException(429, message, headers={"Retry-After": str(retry)})
        q.append(now)


def is_blocked(key: str, max_hits: int, window_seconds: float) -> bool:
    """هل بلغ المفتاح الحد؟ (بدون تسجيل محاولة جديدة)."""
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        _prune(q, window_seconds, now)
        return len(q) >= max_hits


def record_hit(key: str):
    with _lock:
        _hits[key].append(time.monotonic())


def reset(key: str):
    with _lock:
        _hits.pop(key, None)


def clear_all():
    """للاختبارات فقط."""
    with _lock:
        _hits.clear()
