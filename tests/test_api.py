from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def initialized_app():
    async with LifespanManager(app) as manager:
        yield manager.app


@pytest.fixture
async def client(initialized_app) -> AsyncClient:
    transport = ASGITransport(app=initialized_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def auth_client(initialized_app) -> AsyncClient:
    """Authenticated client with service account."""
    transport = ASGITransport(app=initialized_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Create token inside the app context
        from app.auth.jwt import create_token_pair, get_user_by_id
        user = get_user_by_id("service")
        tokens = create_token_pair(user)
        ac.headers["Authorization"] = f"Bearer {tokens.access_token}"
        yield ac


@pytest.fixture
async def admin_client(initialized_app) -> AsyncClient:
    """Authenticated client with admin account."""
    transport = ASGITransport(app=initialized_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        from app.auth.jwt import create_token_pair, get_user_by_id
        user = get_user_by_id("admin")
        tokens = create_token_pair(user)
        ac.headers["Authorization"] = f"Bearer {tokens.access_token}"
        yield ac


class TestHealthEndpoints:
    async def test_liveness(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "timestamp" in data
        assert data["version"] == "0.1.0"

    async def test_health(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    async def test_readiness(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "components" in data
        assert "inference" in data["components"]
        assert "routing" in data["components"]


class TestAuthEndpoints:
    async def test_login(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "service", "password": "any"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    async def test_login_invalid(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": "nonexistent", "password": "any"},
        )
        assert response.status_code == 401

    async def test_refresh_token(self, client: AsyncClient) -> None:
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "service", "password": "any"},
        )
        refresh_token = login_resp.json()["refresh_token"]

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_me(self, auth_client: AsyncClient) -> None:
        response = await auth_client.get("/api/v1/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "service-account"
        assert data["role"] == "service"


class TestClassificationEndpoints:
    async def test_classify_single_ticket(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post(
            "/api/v1/classify",
            json={
                "subject": "Login issue",
                "body": "Cannot login to my account",
                "customer_id": "cust-123",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "ticket_id" in data
        assert "classification" in data
        assert "processing_time_ms" in data
        assert "model_version" in data

        classification = data["classification"]
        assert "category" in classification
        assert "confidence" in classification
        assert "priority" in classification
        assert "suggested_team" in classification
        assert 0 <= classification["confidence"] <= 1

    async def test_classify_batch(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post(
            "/api/v1/classify/batch",
            json={
                "tickets": [
                    {"subject": "Bug in API", "body": "API returns 500 error"},
                    {"subject": "Billing question", "body": "Invoice amount is wrong"},
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2
        assert "total_processing_time_ms" in data
        assert "model_version" in data

    async def test_classify_invalid_request(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post(
            "/api/v1/classify",
            json={"subject": "", "body": "test"},
        )
        assert response.status_code == 422

    async def test_classify_missing_fields(self, auth_client: AsyncClient) -> None:
        response = await auth_client.post("/api/v1/classify", json={})
        assert response.status_code == 422

    async def test_classify_without_auth(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/v1/classify",
            json={
                "subject": "Test",
                "body": "Test body",
            },
        )
        assert response.status_code == 401


class TestMetricsEndpoint:
    async def test_metrics(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
