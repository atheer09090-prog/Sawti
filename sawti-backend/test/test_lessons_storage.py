# -*- coding: utf-8 -*-
"""
محتوى المعلم في PostgreSQL (content_store): البذر بالافتراضي، حفظ التعديلات،
عدم الكتابة على القرص، وسلوك الإنتاج بلا قاعدة بيانات.
"""
import os
import subprocess
import sys
import uuid

import pytest
from conftest import needs_db

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BACKEND_DIR, "app", "data")


def _db_fetch(key):
    from app.services import db
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT data FROM content_store WHERE key = %s", (key,))
            row = cur.fetchone()
            return row[0] if row else None
    finally:
        conn.close()


def _wipe(keys):
    from app.services import db
    db.ensure_table("content_store", "CREATE TABLE IF NOT EXISTS content_store (key TEXT PRIMARY KEY, data JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())")
    conn = db.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM content_store WHERE key = ANY(%s)", (list(keys),))
        conn.commit()
    finally:
        conn.close()


ALL_KEYS = ["speaking", "writing", "self_learning", "games", "dictation", "hamza_games", "hamza_journeys"]


@needs_db
def test_defaults_are_seeded_on_first_read(client):
    _wipe(ALL_KEYS)
    speaking = client.get("/api/lessons/speaking").json()
    assert {l["id"] for l in speaking} >= {"summer", "earth", "opinion"}
    writing = client.get("/api/lessons/writing").json()
    assert {t["id"] for t in writing} >= {"home", "neighborhood", "mosque"}
    assert len(client.get("/api/lessons/self-learning").json()["quiz"]) >= 3
    assert len(client.get("/api/lessons/dictation").json()) == 10
    assert set(client.get("/api/lessons/games").json()) == {"middle_hamza", "end_hamza", "quick_quiz"}
    assert set(client.get("/api/lessons/hamza-journeys").json())  # غير فارغ
    # البذر نفسه صار مخزَّنًا في القاعدة
    assert _db_fetch("speaking") is not None and _db_fetch("dictation") is not None


@needs_db
def test_hamza_games_seeded_from_shipped_file_and_file_not_modified(client):
    import json
    _wipe(["hamza_games"])
    shipped_path = os.path.join(DATA_DIR, "hamza_games.json")
    before = open(shipped_path, "rb").read()
    shipped = json.loads(before)
    data = client.get("/api/lessons/hamza-games").json()
    assert {k: len(v) for k, v in data.items()} == {k: len(v) for k, v in shipped.items()}
    assert data["l1_gate"][0]["word"] == shipped["l1_gate"][0]["word"]
    assert open(shipped_path, "rb").read() == before  # لم يُكتب عليه


@needs_db
def test_teacher_edits_persist_in_db_not_on_disk(client, teacher_headers):
    _wipe(["speaking"])
    files_before = set(os.listdir(DATA_DIR))
    lesson_id = "t-" + uuid.uuid4().hex[:8]
    body = {"id": lesson_id, "title": "درس تجريبي", "level": "سَهْلٌ", "icon": "🧪", "desc": "وصف", "topics": ["أ", "ب"]}

    assert client.post("/api/lessons/speaking", json=body, headers=teacher_headers).json() == {"ok": True}
    # تكرار المعرّف مرفوض
    assert client.post("/api/lessons/speaking", json=body, headers=teacher_headers).status_code == 400

    got = client.get("/api/lessons/speaking").json()
    assert lesson_id in [l["id"] for l in got]
    # الافتراضيات ما زالت موجودة بجانب الجديد
    assert {"summer", "earth", "opinion"} <= {l["id"] for l in got}
    # مخزَّن فعليًا في القاعدة (مصدر الحقيقة)، وبنفس شكل JSON
    stored = _db_fetch("speaking")
    assert any(l["id"] == lesson_id and l["topics"] == ["أ", "ب"] for l in stored)

    body["title"] = "عنوان معدّل"
    assert client.put(f"/api/lessons/speaking/{lesson_id}", json=body, headers=teacher_headers).status_code == 200
    assert next(l for l in client.get("/api/lessons/speaking").json() if l["id"] == lesson_id)["title"] == "عنوان معدّل"

    assert client.delete(f"/api/lessons/speaking/{lesson_id}", headers=teacher_headers).status_code == 200
    assert lesson_id not in [l["id"] for l in client.get("/api/lessons/speaking").json()]

    # لم يُنشأ أي ملف JSON على القرص
    assert set(os.listdir(DATA_DIR)) == files_before


