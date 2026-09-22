"""tests/test_ai.py – AI feature endpoint tests (LLM calls mocked)."""

from unittest.mock import patch


# ── Summarize ─────────────────────────────────────────────────────────────────

@patch("app.ai.routes.summarize_research_paper")
def test_summarize_success(mock_summarize, client, auth_headers):
    mock_summarize.return_value = {"success": True, "data": "Mocked structured summary."}
    resp = client.post(
        "/api/summarize",
        json={"text": "This is a research paper about deep learning."},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert data["summary"] == "Mocked structured summary."


@patch("app.ai.routes.summarize_research_paper")
def test_summarize_llm_error(mock_summarize, client, auth_headers):
    mock_summarize.return_value = {"success": False, "error": "LLM unavailable"}
    resp = client.post(
        "/api/summarize",
        json={"text": "Some text to summarize."},
        headers=auth_headers,
    )
    assert resp.status_code == 500


def test_summarize_missing_text(client, auth_headers):
    resp = client.post("/api/summarize", json={}, headers=auth_headers)
    assert resp.status_code == 400


def test_summarize_unauthenticated(client):
    resp = client.post("/api/summarize", json={"text": "Hello"})
    assert resp.status_code == 401


# ── Auto Cite ─────────────────────────────────────────────────────────────────

def test_auto_cite_success(client, auth_headers):
    resp = client.post(
        "/api/auto_cite",
        json={
            "paragraph": "Neural networks have revolutionized deep learning.",
            "references": {"ref1": ["neural networks", "deep learning"]},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "cited_paragraph" in data
    # Citations should be inserted
    assert "[ref1]" in data["cited_paragraph"]


def test_auto_cite_missing_fields(client, auth_headers):
    resp = client.post(
        "/api/auto_cite",
        json={"paragraph": "Only paragraph, no references."},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_auto_cite_unauthenticated(client):
    resp = client.post("/api/auto_cite", json={"paragraph": "x", "references": {}})
    assert resp.status_code == 401


# ── SSE Test Stream ───────────────────────────────────────────────────────────

def test_test_stream_returns_event_stream(client):
    """Verify the SSE endpoint responds with text/event-stream content type."""
    with client.stream("GET", "/api/test") as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        # Consume first chunk to confirm data flows
        first_chunk = next(resp.iter_lines())
        assert first_chunk.startswith("data:")


# ── Start Analysis ────────────────────────────────────────────────────────────

def test_start_analysis(client):
    resp = client.post("/api/start", json={"topic": "AI in healthcare"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
