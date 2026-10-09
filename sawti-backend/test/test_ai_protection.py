# -*- coding: utf-8 -*-
"""
حماية مسارات /api/eval/* : مصادقة، حدود طول النص وحجم الصوت، نوع الملف،
تحديد المعدل لكل مستخدم، وعدم تحويل الفشل إلى نجاح وهمي.
لا تحتاج قاعدة بيانات ولا مفاتيح Groq/Gemini (تُفرَّغ في conftest).
"""
import uuid
import pytest
from app.services.security import create_token

TEXT_ENDPOINTS = [
    ("/api/eval/diacritize", {"text": "ذهب الولد"}),
    ("/api/eval/spellcheck", {"text": "ذهب الولد", "use_ai": False}),
    ("/api/eval/context", {"text": "ذهب الولد"}),
    ("/api/eval/writing", {"text": "ذهب الولد إلى المدرسة"}),
    ("/api/eval/ask", {"question": "ما هي الهمزة؟"}),
]
WEBM_HEADER = b"\x1a\x45\xdf\xa3" + b"\x00" * 3000


def new_student():
    return {"Authorization": f"Bearer {create_token('u-' + uuid.uuid4().hex)}"}


def speech(client, headers, content=WEBM_HEADER, ctype="audio/webm", name="r.webm", params=None):
    return client.post("/api/eval/speech", files={"audio_file": (name, content, ctype)},
                       headers=headers, params=params or {})


# ═════════════ المصادقة ═════════════

@pytest.mark.parametrize("path,body", TEXT_ENDPOINTS)
def test_text_endpoints_require_login(client, path, body):
    assert client.post(path, json=body).status_code == 401
    assert client.post(path, json=body, headers={"Authorization": "Bearer junk"}).status_code == 401


def test_speech_requires_login(client):
    assert speech(client, {}).status_code == 401


def test_student_and_teacher_tokens_are_both_accepted(client, teacher_headers):
    body = {"text": "ذهب الولد إلى المدرسة"}
    assert client.post("/api/eval/writing", json=body, headers=new_student()).status_code == 200
    assert client.post("/api/eval/writing", json=body, headers=teacher_headers).status_code == 200


# ═════════════ حدود الطول ═════════════

@pytest.mark.parametrize("path,key", [
    ("/api/eval/diacritize", "text"), ("/api/eval/spellcheck", "text"),
    ("/api/eval/context", "text"), ("/api/eval/writing", "text"),
])
def test_text_length_limit(client, path, key):
    h = new_student()
    assert client.post(path, json={key: "ا" * 5000}, headers=h).status_code != 413      # عند الحد مقبول
    r = client.post(path, json={key: "ا" * 5001}, headers=h)
    assert r.status_code == 413
    assert "أطول من المسموح" in r.json()["detail"]


def test_question_length_limit(client):
    r = client.post("/api/eval/ask", json={"question": "س" * 501}, headers=new_student())
    assert r.status_code == 413


def test_oversized_json_body_rejected_early(client):
    r = client.post("/api/eval/writing", content=b"x" * (3 * 1024 * 1024),
                    headers={**new_student(), "Content-Type": "application/json"})
    assert r.status_code == 413


# ═════════════ الصوت ═════════════

def test_speech_rejects_disallowed_content_type(client):
    r = speech(client, new_student(), content=b"%PDF-1.4" + b"0" * 3000, ctype="application/pdf", name="x.pdf")
    assert r.status_code == 400 and "غير مدعومة" in r.json()["detail"]


def test_speech_rejects_fake_audio_content(client):
    # Content-Type صوتي لكن المحتوى ليس صوتًا
    r = speech(client, new_student(), content=b"<html>not audio at all</html>" * 100)
    assert r.status_code == 400 and "ليس تسجيلًا صوتيًا" in r.json()["detail"]


def test_speech_rejects_tiny_file(client):
    r = speech(client, new_student(), content=b"\x1a\x45\xdf\xa3tiny")
    assert r.status_code == 400


def test_speech_rejects_oversized_audio_with_clear_message(client):
    big = WEBM_HEADER + b"\x00" * (10 * 1024 * 1024)          # أكبر من 10MB وأصغر من 12MB
    r = speech(client, new_student(), content=big)
    assert r.status_code == 413 and "التسجيل أكبر من المسموح" in r.json()["detail"]


def test_speech_rejects_huge_upload_before_processing(client):
    huge = WEBM_HEADER + b"\x00" * (13 * 1024 * 1024)
    assert speech(client, new_student(), content=huge).status_code == 413


def test_speech_long_reference_text_rejected(client):
    r = speech(client, new_student(), params={"reference_text": "ع" * 501})
    assert r.status_code == 413


def test_speech_provider_failure_returns_generic_error_not_fake_score(client):
    # صوت صالح الشكل، لكن لا مفتاح Groq في الاختبار → فشل المزوّد
    r = speech(client, new_student())
    assert r.status_code == 500
    detail = r.json()["detail"]
    assert "لم تُحتسب نتيجة" in detail
    assert "overall" not in r.json()
    low = detail.lower()
    assert "groq" not in low and "api_key" not in low and "traceback" not in low


# ═════════════ الفشل لا يصير نجاحًا وهميًا ═════════════

def test_ask_returns_503_when_ai_unavailable_instead_of_apology_as_answer(client):
    r = client.post("/api/eval/ask", json={"question": "ما الهمزة؟"}, headers=new_student())
    assert r.status_code == 503
    assert "answer" not in r.json()


# ═════════════ تحديد المعدل ═════════════

def test_rate_limit_per_user_and_isolated_between_users(client):
    a, b = new_student(), new_student()
    for _ in range(20):
        assert client.post("/api/eval/ask", json={"question": "س"}, headers=a).status_code in (200, 503)
    r = client.post("/api/eval/ask", json={"question": "س"}, headers=a)
    assert r.status_code == 429 and "Retry-After" in r.headers
    # مستخدم آخر لا يتأثر
    assert client.post("/api/eval/ask", json={"question": "س"}, headers=b).status_code in (200, 503)


def test_speech_rate_limit(client):
    h = new_student()
    for _ in range(15):
        assert speech(client, h, content=b"x" * 2000).status_code == 400
    assert speech(client, h, content=b"x" * 2000).status_code == 429


def test_normal_usage_is_not_throttled(client):
    h = new_student()
    for _ in range(10):  # طالب يعيد تقييم كتابته عدة مرات
        assert client.post("/api/eval/writing", json={"text": "ذهب الولد إلى المدرسة"}, headers=h).status_code == 200
