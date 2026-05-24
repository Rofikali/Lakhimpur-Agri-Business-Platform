

class TestLogin:
    async def test_valid_login_returns_200_and_sets_cookie(self, client, owner):
        resp = await client.post(
            "/api/auth/login",
            json={
                "username": "testadmin",
                "password": "TestPass123!",
            },
        )
        assert resp.status_code == 200
        assert "token" in resp.cookies
        data = resp.json()
        assert "owner_id" in data
        assert "expires_at" in data
        assert data["username"] == "testadmin"

    async def test_wrong_password_returns_401(self, client, owner):
        resp = await client.post(
            "/api/auth/login",
            json={
                "username": "testadmin",
                "password": "WrongPassword!",
            },
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "INVALID_CREDENTIALS"

    async def test_wrong_username_returns_401(self, client, owner):
        resp = await client.post(
            "/api/auth/login",
            json={
                "username": "nobody",
                "password": "TestPass123!",
            },
        )
        assert resp.status_code == 401
        # Same error for wrong username AND wrong password — prevents enumeration
        assert resp.json()["error"] == "INVALID_CREDENTIALS"

    async def test_cookie_is_httponly(self, client, owner):
        resp = await client.post(
            "/api/auth/login",
            json={
                "username": "testadmin",
                "password": "TestPass123!",
            },
        )
        assert resp.status_code == 200
        # httponly cookies are not visible to JS — FastAPI sets the header
        set_cookie = resp.headers.get("set-cookie", "")
        assert "httponly" in set_cookie.lower()

    async def test_empty_password_rejected(self, client, owner):
        resp = await client.post(
            "/api/auth/login",
            json={
                "username": "testadmin",
                "password": "",
            },
        )
        assert resp.status_code == 422


class TestLogout:
    async def test_logout_clears_cookie(self, auth_client):
        resp = await auth_client.post("/api/auth/logout")
        assert resp.status_code == 200
        # Cookie should be cleared (max-age=0 or deleted)
        set_cookie = resp.headers.get("set-cookie", "")
        assert "max-age=0" in set_cookie.lower() or "expires" in set_cookie.lower()

    async def test_no_cookie_returns_401(self, client, owner):
        resp = await client.post("/api/auth/logout")
        assert resp.status_code == 401

    async def test_logged_out_token_rejected(self, client, owner):
        """After logout, the same JWT must be rejected (blocklist check)."""
        # Login
        login = await client.post(
            "/api/auth/login",
            json={
                "username": "testadmin",
                "password": "TestPass123!",
            },
        )
        assert login.status_code == 200

        # Logout
        logout = await client.post("/api/auth/logout")
        assert logout.status_code == 200

        # Try using the old cookie — should fail
        # (httpx retains cookies between requests in the same client)
        resp = await client.get("/api/orders/")
        assert resp.status_code == 401


class TestRefresh:
    async def test_refresh_returns_new_expiry(self, auth_client):
        resp = await auth_client.post("/api/auth/refresh")
        assert resp.status_code == 200
        assert "expires_at" in resp.json()

    async def test_unauthenticated_refresh_returns_401(self, client, owner):
        resp = await client.post("/api/auth/refresh")
        assert resp.status_code == 401


class TestProtectedRoutes:
    async def test_dashboard_requires_auth(self, client, owner):
        resp = await client.get("/api/orders/")
        assert resp.status_code == 401

    async def test_authenticated_can_access_dashboard(self, auth_client):
        resp = await auth_client.get("/api/orders/")
        assert resp.status_code == 200
