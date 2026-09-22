"""tests/test_users.py – User profile & token endpoints."""


def test_get_user_authenticated(client, auth_headers):
    resp = client.get("/api/user", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "email" in data
    assert "tokens" in data
    assert "tokens_formatted" in data


def test_get_user_unauthenticated(client):
    resp = client.get("/api/user")
    assert resp.status_code == 401


def test_get_tokens(client, auth_headers):
    resp = client.get("/api/tokens", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "tokens" in data
    assert isinstance(data["tokens"], int)


def test_get_tokens_unauthenticated(client):
    resp = client.get("/api/tokens")
    assert resp.status_code == 401


def test_check_tokens_sufficient(client, auth_headers):
    resp = client.post(
        "/api/tokens/check",
        json={"required_tokens": 100},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "has_enough" in data
    assert "current_tokens" in data


def test_check_tokens_zero_required(client, auth_headers):
    resp = client.post(
        "/api/tokens/check",
        json={"required_tokens": 0},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["has_enough"] is True


def test_check_tokens_negative(client, auth_headers):
    resp = client.post(
        "/api/tokens/check",
        json={"required_tokens": -1},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_protected_route(client, auth_headers):
    resp = client.get("/api/protected", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "user_id" in data


def test_protected_route_unauthenticated(client):
    resp = client.get("/api/protected")
    assert resp.status_code == 401
