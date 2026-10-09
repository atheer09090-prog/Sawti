# -*- coding: utf-8 -*-
"""
اختبارات تحتاج قاعدة Postgres (TEST_DATABASE_URL): تسجيل/دخول الطلاب،
عزل سجلات الطلاب عن بعضهم، وملكية تعليق المعلم، وSUS.

تشغيل محلي:
    TEST_DATABASE_URL="postgresql://user:pass@localhost:5432/sawti_test?sslmode=disable" pytest
"""
import uuid
import pytest
from conftest import needs_db

pytestmark = needs_db


def _email():
    return f"t-{uuid.uuid4().hex[:10]}@example.com"


def register(client, name="طالب", grade="السادس", password="secret123", email=None):
    email = email or _email()
    r = client.post("/api/auth/register", json={
        "name": name, "grade": grade, "email": email, "password": password})
    assert r.status_code == 200, r.text
    d = r.json()
    return d["user"]["id"], {"Authorization": f"Bearer {d['token']}"}, email


# ═════════════ التسجيل والدخول ═════════════

def test_register_then_login(client):
    uid, headers, email = register(client)
    r = client.post("/api/auth/login", json={"email": email, "password": "secret123"})
    assert r.status_code == 200
    assert r.json()["user"]["id"] == uid
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["email"] == email


def test_login_wrong_password(client):
    _, _, email = register(client)
    r = client.post("/api/auth/login", json={"email": email, "password": "not-it"})
    assert r.status_code == 401


def test_login_unknown_email(client):
    r = client.post("/api/auth/login", json={"email": _email(), "password": "whatever1"})
    assert r.status_code == 404


def test_duplicate_email_rejected(client):
    _, _, email = register(client)
    r = client.post("/api/auth/register", json={
        "name": "آخر", "grade": "السادس", "email": email, "password": "secret123"})
    assert r.status_code == 409


def test_short_password_rejected(client):
    r = client.post("/api/auth/register", json={
        "name": "طالب", "grade": "السادس", "email": _email(), "password": "123"})
    assert r.status_code == 422


def test_guest_login_gets_working_student_token(client):
    r = client.post("/api/auth/guest-login")
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.get("/api/students/me", headers=headers).status_code == 200


# ═════════════ عزل الطلاب ═════════════

def test_student_cannot_see_or_change_another_students_record(client, teacher_headers):
    uid_a, ha, _ = register(client, name="أ")
    uid_b, hb, _ = register(client, name="ب")

    assert client.put("/api/students/me", json={"name": "أ", "grade": "السادس", "points": 50}, headers=ha).status_code == 200
    # /me يعيد سجل صاحب الرمز فقط
    assert client.get("/api/students/me", headers=ha).json()["points"] == 50
    assert client.get("/api/students/me", headers=hb).json() is None

    # لا يوجد أي مسار للطالب يسمح بتحديد مستخدم آخر
    assert client.get("/api/students", headers=hb).status_code == 403
    assert client.get("/api/students/أ/السادس", headers=hb).status_code == 403
    assert client.put("/api/students/أ/السادس", json={"points": 9999}, headers=hb).status_code == 403
    assert client.put("/api/students/by-key", json={"key": uid_a, "data": {"teacherComment": "x"}}, headers=hb).status_code == 403

    # سجل أ لم يتغير
    assert client.get("/api/students/me", headers=ha).json()["points"] == 50


def test_teacher_lists_students_with_keys(client, teacher_headers):
    uid, h, _ = register(client, name="ج")
    client.put("/api/students/me", json={"name": "ج", "grade": "السادس"}, headers=h)
    r = client.get("/api/students", headers=teacher_headers)
    assert r.status_code == 200
    assert uid in [row["_key"] for row in r.json()]


