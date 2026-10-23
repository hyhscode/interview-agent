from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

def test_healthz_returns_ok():
    response = client.get("/healthz")

    assert response.status_code ==200
    assert response.json()["status"] == "ok"

def test_healthz_writes_request_id_header():
    response = client.get("/healthz")

    assert "x-request-id" in response.headers
    assert len(response.headers["x-request-id"]) == 8
