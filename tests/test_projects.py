"""tests/test_projects.py – Project collaboration endpoint tests."""

import pytest
from unittest.mock import patch, MagicMock


# ── Create & List ─────────────────────────────────────────────────────────────

def test_create_project_success(client, auth_headers):
    resp = client.post(
        "/api/projects/create",
        json={"project_name": "My Research Project"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert "project_id" in resp.json()


def test_create_project_missing_name(client, auth_headers):
    resp = client.post("/api/projects/create", json={}, headers=auth_headers)
    assert resp.status_code == 400


def test_create_project_unauthenticated(client):
    resp = client.post("/api/projects/create", json={"project_name": "X"})
    assert resp.status_code == 401


def test_list_projects(client, auth_headers, test_project):
    resp = client.get("/api/projects", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [p["project_id"] for p in data]
    assert test_project in ids


def test_get_project(client, auth_headers, test_project):
    resp = client.get(f"/api/projects/{test_project}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == test_project


def test_get_project_not_found(client, auth_headers):
    resp = client.get("/api/projects/nonexistent-uuid", headers=auth_headers)
    assert resp.status_code == 404


# ── Rename ────────────────────────────────────────────────────────────────────

def test_rename_project(client, auth_headers, test_project):
    resp = client.post(
        f"/api/projects/{test_project}/rename",
        json={"project_name": "Renamed Project"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


# ── Messages ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def message_id(client, auth_headers, test_project):
    resp = client.post(
        f"/api/projects/{test_project}/messages",
        json={"content": "Hello from test"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["message_id"]


def test_post_message(client, auth_headers, test_project):
    resp = client.post(
        f"/api/projects/{test_project}/messages",
        json={"content": "Another test message"},
        headers=auth_headers,
    )
    assert resp.status_code == 201


def test_get_messages(client, auth_headers, test_project, message_id):
    resp = client.get(f"/api/projects/{test_project}/messages", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


def test_delete_message(client, auth_headers, test_project):
    # Create a throwaway message
    cr = client.post(
        f"/api/projects/{test_project}/messages",
        json={"content": "To be deleted"},
        headers=auth_headers,
    )
    mid = cr.json()["message_id"]
    resp = client.delete(f"/api/messages/{mid}", headers=auth_headers)
    assert resp.status_code == 200


# ── Responses ─────────────────────────────────────────────────────────────────

def test_post_response(client, auth_headers, test_project):
    resp = client.post(
        f"/api/projects/{test_project}/responses",
        json={"content": "This is an AI response"},
        headers=auth_headers,
    )
    assert resp.status_code == 201


def test_get_responses(client, auth_headers, test_project):
    resp = client.get(f"/api/projects/{test_project}/responses", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── Conversation ──────────────────────────────────────────────────────────────

def test_get_conversation(client, auth_headers, test_project):
    resp = client.get(f"/api/projects/{test_project}/conversation", headers=auth_headers)
    assert resp.status_code == 200


# ── Top Users ─────────────────────────────────────────────────────────────────

def test_top_users(client, auth_headers, test_project):
    resp = client.get(f"/api/projects/{test_project}/top-users", headers=auth_headers)
    assert resp.status_code == 200


# ── Vector Status ─────────────────────────────────────────────────────────────

def test_vector_status(client, auth_headers, test_project):
    resp = client.get(f"/api/projects/{test_project}/vector-status", headers=auth_headers)
    assert resp.status_code == 200


# ── Paper Bucket ─────────────────────────────────────────────────────────────

def test_get_paper_bucket(client, auth_headers, test_project):
    resp = client.get(f"/api/projects/{test_project}/paper-bucket", headers=auth_headers)
    assert resp.status_code == 200


def test_add_to_paper_bucket(client, auth_headers, test_project, test_document):
    resp = client.post(
        f"/api/projects/{test_project}/paper-bucket/add",
        json={"doc_id": test_document},
        headers=auth_headers,
    )
    assert resp.status_code in (200, 201)


def test_update_paper_bucket(client, auth_headers, test_project, test_document):
    resp = client.put(
        f"/api/projects/{test_project}/paper-bucket",
        json={"paper_ids": [test_document]},
        headers=auth_headers,
    )
    assert resp.status_code == 200


def test_delete_from_paper_bucket(client, auth_headers, test_project, test_document):
    resp = client.delete(
        f"/api/projects/{test_project}/paper-bucket/{test_document}",
        headers=auth_headers,
    )
    assert resp.status_code == 200


# ── Paper (LaTeX / final draft) ───────────────────────────────────────────────

def test_get_paper(client, auth_headers, test_project):
    resp = client.get(f"/api/projects/{test_project}/paper", headers=auth_headers)
    assert resp.status_code == 200


def test_update_paper(client, auth_headers, test_project):
    resp = client.put(
        f"/api/projects/{test_project}/paper",
        json={"content": r"\documentclass{article}\begin{document}Hello\end{document}"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


# ── Generate PDF (ReportLab) ──────────────────────────────────────────────────

def test_generate_pdf(client, auth_headers, test_project):
    resp = client.get(f"/api/projects/{test_project}/generate-pdf", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"


# ── Temporary Query (no auth required) ───────────────────────────────────────

@patch("rag.raptor.temporary_query_pipeline", return_value="Mocked answer")
def test_query_temporary(mock_pipeline, client):
    resp = client.post(
        "/api/query-temporary",
        json={
            "text": "This is a long enough text for the temporary query endpoint.",
            "question": "What is this about?",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert data["mode"] == "temporary"


def test_query_temporary_missing_fields(client):
    resp = client.post("/api/query-temporary", json={"text": "only text"})
    assert resp.status_code == 400


def test_query_temporary_short_text(client):
    resp = client.post(
        "/api/query-temporary",
        json={"text": "short", "question": "What is this?"},
    )
    assert resp.status_code == 400


# ── Delete Project ────────────────────────────────────────────────────────────

def test_delete_project(client, auth_headers):
    cr = client.post(
        "/api/projects/create",
        json={"project_name": "To Delete"},
        headers=auth_headers,
    )
    pid = cr.json()["project_id"]
    resp = client.delete(f"/api/projects/{pid}", headers=auth_headers)
    assert resp.status_code == 200