def test_teacher_comment_survives_student_autosave_and_cannot_be_forged(client, teacher_headers):
    uid, h, _ = register(client, name="د")
    client.put("/api/students/me", json={"name": "د", "grade": "السادس", "points": 10}, headers=h)

    # المعلم يكتب تعليقًا
    r = client.put("/api/students/by-key", json={"key": uid, "data": {"teacherComment": "أحسنت"}}, headers=teacher_headers)
    assert r.status_code == 200

    # الطالب يحفظ تلقائيًا بنسخة قديمة (تعليق فارغ) وحاول أيضًا تزوير تعليق
    client.put("/api/students/me", json={"name": "د", "grade": "السادس", "points": 20,
                                         "teacherComment": "تعليق مزوَّر"}, headers=h)
    rec = client.get("/api/students/me", headers=h).json()
    assert rec["teacherComment"] == "أحسنت"
    assert rec["points"] == 20


def test_teacher_comment_does_not_overwrite_student_progress(client, teacher_headers):
    uid, h, _ = register(client, name="هـ")
    client.put("/api/students/me", json={"name": "هـ", "grade": "السادس", "points": 70}, headers=h)
    # المعلم يرسل نسخة قديمة فيها نقاط أقل
    client.put("/api/students/by-key", json={"key": uid, "data": {"name": "هـ", "points": 1, "teacherComment": "جيد"}},
               headers=teacher_headers)
    rec = client.get("/api/students/me", headers=h).json()
    assert rec["points"] == 70 and rec["teacherComment"] == "جيد"


def test_by_key_unknown_key_404(client, teacher_headers):
    r = client.put("/api/students/by-key", json={"key": "nope-" + uuid.uuid4().hex, "data": {"teacherComment": "x"}},
                   headers=teacher_headers)
    assert r.status_code == 404


def test_student_record_size_limit(client):
    _, h, _ = register(client)
    big = {"name": "ز", "grade": "السادس", "blob": "x" * (300 * 1024)}
    assert client.put("/api/students/me", json=big, headers=h).status_code == 413


# ═════════════ SUS ═════════════

def test_sus_student_submit_and_teacher_only_reports(client, teacher_headers):
    _, h, _ = register(client, name="و")
    assert client.post("/api/sus", json={"answers": [5, 1] * 5}, headers=h).json()["score"] == 100.0
    assert client.get("/api/sus/me", headers=h).json()["score"] == 100.0

    # الطالب لا يرى التصدير/الملخص/التقرير
    for path in ("export", "summary", "report"):
        assert client.get(f"/api/sus/{path}", headers=h).status_code == 403
        assert client.get(f"/api/sus/{path}").status_code == 401

    assert client.get("/api/sus/export", headers=teacher_headers).status_code == 200
    assert client.get("/api/sus/summary", headers=teacher_headers).json()["count"] >= 1
    assert client.get("/api/sus/report", headers=teacher_headers).status_code == 200


# ═════════════ التقييمات القديمة ═════════════

def test_reviews_student_post_teacher_get(client, teacher_headers, tmp_path, monkeypatch):
    from app.routers import reviews
    monkeypatch.setattr(reviews, "REVIEWS_FILE", str(tmp_path / "reviews.json"))  # لا نلوّث app/data
    _, h, _ = register(client)
    body = {"student": "ز", "quality": 5, "ease": 4, "benefit": 5, "comment": "ممتاز"}
    assert client.post("/api/reviews", json=body).status_code == 401
    assert client.post("/api/reviews", json=body, headers=h).status_code == 200
    assert client.get("/api/reviews", headers=h).status_code == 403
    assert client.get("/api/reviews", headers=teacher_headers).status_code == 200


# ═════════════ حدود المحاولات ═════════════

def test_login_failures_are_throttled_per_email_but_success_resets(client):
    _, _, email = register(client)
    for _ in range(8):
        assert client.post("/api/auth/login", json={"email": email, "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "wrong-pass"}).status_code == 429
    # حتى كلمة المرور الصحيحة مرفوضة أثناء الحظر
    assert client.post("/api/auth/login", json={"email": email, "password": "secret123"}).status_code == 429


def test_successful_logins_do_not_trigger_throttle(client):
    _, _, email = register(client)
    for _ in range(25):
        assert client.post("/api/auth/login", json={"email": email, "password": "secret123"}).status_code == 200
