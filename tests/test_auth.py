"""tests/test_auth.py – Authentication endpoint tests."""

import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

UNIQUE = "authtests"
USER = {
    "email": f"{UNIQUE}@example.com",
    "password": "StrongPass1",
    "first_name": "Auth",
    "last_name": "Tester",
}


# ── Registration ──────────────────────────────────────────────────────────────

def test_register_success(client):
    resp = client.post("/auth/register", json=USER)
    assert resp.status_code == 201
    data = resp.json()
    assert "token" in data
    assert data["user"]["email"] == USER["email"]


def test_register_duplicate_email(client):
    resp = client.post("/auth/register", json=USER)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["error"].lower()


def test_register_invalid_email(client):
    resp = client.post("/auth/register", json={
        "email": "not-an-email",
        "password": "Password123",
    })
    assert resp.status_code == 400


def test_register_short_password(client):
    resp = client.post("/auth/register", json={
        "email": "short@example.com",
        "password": "abc",
    })
    assert resp.status_code == 400
    assert "password" in resp.json()["error"].lower()


def test_register_no_data(client):
    resp = client.post("/auth/register")
    assert resp.status_code in (400, 422)


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_success(client):
    resp = client.post("/auth/login", json={
        "email": USER["email"],
        "password": USER["password"],
    })
    assert resp.status_code == 200
    assert "token" in resp.json()


def test_login_wrong_password(client):
    resp = client.post("/auth/login", json={
        "email": USER["email"],
        "password": "WrongPassword999",
    })
    assert resp.status_code == 401


def test_login_nonexistent_user(client):
    resp = client.post("/auth/login", json={
        "email": "nobody@nowhere.com",
        "password": "Password123",
    })
    assert resp.status_code == 401


def test_login_missing_fields(client):
    resp = client.post("/auth/login", json={"email": USER["email"]})
    assert resp.status_code == 400


# ── Profile ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def _token(client):
    resp = client.post("/auth/login", json={
        "email": USER["email"],
        "password": USER["password"],
    })
    return resp.json()["token"]


@pytest.fixture(scope="module")
def _headers(_token):
    return {"Authorization": f"Bearer {_token}"}


def test_get_profile(client, _headers):
    resp = client.get("/auth/profile", headers=_headers)
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == USER["email"]


def test_get_profile_unauthenticated(client):
    resp = client.get("/auth/profile")
    assert resp.status_code == 401


def test_update_profile(client, _headers):
    resp = client.put("/auth/profile", json={"first_name": "Updated"}, headers=_headers)
    assert resp.status_code == 200
    assert resp.json()["user"]["first_name"] == "Updated"


# ── Password Change ───────────────────────────────────────────────────────────

def test_change_password_success(client, _headers):
    resp = client.post(
        "/auth/change-password",
        json={"current_password": USER["password"], "new_password": "NewStrong123"},
        headers=_headers,
    )
    assert resp.status_code == 200
    # Reset password back so other tests still work
    client.post(
        "/auth/change-password",
        json={"current_password": "NewStrong123", "new_password": USER["password"]},
        headers=_headers,
    )


def test_change_password_wrong_current(client, _headers):
    resp = client.post(
        "/auth/change-password",
        json={"current_password": "WrongCurrent", "new_password": "NewPass123"},
        headers=_headers,
    )
    assert resp.status_code == 401


def test_change_password_too_short(client, _headers):
    resp = client.post(
        "/auth/change-password",
        json={"current_password": USER["password"], "new_password": "ab"},
        headers=_headers,
    )
    assert resp.status_code == 400


# ── Logout ────────────────────────────────────────────────────────────────────

def test_logout(client, _headers, _token):
    resp = client.post(
        "/auth/logout",
        headers={**_headers, "Authorization": f"Bearer {_token}"},
    )
    assert resp.status_code == 200
    assert "logged out" in resp.json()["message"].lower()
