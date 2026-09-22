"""tests/test_analyse.py – NLP document analysis endpoint tests."""

import uuid
from unittest.mock import patch, MagicMock


# ── POST /api/nlp ─────────────────────────────────────────────────────────────

def test_nlp_start_analysis(client, auth_headers, test_document):
    resp = client.post(
        "/api/nlp",
        json=[{"doc_id": test_document}],
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data


def test_nlp_missing_body(client, auth_headers):
    resp = client.post("/api/nlp", json=None, headers=auth_headers)
    assert resp.status_code in (400, 422)


def test_nlp_wrong_body_type(client, auth_headers):
    # Endpoint expects a list, not a dict
    resp = client.post("/api/nlp", json={"doc_id": "abc"}, headers=auth_headers)
    assert resp.status_code == 400


def test_nlp_unauthenticated(client, test_document):
    resp = client.post("/api/nlp", json=[{"doc_id": test_document}])
    assert resp.status_code == 401


# ── GET /api/nlp/stream/{session_id} ─────────────────────────────────────────

def test_nlp_stream_invalid_session(client):
    fake_id = str(uuid.uuid4())
    resp = client.get(f"/api/nlp/stream/{fake_id}")
    assert resp.status_code == 404


def test_nlp_stream_valid_session(client, auth_headers, test_document):
    """Start a session then verify the SSE stream opens with correct content-type."""
    start_resp = client.post(
        "/api/nlp",
        json=[{"doc_id": test_document}],
        headers=auth_headers,
    )
    session_id = start_resp.json()["session_id"]

    # Mock the LLM to avoid real API calls during streaming
    with patch("app.analyse.routes.ChatGoogleGenerativeAI") as MockLLM:
        mock_chain_result = "Mocked summary of the document."
        mock_llm_instance = MagicMock()
        MockLLM.return_value = mock_llm_instance

        # Patch the chain invocation
        with patch("langchain_core.runnables.base.RunnableSequence.invoke",
                   return_value=mock_chain_result):
            with client.stream("GET", f"/api/nlp/stream/{session_id}") as resp:
                assert resp.status_code == 200
                assert "text/event-stream" in resp.headers.get("content-type", "")
                # Read first event to confirm stream starts
                first_line = next(
                    (line for line in resp.iter_lines() if line.startswith("data:")),
                    None,
                )
                assert first_line is not None
