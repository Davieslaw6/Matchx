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

def test_readiness_checks_database_connectivity():
    response = client.get("/api/v1/health/ready")
    assert response.status_code in (200, 503)
    if response.status_code == 200:
        assert response.json()["checks"]["database"] == "ok"
    else:
        assert response.json()["checks"]["database"] == "unavailable"
