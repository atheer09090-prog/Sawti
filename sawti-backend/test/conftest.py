# -*- coding: utf-8 -*-
"""
إعداد بيئة الاختبارات. يجب أن يُنفَّذ قبل استيراد التطبيق، لأن الإعدادات
(JWT_SECRET, DATABASE_URL...) تُقرأ من متغيرات البيئة عند الاستيراد.

أمان مهم: نفرض DATABASE_URL = TEST_DATABASE_URL (أو فارغًا) دائمًا، كي لا
تعمل الاختبارات أبدًا على قاعدة الإنتاج لو كانت DATABASE_URL مضبوطة في جهازك.
الاختبارات التي تحتاج قاعدة بيانات تُتخطّى تلقائيًا إن لم يُضبَط TEST_DATABASE_URL.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["JWT_SECRET"] = "test-secret-not-for-production-0123456789abcdef"
os.environ["TEACHER_ACCESS_CODE"] = "test-teacher-code"
os.environ["ALLOWED_ORIGINS"] = "https://sawti.example.com"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", "")
os.environ.pop("ENV", None)
os.environ.pop("ENVIRONMENT", None)
os.environ["GROQ_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    from app.services import rate_limit
    rate_limit.clear_all()
    yield
    rate_limit.clear_all()


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


@pytest.fixture
def teacher_headers(client):
    r = client.post("/api/auth/teacher-login", json={"code": "test-teacher-code"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


needs_db = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="يتطلب TEST_DATABASE_URL (قاعدة Postgres للاختبار)",
)
