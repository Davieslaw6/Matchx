from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_fixture_explorer_requires_owner_session():
    response = client.get("/api/v1/fixtures")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "authentication_required"
