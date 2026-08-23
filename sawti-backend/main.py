from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import evaluation, reports, lessons, students, auth
import os

app = FastAPI(
    title="API - منصة صوتي قلمي",
    description="خادم خلفي لمنصة تعليم اللغة العربية",
    version="1.0.0",
    docs_url="/api/docs",
)

origins = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(evaluation.router, prefix="/api/eval", tags=["التقييم"])
app.include_router(reports.router, prefix="/api/reports", tags=["التقارير"])
app.include_router(lessons.router, prefix="/api/lessons", tags=["الدروس"])
app.include_router(students.router, prefix="/api/students", tags=["الطلاب"])
app.include_router(auth.router, prefix="/api/auth", tags=["الدخول"])


@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "✅ منصة صوتي قلمي تعمل بنجاح"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
