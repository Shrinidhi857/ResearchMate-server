"""tests/test_rag.py – RAG (RAPTOR) endpoint tests with mocked pipeline."""

from unittest.mock import patch, MagicMock


# ── POST /api/analyse ─────────────────────────────────────────────────────────

@patch("app.rag.routes.RaptorPipeline")
def test_raptor_analyse_success(MockRaptor, client, auth_headers, test_document):
    MockRaptor.return_value = MagicMock()
    resp = client.post(
        "/api/analyse",
        json=[{"doc_id": test_document, "content": "Some research content."}],
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "analysed" in resp.json()["message"].lower()


def test_raptor_analyse_empty_body(client, auth_headers):
    resp = client.post("/api/analyse", json=[], headers=auth_headers)
    assert resp.status_code == 400


def test_raptor_analyse_unauthenticated(client):
    resp = client.post("/api/analyse", json=[{"doc_id": "abc"}])
    assert resp.status_code == 401


@patch("app.rag.routes.RaptorPipeline", side_effect=Exception("Embedding error"))
def test_raptor_analyse_pipeline_error(MockRaptor, client, auth_headers, test_document):
    resp = client.post(
        "/api/analyse",
        json=[{"doc_id": test_document}],
        headers=auth_headers,
    )
    assert resp.status_code == 500


# ── POST /api/ask ─────────────────────────────────────────────────────────────

def test_raptor_ask_no_context(client, auth_headers):
    """When no document has been analysed, retriever is None → 500."""
    # Reset the module-level retriever to None
    import app.rag.routes as rag_routes
    rag_routes.retriever = None

    resp = client.post(
        "/api/ask",
        json={"question": "What are the findings?"},
        headers=auth_headers,
    )
    assert resp.status_code == 500
    assert "no document context" in resp.json()["message"].lower()


@patch("app.rag.routes.asking_llm", return_value="Mocked RAG answer.")
@patch("app.rag.routes.RaptorPipeline")
def test_raptor_ask_with_context(MockRaptor, mock_ask, client, auth_headers, test_document):
    """Set up the retriever then ask a question."""
    import app.rag.routes as rag_routes
    rag_routes.retriever = MagicMock()

    resp = client.post(
        "/api/ask",
        json={"question": "What are the key findings?"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Success"
    assert data["answer"] == "Mocked RAG answer."


def test_raptor_ask_unauthenticated(client):
    resp = client.post("/api/ask", json={"question": "Tell me something."})
    assert resp.status_code == 401
