"""tests/test_health.py – Health check endpoint tests."""


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_body(client):
    response = client.get("/health")
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
