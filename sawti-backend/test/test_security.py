# -*- coding: utf-8 -*-
"""
اختبارات الأمان: جلسة المعلم (JWT)، رفض الرموز غير الصالحة، فصل الأدوار،
حماية مسارات المعلم، CORS، وفشل الإقلاع في الإنتاج بلا JWT_SECRET.
"""
import os
import subprocess
import sys
import time

import jwt
import pytest

from conftest import needs_db
from app.services import security
from app.services.security import create_token, JWT_SECRET, JWT_ALGORITHM

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def student_headers(user_id="u-test-1"):
    return bearer(create_token(user_id))


# ═════════════ دخول المعلم ═════════════

def test_teacher_login_returns_teacher_jwt(client):
    r = client.post("/api/auth/teacher-login", json={"code": "test-teacher-code"})
    assert r.status_code == 200
    body = r.json()
    payload = jwt.decode(body["token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert payload["role"] == "teacher"
    # ~8 ساعات
    assert 7.9 * 3600 < payload["exp"] - time.time() <= 8 * 3600 + 5
    assert body["expires_in"] == 8 * 3600


def test_teacher_login_wrong_code(client):
    assert client.post("/api/auth/teacher-login", json={"code": "wrong"}).status_code == 401
    assert client.post("/api/auth/teacher-login", json={}).status_code == 401


def test_old_default_code_is_not_accepted(client):
    assert client.post("/api/auth/teacher-login", json={"code": "sawti2026"}).status_code == 401


def test_teacher_login_disabled_when_code_missing(client, monkeypatch):
    monkeypatch.delenv("TEACHER_ACCESS_CODE", raising=False)
    r = client.post("/api/auth/teacher-login", json={"code": "anything"})
    assert r.status_code == 503
    r = client.post("/api/auth/teacher-login", json={"code": ""})
    assert r.status_code == 503


def test_teacher_login_is_rate_limited_after_failures(client):
    for _ in range(5):
        assert client.post("/api/auth/teacher-login", json={"code": "bad"}).status_code == 401
    # السادسة محظورة حتى بالرمز الصحيح
    assert client.post("/api/auth/teacher-login", json={"code": "bad"}).status_code == 429
    assert client.post("/api/auth/teacher-login", json={"code": "test-teacher-code"}).status_code == 429


# ═════════════ JWT غير صالح / منتهٍ ═════════════

def _forge(role, exp_delta, secret=JWT_SECRET, sub="x"):
    return jwt.encode({"sub": sub, "role": role, "exp": int(time.time()) + exp_delta},
                      secret, algorithm=JWT_ALGORITHM)


@pytest.mark.parametrize("token", [
    "not-a-jwt",
    "",
    _forge("teacher", -10),                       # منتهٍ
    _forge("teacher", 3600, secret="other-key-0123456789abcdef0123456789"),  # توقيع خاطئ
])
def test_invalid_or_expired_teacher_token_rejected(client, token):
    r = client.get("/api/students", headers=bearer(token))
    assert r.status_code == 401


def test_expired_student_token_rejected(client):
    r = client.get("/api/students/me", headers=bearer(_forge("student", -10)))
    assert r.status_code == 401


def test_alg_none_token_rejected(client):
    forged = jwt.encode({"sub": "teacher", "role": "teacher", "exp": int(time.time()) + 3600},
                        key=None, algorithm="none")
    assert client.get("/api/students", headers=bearer(forged)).status_code == 401


def test_legacy_student_token_without_role_still_valid_as_student():
    old = jwt.encode({"sub": "legacy-user", "exp": int(time.time()) + 3600}, JWT_SECRET, algorithm=JWT_ALGORITHM)
    assert security.decode_token(old) == "legacy-user"


def test_teacher_token_is_not_a_student_token(client, teacher_headers):
    assert client.get("/api/students/me", headers=teacher_headers).status_code == 401
    assert client.post("/api/sus", json={"answers": [3] * 10}, headers=teacher_headers).status_code == 401


# ═════════════ مسارات المعلم ترفض غير المعلم ═════════════

TEACHER_ONLY_ENDPOINTS = [
    ("GET", "/api/students"),
    ("PUT", "/api/students/by-key"),
    ("GET", "/api/students/اسم/الصف"),
    ("PUT", "/api/students/اسم/الصف"),
    ("GET", "/api/sus/export"),
    ("GET", "/api/sus/report"),
    ("GET", "/api/sus/summary"),
    ("POST", "/api/reports/student"),
    ("GET", "/api/reviews"),
    ("POST", "/api/lessons/speaking"),
    ("PUT", "/api/lessons/speaking/summer"),
    ("DELETE", "/api/lessons/speaking/summer"),
    ("POST", "/api/lessons/writing"),
    ("PUT", "/api/lessons/writing/home"),
    ("DELETE", "/api/lessons/writing/home"),
    ("POST", "/api/lessons/self-learning/quiz"),
    ("DELETE", "/api/lessons/self-learning/quiz/0"),
    ("POST", "/api/lessons/games/middle-hamza"),
    ("DELETE", "/api/lessons/games/quick-quiz/0"),
    ("POST", "/api/lessons/dictation"),
    ("PUT", "/api/lessons/dictation/0"),
    ("DELETE", "/api/lessons/dictation/0"),
    ("POST", "/api/lessons/hamza-games/l1_gate"),
    ("DELETE", "/api/lessons/hamza-games/l1_gate/0"),
    ("PUT", "/api/lessons/hamza-journeys/treasure"),
    ("PUT", "/api/lessons/hamza-journeys/treasure/reset"),
]


@pytest.mark.parametrize("method,path", TEACHER_ONLY_ENDPOINTS)
def test_teacher_endpoints_reject_anonymous(client, method, path):
    r = client.request(method, path, json={})
    assert r.status_code == 401, f"{method} {path} → {r.status_code}"


@pytest.mark.parametrize("method,path", TEACHER_ONLY_ENDPOINTS)
def test_teacher_endpoints_reject_student(client, method, path):
    r = client.request(method, path, json={}, headers=student_headers())
    assert r.status_code == 403, f"{method} {path} → {r.status_code}"


def test_every_lessons_mutation_route_requires_teacher():
    """شبكة أمان: أي مسار تعديل جديد في lessons بلا require_teacher يُفشل هذا الاختبار."""
    from app.routers import lessons
    from app.services.current_user import require_teacher
    unprotected = []
    checked = 0
    for route in lessons.router.routes:
        methods = getattr(route, "methods", set()) or set()
        for m in methods - {"GET", "HEAD", "OPTIONS"}:
            checked += 1
            deps = [d.call for d in route.dependant.dependencies]
            if require_teacher not in deps:
                unprotected.append(f"{m} {route.path}")
    assert checked >= 25
    assert not unprotected, unprotected


def test_lessons_get_endpoints_remain_public_for_students(client):
    # لا مصادقة مطلوبة للقراءة (يستفيد منها الطالب). النتيجة 200 بغض النظر عن مصدر التخزين.
    for path in ("speaking", "writing", "self-learning", "games", "dictation", "hamza-games", "hamza-journeys"):
        r = client.get(f"/api/lessons/{path}")
        assert r.status_code == 200, f"{path} → {r.status_code}"


def test_teacher_can_pass_the_gate(client, teacher_headers):
    # مثال لا يحتاج قاعدة بيانات: تقرير PDF
    r = client.post("/api/reports/student", json={"name": "طالب", "grade": "السادس"}, headers=teacher_headers)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


# ═════════════ CORS ═════════════

def test_cors_allows_configured_origin(client):
    r = client.options("/api/health", headers={
        "Origin": "https://sawti.example.com", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "https://sawti.example.com"


def test_cors_blocks_unknown_origin(client):
    r = client.options("/api/health", headers={
        "Origin": "https://evil.example.org", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in r.headers
    r = client.get("/api/health", headers={"Origin": "https://evil.example.org"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_localhost_allowed_only_in_development(client):
    r = client.options("/api/health", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"

    code = (
        "from fastapi.testclient import TestClient; from main import app;"
        "c=TestClient(app);"
        "r=c.options('/api/health',headers={'Origin':'http://localhost:5173','Access-Control-Request-Method':'GET'});"
        "print('ALLOW=' + str(r.headers.get('access-control-allow-origin')))"
    )
    env = {**os.environ, "ENVIRONMENT": "production"}
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True)
    assert "ALLOW=None" in out.stdout, out.stdout + out.stderr


# ═════════════ الإقلاع في الإنتاج ═════════════

def test_production_startup_fails_without_jwt_secret():
    env = {k: v for k, v in os.environ.items() if k != "JWT_SECRET"}
    env["ENVIRONMENT"] = "production"
    out = subprocess.run([sys.executable, "-c", "import main"], cwd=BACKEND_DIR, env=env,
                         capture_output=True, text=True)
    assert out.returncode != 0
    assert "JWT_SECRET" in out.stderr


def test_production_startup_ok_with_jwt_secret():
    env = {**os.environ, "ENVIRONMENT": "production", "ENV": "production"}
    out = subprocess.run([sys.executable, "-c", "import main; print('OK')"], cwd=BACKEND_DIR, env=env,
                         capture_output=True, text=True)
    assert out.returncode == 0 and "OK" in out.stdout, out.stderr


def test_no_hardcoded_teacher_code_in_source():
    for root, _, files in os.walk(os.path.join(BACKEND_DIR, "app")):
        for f in files:
            if f.endswith(".py"):
                with open(os.path.join(root, f), encoding="utf-8") as fh:
                    assert "sawti2026" not in fh.read(), f
