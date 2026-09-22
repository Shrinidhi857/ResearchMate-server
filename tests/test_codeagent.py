"""tests/test_codeagent.py – LaTeX Code Agent REST endpoint tests."""

from unittest.mock import patch, AsyncMock


# ── GET /codeagent ────────────────────────────────────────────────────────────

def test_codeagent_root(client):
    resp = client.get("/codeagent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service"] == "LaTeX Agent API"
    assert data["status"] == "running"
    assert "active_sessions" in data
    assert "endpoints" in data


# ── GET /codeagent/health ─────────────────────────────────────────────────────

@patch("app.codeagent.routes.llm")
def test_codeagent_health(mock_llm, client):
    """Mock the LLM generate call so no real API key is needed."""
    mock_llm.generate = AsyncMock(return_value="pong")
    resp = client.get("/codeagent/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "llm_status" in data
    assert "active_sessions" in data
    assert "timestamp" in data


# ── GET /codeagent/sessions ───────────────────────────────────────────────────

def test_codeagent_sessions(client):
    resp = client.get("/codeagent/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "active_sessions" in data
    assert isinstance(data["active_sessions"], list)
    assert "total" in data


# ── WebSocket endpoint presence (smoke test) ──────────────────────────────────

def test_websocket_route_registered(client):
    """Verify the WebSocket route /ws/{client_id}/{project_id} is registered
    by checking the app routes list — no actual WS handshake needed."""
    from app.main import app
    ws_routes = [
        route for route in app.routes
        if hasattr(route, "path") and "/ws/" in route.path
    ]
    assert len(ws_routes) > 0, "WebSocket route /ws/{client_id}/{project_id} not found"
