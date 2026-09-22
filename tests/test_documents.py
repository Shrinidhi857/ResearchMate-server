"""tests/test_documents.py – Document CRUD endpoint tests."""

import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def doc_id(client, auth_headers):
    """Create a document for this module and return its doc_id."""
    resp = client.post(
        "/api/documents",
        json={"title": "Module Test Doc", "content": "Hello world content for testing."},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["doc_id"]


# ── Create ────────────────────────────────────────────────────────────────────

def test_create_document_success(client, auth_headers):
    resp = client.post(
        "/api/documents",
        json={"title": "My Paper", "content": "Abstract: This paper studies something."},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "doc_id" in data
    assert data["title"] == "My Paper"


def test_create_document_missing_content(client, auth_headers):
    resp = client.post(
        "/api/documents",
        json={"title": "No Content"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_create_document_unauthenticated(client):
    resp = client.post(
        "/api/documents",
        json={"content": "Some content"},
    )
    assert resp.status_code == 401


# ── List ──────────────────────────────────────────────────────────────────────

def test_list_documents(client, auth_headers, doc_id):
    resp = client.get("/api/documents", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    ids = [d["doc_id"] for d in data]
    assert doc_id in ids


def test_list_documents_unauthenticated(client):
    resp = client.get("/api/documents")
    assert resp.status_code == 401


# ── Summary ───────────────────────────────────────────────────────────────────

def test_documents_summary(client, auth_headers):
    resp = client.get("/api/documents/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    for item in data:
        assert "doc_id" in item
        assert "title" in item


# ── Get single ───────────────────────────────────────────────────────────────

def test_get_document(client, auth_headers, doc_id):
    resp = client.get(f"/api/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["doc_id"] == doc_id
    assert "content" in data


def test_get_document_not_found(client, auth_headers):
    resp = client.get("/api/documents/nonexistent-id-xyz", headers=auth_headers)
    assert resp.status_code == 404


# ── Update ────────────────────────────────────────────────────────────────────

def test_update_document(client, auth_headers, doc_id):
    resp = client.put(
        f"/api/documents/{doc_id}",
        json={"content": "Updated content goes here."},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "updated" in resp.json()["message"].lower()


def test_update_document_missing_content(client, auth_headers, doc_id):
    resp = client.put(
        f"/api/documents/{doc_id}",
        json={"title": "Only title, no content"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


# ── Delete ────────────────────────────────────────────────────────────────────

def test_delete_document(client, auth_headers):
    # Create a throwaway document
    create_resp = client.post(
        "/api/documents",
        json={"title": "To Delete", "content": "Goodbye."},
        headers=auth_headers,
    )
    throwaway_id = create_resp.json()["doc_id"]
    resp = client.delete(f"/api/documents/{throwaway_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert "deleted" in resp.json()["message"].lower()


def test_delete_document_not_found(client, auth_headers):
    resp = client.delete("/api/documents/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404
