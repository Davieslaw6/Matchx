from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_liveness_is_available():
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_request_id_and_security_headers_are_set():
    response = client.get("/api/v1/health/live", headers={"X-Request-ID":"test-request-123"})
    assert response.headers["X-Request-ID"] == "test-request-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"

def test_readiness_does_not_claim_database_is_ready():
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
