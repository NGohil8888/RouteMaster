"""Comprehensive tests for the Ollama Cloud API Gateway."""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, AsyncMock

import httpx
from fastapi.testclient import TestClient
from starlette.responses import Response

from app.main import app
from app.config import settings
from app.account_manager import AccountPool, AccountState, initialize_pool
from app.proxy import proxy_request
from app.health import check_account_health


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_settings():
    """Mock settings with test API keys."""
    with patch.object(settings, "ollama_api_keys", "key1,key2,key3"):
        with patch.object(settings, "ollama_base_url", "https://ollama.com"):
            with patch.object(settings, "max_retries", 3):
                with patch.object(settings, "request_timeout_seconds", 5):
                    with patch.object(settings, "account_cooldown_seconds", 1):
                        yield settings


@pytest.fixture
def initialized_pool(mock_settings):
    """Initialize account pool for tests."""
    pool = initialize_pool(mock_settings.api_keys_list)
    yield pool
    import app.account_manager as am
    am.account_pool = None


class TestAccountPool:
    """Tests for the account pool management."""

    def test_pool_initialization(self, mock_settings):
        pool = AccountPool(mock_settings.api_keys_list)
        assert pool.total_accounts == 3

    def test_round_robin_selection(self, initialized_pool):
        async def test():
            acct1 = await initialized_pool.get_next_account()
            assert acct1 is not None
            assert acct1.index == 0
            await initialized_pool.release_account(acct1)

            acct2 = await initialized_pool.get_next_account()
            assert acct2 is not None
            assert acct2.index == 1
            await initialized_pool.release_account(acct2)

            acct3 = await initialized_pool.get_next_account()
            assert acct3 is not None
            assert acct3.index == 2
            await initialized_pool.release_account(acct3)

            acct4 = await initialized_pool.get_next_account()
            assert acct4 is not None
            assert acct4.index == 0
            await initialized_pool.release_account(acct4)

        asyncio.run(test())

    def test_skip_unavailable_accounts(self, initialized_pool):
        async def test():
            await initialized_pool.record_failure(
                initialized_pool.accounts[0],
                "Rate limited",
                AccountState.RATE_LIMITED,
                cooldown_seconds=3600,
            )

            acct = await initialized_pool.get_next_account()
            assert acct is not None
            assert acct.index != 0
            await initialized_pool.release_account(acct)

        asyncio.run(test())

    def test_account_recovery(self, initialized_pool):
        async def test():
            await initialized_pool.record_failure(
                initialized_pool.accounts[0],
                "Server error",
                AccountState.TEMPORARILY_UNAVAILABLE,
                cooldown_seconds=0.1,
            )

            assert not initialized_pool.accounts[0].is_available
            await asyncio.sleep(0.2)
            assert initialized_pool.accounts[0].is_available

            await initialized_pool.record_success(initialized_pool.accounts[0])
            assert initialized_pool.accounts[0].status.state == AccountState.HEALTHY

        asyncio.run(test())

    def test_exponential_backoff(self, initialized_pool):
        async def test():
            account = initialized_pool.accounts[0]
            await initialized_pool.record_failure(account, "Error 1", AccountState.TEMPORARILY_UNAVAILABLE, cooldown_seconds=1)
            first_cooldown = account.status.cooldown_until

            await initialized_pool.record_failure(account, "Error 2", AccountState.TEMPORARILY_UNAVAILABLE, cooldown_seconds=1)
            second_cooldown = account.status.cooldown_until

            assert second_cooldown > first_cooldown

        asyncio.run(test())