@needs_db
def test_every_content_type_roundtrips_through_db(client, teacher_headers):
    _wipe(ALL_KEYS)
    H = teacher_headers
    # أسئلة التعلم الذاتي
    n = len(client.get("/api/lessons/self-learning").json()["quiz"])
    assert client.post("/api/lessons/self-learning/quiz", json={"q": "س؟", "options": ["أ", "ب"], "correct": 0}, headers=H).status_code == 200
    assert len(client.get("/api/lessons/self-learning").json()["quiz"]) == n + 1
    assert client.delete(f"/api/lessons/self-learning/quiz/{n}", headers=H).status_code == 200
    assert len(client.get("/api/lessons/self-learning").json()["quiz"]) == n

    # الألعاب
    g = {"q": "ن؟", "opts": ["أ", "ب"], "correct": "أ", "explain": "ش", "emoji": "✨"}
    k = len(client.get("/api/lessons/games").json()["quick_quiz"])
    assert client.post("/api/lessons/games/quick-quiz", json=g, headers=H).status_code == 200
    assert len(client.get("/api/lessons/games").json()["quick_quiz"]) == k + 1
    assert client.delete(f"/api/lessons/games/quick-quiz/{k}", headers=H).status_code == 200

    # الإملاء
    d = {"word": "كلمة", "type": "نوع", "correct": "كلمة", "opts": ["كلمة", "كلمه"], "hint": "تلميح"}
    m = len(client.get("/api/lessons/dictation").json())
    assert client.post("/api/lessons/dictation", json=d, headers=H).status_code == 200
    assert len(client.get("/api/lessons/dictation").json()) == m + 1
    assert client.delete(f"/api/lessons/dictation/{m}", headers=H).status_code == 200

    # ألعاب الهمزة
    h = len(client.get("/api/lessons/hamza-games").json()["l1_gate"])
    assert client.post("/api/lessons/hamza-games/l1_gate", json={"word": "ج", "isNabra": True, "reason": "ر"}, headers=H).status_code == 200
    assert len(client.get("/api/lessons/hamza-games").json()["l1_gate"]) == h + 1
    assert client.delete(f"/api/lessons/hamza-games/l1_gate/{h}", headers=H).status_code == 200
    assert client.post("/api/lessons/hamza-games/bad_key", json={}, headers=H).status_code == 400

    # رحلات الهمزة: تعديل ثم إعادة للافتراضي
    journeys = client.get("/api/lessons/hamza-journeys").json()
    jid = next(iter(journeys))
    original_rule = journeys[jid].get("rule")
    r = client.put(f"/api/lessons/hamza-journeys/{jid}", json={"rule": "قاعدة معدّلة"}, headers=H)
    assert r.status_code == 200
    assert client.get("/api/lessons/hamza-journeys").json()[jid]["rule"] == "قاعدة معدّلة"
    assert client.put(f"/api/lessons/hamza-journeys/{jid}/reset", headers=H).status_code == 200
    assert client.get("/api/lessons/hamza-journeys").json()[jid].get("rule") == original_rule


@needs_db
def test_default_dicts_in_code_are_not_mutated_by_edits(client, teacher_headers):
    from app.routers import lessons
    _wipe(["self_learning"])
    before = len(lessons.DEFAULT_SELF_LEARNING["quiz"])
    client.post("/api/lessons/self-learning/quiz", json={"q": "س؟", "options": ["أ", "ب"], "correct": 0}, headers=teacher_headers)
    assert len(lessons.DEFAULT_SELF_LEARNING["quiz"]) == before
    n = len(client.get("/api/lessons/self-learning").json()["quiz"])
    client.delete(f"/api/lessons/self-learning/quiz/{n - 1}", headers=teacher_headers)


def test_production_without_database_serves_defaults_but_rejects_edits():
    code = r'''
import os
from fastapi.testclient import TestClient
from main import app
c = TestClient(app)
tok = c.post("/api/auth/teacher-login", json={"code": "test-teacher-code"}).json()["token"]
h = {"Authorization": "Bearer " + tok}
r1 = c.get("/api/lessons/speaking")
r2 = c.post("/api/lessons/speaking", json={"id": "x1", "title": "t", "level": "l", "icon": "i", "desc": "d"}, headers=h)
print("GET", r1.status_code, len(r1.json()))
print("POST", r2.status_code)
content_files = {"lessons.json", "self_learning.json", "writing_games.json", "dictation.json", "hamza_journeys.json"}
print("LEAKED", sorted(content_files & set(os.listdir("app/data"))))
print("LOCAL", os.path.exists("app/data/local/speaking.json"))
'''
    env = {**os.environ, "ENVIRONMENT": "production", "DATABASE_URL": ""}
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, env=env, capture_output=True, text=True)
    assert "GET 200 3" in out.stdout, out.stdout + out.stderr
    assert "POST 503" in out.stdout, out.stdout + out.stderr
    assert "LEAKED []" in out.stdout, out.stdout     # لا ملفات محتوى على القرص
    assert "LOCAL False" in out.stdout, out.stdout   # ولا ملفات تطوير محلية في الإنتاج


@needs_db
def test_concurrent_teacher_edits_do_not_lose_updates(client, teacher_headers):
    """عشرون إضافة متزامنة لنفس القائمة: يجب أن تبقى كلها (بدون القفل كان بعضها يضيع)."""
    from concurrent.futures import ThreadPoolExecutor
    _wipe(["dictation"])
    start = len(client.get("/api/lessons/dictation").json())
    d = {"word": "ك", "type": "ن", "correct": "ك", "opts": ["ك", "ق"], "hint": "ت"}

    def add(_):
        return client.post("/api/lessons/dictation", json=d, headers=teacher_headers).status_code

    with ThreadPoolExecutor(max_workers=8) as ex:
        codes = list(ex.map(add, range(20)))
    assert set(codes) == {200}
    assert len(client.get("/api/lessons/dictation").json()) == start + 20
