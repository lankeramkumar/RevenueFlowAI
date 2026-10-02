from fastapi.testclient import TestClient

from revenueflowai.main import app


def test_healthz_does_not_require_auth_or_database():
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