class TestProxy:
    """Tests for the proxy layer."""

    @pytest.mark.asyncio
    async def test_successful_request(self, initialized_pool):
        with patch("app.proxy.get_ollama_client") as mock_client_factory:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "application/json"}
            mock_response.aread = AsyncMock(return_value=b'{"id":"test"}')

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_factory.return_value = mock_client

            response = await proxy_request(
                method="POST",
                path="v1/chat/completions",
                request_headers={"content-type": "application/json"},
                body=b'{"model":"test","messages":[]}',
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_failover_on_429(self, initialized_pool):
        with patch("app.proxy.get_ollama_client") as mock_client_factory:
            mock_response_429 = AsyncMock()
            mock_response_429.status_code = 429
            mock_response_429.headers = {"retry-after": "60"}
            mock_response_429.reason_phrase = "Too Many Requests"
            mock_response_429.json = AsyncMock(return_value={"error": {"message": "Rate limited"}})
            mock_response_429.aread = AsyncMock(return_value=b'{"error":"rate limited"}')

            mock_response_200 = AsyncMock()
            mock_response_200.status_code = 200
            mock_response_200.headers = {"content-type": "application/json"}
            mock_response_200.aread = AsyncMock(return_value=b'{"id":"success"}')

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(side_effect=[mock_response_429, mock_response_200])
            mock_client.aclose = AsyncMock()
            mock_client_factory.return_value = mock_client

            response = await proxy_request(
                method="POST",
                path="v1/chat/completions",
                request_headers={"content-type": "application/json"},
                body=b'{"model":"test","messages":[]}',
            )

            assert response.status_code == 200
            assert mock_client.request.call_count == 2

    @pytest.mark.asyncio
    async def test_failover_on_500(self, initialized_pool):
        with patch("app.proxy.get_ollama_client") as mock_client_factory:
            mock_response_500 = AsyncMock()
            mock_response_500.status_code = 500
            mock_response_500.reason_phrase = "Internal Server Error"
            mock_response_500.json = AsyncMock(return_value={"error": "server error"})
            mock_response_500.aread = AsyncMock(return_value=b'{"error":"server error"}')

            mock_response_200 = AsyncMock()
            mock_response_200.status_code = 200
            mock_response_200.headers = {"content-type": "application/json"}
            mock_response_200.aread = AsyncMock(return_value=b'{"id":"success"}')

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(side_effect=[mock_response_500, mock_response_200])
            mock_client.aclose = AsyncMock()
            mock_client_factory.return_value = mock_client

            response = await proxy_request(
                method="POST",
                path="v1/chat/completions",
                request_headers={"content-type": "application/json"},
                body=b'{"model":"test","messages":[]}',
            )

            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_all_accounts_unavailable(self, initialized_pool):
        with patch("app.proxy.get_ollama_client") as mock_client_factory:
            mock_response = AsyncMock()
            mock_response.status_code = 429
            mock_response.headers = {}
            mock_response.reason_phrase = "Too Many Requests"
            mock_response.json = AsyncMock(return_value={"error": "rate limited"})
            mock_response.aread = AsyncMock(return_value=b'{"error":"rate limited"}')

            mock_client = AsyncMock()
            mock_client.request = AsyncMock(return_value=mock_response)
            mock_client.aclose = AsyncMock()
            mock_client_factory.return_value = mock_client

            response = await proxy_request(
                method="POST",
                path="v1/chat/completions",
                request_headers={"content-type": "application/json"},
                body=b'{"model":"test","messages":[]}',
            )

            assert response.status_code == 503
            body = json.loads(response.body)
            assert "No upstream Ollama provider available" in body["error"]["message"]

    @pytest.mark.asyncio
    async def test_streaming_request_detection(self, initialized_pool):
        with patch("app.proxy.get_ollama_client") as mock_client_factory:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.headers = {"content-type": "text/event-stream"}

            async def fake_aiter():
                yield b"data: test\n\n"

            mock_response.aiter_bytes = fake_aiter
            mock_response.aclose = AsyncMock()

            from unittest.mock import MagicMock

            stream_cm = MagicMock()
            stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
            stream_cm.__aexit__ = AsyncMock()

            mock_client = AsyncMock()
            # .stream() itself is a plain (non-async) method in real httpx,
            # returning an async context manager - not a coroutine.
            mock_client.stream = MagicMock(return_value=stream_cm)
            mock_client.aclose = AsyncMock()
            mock_client_factory.return_value = mock_client

            response = await proxy_request(
                method="POST",
                path="v1/chat/completions",
                request_headers={"content-type": "application/json"},
                body=b'{"model":"test","messages":[],"stream":true}',
            )

            from fastapi.responses import StreamingResponse
            assert isinstance(response, StreamingResponse)


class TestHealthCheck:
    """Tests for health monitoring."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, initialized_pool):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json = AsyncMock(return_value={"models": []})

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()

            mock_client_class.return_value = mock_client

            result = await check_account_health(0)
            assert result.healthy is True
            assert result.state == AccountState.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_429(self, initialized_pool):
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = AsyncMock()
            mock_response.status_code = 429
            mock_response.json = AsyncMock(return_value={"error": "rate limited"})

            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock()

            mock_client_class.return_value = mock_client

            result = await check_account_health(0)
            assert result.healthy is False
            assert result.state == AccountState.RATE_LIMITED


class TestEndpoints:
    """Tests for FastAPI endpoints."""

    def test_health_endpoint(self, client, initialized_pool):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["accounts"]["total"] == 3

    def test_status_endpoint(self, client, initialized_pool):
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "accounts" in data
        assert "requests" in data

    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "Ollama Cloud API Failover Gateway" in response.json()["name"]


class TestConcurrency:
    """Tests for concurrent request handling."""

    def test_concurrent_requests(self, initialized_pool):
        async def make_request(idx):
            acct = await initialized_pool.get_next_account()
            assert acct is not None
            await asyncio.sleep(0.01)
            await initialized_pool.release_account(acct)
            return acct.index

        async def run():
            tasks = [make_request(i) for i in range(10)]
            results = await asyncio.gather(*tasks)
            assert len(results) == 10

        asyncio.run(run())