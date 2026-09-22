"""tests/test_admin.py – Admin endpoint tests."""

import pytest


# ── Access control ────────────────────────────────────────────────────────────

def test_admin_users_forbidden_for_regular_user(client, auth_headers):
    resp = client.get("/api/admin/users", headers=auth_headers)
    assert resp.status_code == 403


def test_admin_users_unauthenticated(client):
    resp = client.get("/api/admin/users")
    assert resp.status_code == 401


# ── User management ───────────────────────────────────────────────────────────

def test_admin_list_users(client, admin_headers):
    resp = client.get("/api/admin/users", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert "total" in data
    assert isinstance(data["users"], list)


def test_admin_list_users_pagination(client, admin_headers):
    resp = client.get("/api/admin/users?page=1&per_page=5", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["per_page"] == 5
    assert data["current_page"] == 1


def test_admin_list_users_search(client, admin_headers):
    resp = client.get("/api/admin/users?search=testuser", headers=admin_headers)
    assert resp.status_code == 200
    assert "users" in resp.json()


def test_admin_get_user(client, admin_headers, regular_user_id):
    resp = client.get(f"/api/admin/users/{regular_user_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == regular_user_id


def test_admin_get_user_not_found(client, admin_headers):
    resp = client.get("/api/admin/users/999999", headers=admin_headers)
    assert resp.status_code == 404


# ── Token management ──────────────────────────────────────────────────────────

def test_admin_get_user_tokens(client, admin_headers, regular_user_id):
    resp = client.get(f"/api/admin/users/{regular_user_id}/tokens", headers=admin_headers)
    assert resp.status_code == 200
    assert "tokens" in resp.json()


def test_admin_add_tokens(client, admin_headers, regular_user_id):
    resp = client.post(
        f"/api/admin/users/{regular_user_id}/tokens/add",
        json={"amount": 5000},
        headers=admin_headers,
    )
    assert resp.status_code == 200


def test_admin_deduct_tokens(client, admin_headers, regular_user_id):
    resp = client.post(
        f"/api/admin/users/{regular_user_id}/tokens/deduct",
        json={"amount": 1000},
        headers=admin_headers,
    )
    assert resp.status_code == 200


def test_admin_set_tokens(client, admin_headers, regular_user_id):
    resp = client.post(
        f"/api/admin/users/{regular_user_id}/tokens/set",
        json={"amount": 25000},
        headers=admin_headers,
    )
    assert resp.status_code == 200


# ── User status operations ────────────────────────────────────────────────────

def test_admin_verify_user(client, admin_headers, regular_user_id):
    resp = client.post(
        f"/api/admin/users/{regular_user_id}/verify",
        headers=admin_headers,
    )
    assert resp.status_code == 200


def test_admin_grant_admin(client, admin_headers, regular_user_id):
    resp = client.post(
        f"/api/admin/users/{regular_user_id}/grant-admin",
        headers=admin_headers,
    )
    assert resp.status_code == 200


def test_admin_revoke_admin(client, admin_headers, regular_user_id):
    resp = client.post(
        f"/api/admin/users/{regular_user_id}/revoke-admin",
        headers=admin_headers,
    )
    assert resp.status_code == 200


# ── Analytics & Reports ───────────────────────────────────────────────────────

def test_admin_analytics(client, admin_headers):
    resp = client.get("/api/admin/analytics", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_users" in data


def test_admin_token_usage_report(client, admin_headers):
    resp = client.get("/api/admin/token-usage-report", headers=admin_headers)
    assert resp.status_code == 200


def test_admin_info(client, admin_headers):
    resp = client.get("/api/admin/info", headers=admin_headers)
    assert resp.status_code == 200
