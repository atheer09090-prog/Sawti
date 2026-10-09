from dotenv import load_dotenv

# يقرأ ملف .env المحلي (للتطوير فقط). لا يستبدل متغيرات البيئة المضبوطة فعلًا، فلا يؤثر على الإنتاج.
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.routers import evaluation, reports, lessons, students, auth, reviews, sus
from app.services.security import is_production
import logging
import os

logger = logging.getLogger("sawti.main")

app = FastAPI(
    title="API - برنامج صوتي قلمي",
    description="خادم خلفي لبرنامج تعليم اللغة العربية",
    version="1.0.0",
    docs_url="/api/docs",
)

# ── حد حجم الطلب ──
# يرفض الطلبات الضخمة (حسب ترويسة Content-Length) قبل معالجتها. مُعرَّف قبل
# CORS عمدًا كي تمرّ ردود 413 عبر CORS فيقرأ المتصفح رسالة الخطأ بدل خطأ CORS غامض.
MAX_BODY_BYTES = 2 * 1024 * 1024          # JSON العادي
MAX_SPEECH_BODY_BYTES = 12 * 1024 * 1024  # رفع تسجيل صوتي (/api/eval/speech)


@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    cl = request.headers.get("content-length", "")
    if cl.isdigit():
        limit = MAX_SPEECH_BODY_BYTES if request.url.path.endswith("/eval/speech") else MAX_BODY_BYTES
        if int(cl) > limit:
            return JSONResponse({"detail": "حجم الطلب أكبر من المسموح"}, status_code=413)
    return await call_next(request)


# ── CORS ──
# ALLOWED_ORIGINS: نطاقات الواجهة مفصولة بفواصل، مثل:
#   https://domain.com,https://www.domain.com
# في الإنتاج لا يُسمح إلا بهذه النطاقات (لا "*"). في التطوير فقط يُسمح
# إضافةً بـ localhost/127.0.0.1 على أي منفذ.
_origins = [o.strip().rstrip("/") for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if "*" in _origins:
    logger.error("CORS: القيمة * غير مسموحة في ALLOWED_ORIGINS وتم تجاهلها — اذكر النطاقات صراحةً.")
    _origins = [o for o in _origins if o != "*"]

_dev = not is_production()
if is_production() and not _origins:
    logger.error(
        "CORS: ALLOWED_ORIGINS غير مضبوط في الإنتاج — لن يُسمح لأي واجهة بالاتصال "
        "بالخادم من المتصفح حتى تضبطه (مثال: https://domain.com,https://www.domain.com)."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$" if _dev else None,
    # الجلسات عبر ترويسة Authorization (Bearer) وليس كوكيز، فلا حاجة لـ credentials
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(evaluation.router, prefix="/api/eval", tags=["التقييم"])
app.include_router(reports.router, prefix="/api/reports", tags=["التقارير"])
app.include_router(lessons.router, prefix="/api/lessons", tags=["الدروس"])
app.include_router(students.router, prefix="/api/students", tags=["الطلاب"])
app.include_router(auth.router, prefix="/api/auth", tags=["الدخول"])
app.include_router(reviews.router, prefix="/api/reviews", tags=["التقييمات (قديم)"])
app.include_router(sus.router, prefix="/api/sus", tags=["استبيان SUS"])


@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "✅ برنامج صوتي قلمي يعمل بنجاح"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
