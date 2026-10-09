# -*- coding: utf-8 -*-
"""شفافية خط STT: raw_transcript خام فعلًا، وحالة تصحيح Gemini صريحة (مع mock لـGroq/Gemini)."""
import uuid
from app.services.security import create_token
from app.routers import evaluation

WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 3000


def _post(client):
    h = {"Authorization": f"Bearer {create_token('u-' + uuid.uuid4().hex)}"}
    return client.post("/api/eval/speech", files={"audio_file": ("r.webm", WEBM, "audio/webm")}, headers=h)


def test_raw_transcript_is_whisper_output_and_fallback_is_flagged(client, monkeypatch):
    monkeypatch.setattr(evaluation, "transcribe_arabic_audio_detailed",
                        lambda *a, **k: {"whisper_text": "قال الولد كلمه", "rules_text": "قال الولد كلمة"})
    monkeypatch.setattr(evaluation, "correct_stt_errors",
                        lambda t, topic_hint="": {"correctedText": t, "corrections": [], "status": "failed_http"})
    r = _post(client)
    assert r.status_code == 200
    d = r.json()
    assert d["raw_transcript"] == "قال الولد كلمه"            # خام فعلًا
    assert d["canonical_transcript"] == "قال الولد كلمة"      # النص الأصلي يُستخدم عند فشل Gemini
    assert d["stt_corrections"] == []
    assert d["stt_pipeline"] == {"phonetic_rules_changed_text": True,
                                 "ai_correction_status": "failed_http", "ai_correction_applied": False}


def test_applied_correction_is_reported(client, monkeypatch):
    monkeypatch.setattr(evaluation, "transcribe_arabic_audio_detailed",
                        lambda *a, **k: {"whisper_text": "ذهب الولد", "rules_text": "ذهب الولد"})
    fix = {"correctedText": "ذهب الوالد", "status": "applied",
           "corrections": [{"wrong": "الولد", "correct": "الوالد", "confidence": 0.95}]}
    monkeypatch.setattr(evaluation, "correct_stt_errors", lambda t, topic_hint="": fix)
    d = _post(client).json()
    assert d["raw_transcript"] == "ذهب الولد" and d["canonical_transcript"] == "ذهب الوالد"
    assert d["stt_pipeline"]["ai_correction_applied"] is True
    assert d["stt_corrections"][0]["wrong"] == "الولد"


def test_correct_stt_errors_status_without_api_key(monkeypatch):
    from app.services.speech_eval import correct_stt_errors
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    out = correct_stt_errors("ذهب الولد")
    assert out["correctedText"] == "ذهب الولد" and out["status"] == "skipped_no_api_key"
