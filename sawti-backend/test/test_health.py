"""فحص الصحة يجب أن يتحقق من قاعدة البيانات قبل أن تعلن المراقبة أن الخادم سليم."""
import main


def test_health_reports_database_connection(client, monkeypatch):
    monkeypatch.setattr(main.db, "is_configured", lambda: True)
    monkeypatch.setattr(main.db, "ping", lambda: True)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["database"] == "connected"


def test_health_returns_unavailable_when_database_is_down(client, monkeypatch):
    monkeypatch.setattr(main.db, "is_configured", lambda: True)
    monkeypatch.setattr(main.db, "ping", lambda: False)

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
