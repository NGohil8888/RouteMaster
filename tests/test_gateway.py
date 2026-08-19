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


class TestImprovements:
    """Regression tests for behavior changes flagged in the audit:

    - #1 streaming usage accounting (#1 in review)
    - #2 plan-gate keyword expansion (#2 in review)
    - #5 runtime settings bounds (#5 in review)
    """

    def test_ensure_include_usage_injects_stream_options(self):
        from app.proxy import _ensure_include_usage

        body = b'{"model":"gemma3:4b","messages":[],"stream":true}'
        out = _ensure_include_usage(body)
        import json as _json
        parsed = _json.loads(out)
        assert parsed["stream"] is True
        assert parsed["stream_options"]["include_usage"] is True
        # The body must remain valid JSON, no leftover malformation.
        assert isinstance(parsed["messages"], list)

    def test_ensure_include_usage_preserves_client_stream_options(self):
        from app.proxy import _ensure_include_usage

        body = b'{"model":"x","messages":[],"stream":true,"stream_options":{"include_obfuscation":true}}'
        out = _ensure_include_usage(body)
        import json as _json
        parsed = _json.loads(out)
        assert parsed["stream_options"]["include_usage"] is True
        # Existing client-side flags survive untouched.
        assert parsed["stream_options"]["include_obfuscation"] is True

    def test_ensure_include_usage_no_op_for_non_stream(self):
        from app.proxy import _ensure_include_usage

        body = b'{"model":"x","messages":[],"stream":false}'
        # Same bytes in, same bytes out.
        assert _ensure_include_usage(body) == body

    def test_ensure_include_usage_handles_garbage(self):
        from app.proxy import _ensure_include_usage

        assert _ensure_include_usage(b"not json at all") == b"not json at all"
        assert _ensure_include_usage(None) is None
        assert _ensure_include_usage(b"") == b""

    def test_extract_streaming_usage_finds_final_chunk(self):
        from app.proxy import _extract_streaming_usage

        chunks = [
            b'data: {"id":"1","choices":[{"delta":{"content":"hi"}}]}\n\n',
            b'data: {"id":"2","choices":[{"delta":{"content":" there"}}]}\n\n',
            b'data: {"id":"3","choices":[],"usage":{"prompt_tokens":12,"completion_tokens":7,"total_tokens":19}}\n\n',
            b'data: [DONE]\n\n',
        ]
        usage = _extract_streaming_usage(chunks)
        assert usage is not None
        assert usage["prompt_tokens"] == 12
        assert usage["completion_tokens"] == 7
        assert usage["total_tokens"] == 19

    def test_extract_streaming_usage_handles_missing(self):
        from app.proxy import _extract_streaming_usage

        # Stream finished without ever emitting usage.
        chunks = [b'data: {"id":"1","choices":[{"delta":{"content":"hi"}}]}\n\n']
        assert _extract_streaming_usage(chunks) is None

    def test_extract_streaming_usage_handles_junk(self):
        from app.proxy import _extract_streaming_usage

        chunks = [b"this is not sse at all\n\n", b"\xff\xfe garbage \xff\xff\n"]
        assert _extract_streaming_usage(chunks) is None

    def test_looks_plan_gated_catches_variants(self):
        from app.proxy import _looks_plan_gated

        # Pre-existing triggers.
        assert _looks_plan_gated("This model requires a subscription to access")
        assert _looks_plan_gated("This model needs upgrade for access")
        # New variants the old code missed.
        assert _looks_plan_gated("This model requires a higher plan")
        assert _looks_plan_gated("Feature_unavailable on the free tier")
        assert _looks_plan_gated("Model X is not available on your plan")
        assert _looks_plan_gated("not entitled to this model")
        # Case-insensitive.
        assert _looks_plan_gated("REQUIRES A SUBSCRIPTION")
        # Negative cases.
        assert not _looks_plan_gated("rate limit exceeded")
        assert not _looks_plan_gated("invalid api key")
        assert not _looks_plan_gated("")
        assert not _looks_plan_gated(None)

    @pytest.mark.asyncio
    async def test_settings_validation_rejects_zero(self):
        # Validation has to happen at the dashboard layer AND in runtime_config
        # so we cover both.
        from app import runtime_config
        from app.dashboard_api import SettingsIn

        # The Pydantic model rejects 0.
        try:
            SettingsIn(max_retries=0)
        except Exception:
            pass
        else:
            raise AssertionError("SettingsIn should reject max_retries=0")

        # runtime_config rejects the same.
        try:
            await runtime_config.update_settings({"max_retries": 0})
        except runtime_config.SettingsValidationError:
            pass
        else:
            raise AssertionError("runtime_config.update_settings should reject max_retries=0")

    @pytest.mark.asyncio
    async def test_settings_validation_rejects_negative(self):
        from app import runtime_config

        try:
            await runtime_config.update_settings({"request_timeout_seconds": -5.0})
        except runtime_config.SettingsValidationError:
            pass
        else:
            raise AssertionError("runtime_config.update_settings should reject negative timeouts")

    @pytest.mark.asyncio
    async def test_settings_validation_accepts_in_range(self, tmp_path):
        import app.store as store
        from app import runtime_config

        original = store.DATA_DIR
        store.DATA_DIR = tmp_path / "data"
        store.DATA_DIR.mkdir()
        try:
            updated = await runtime_config.update_settings({"max_retries": 5})
            assert updated["max_retries"] == 5
        finally:
            store.DATA_DIR = original

    @pytest.mark.asyncio
    async def test_admin_token_open_when_unset(self, client):
        # Without GATEWAY_ADMIN_TOKEN set, /api/* is open as before.
        resp = client.get("/api/overview")
        assert resp.status_code == 200
        resp = client.get("/api/auth/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["required"] is False
        assert body["ok"] is False

    @pytest.mark.asyncio
    async def test_admin_token_locks_when_set(self):
        """Setting GATEWAY_ADMIN_TOKEN makes /api/* reject unsigned requests."""
        from fastapi.testclient import TestClient
        from app.config import settings
        from app.main import app

        original = settings.gateway_admin_token
        settings.gateway_admin_token = "supersecrettoken"
        try:
            # Use a fresh client so the test sees the live settings value.
            test_client = TestClient(app)
            # No token -> 401
            resp = test_client.get("/api/overview")
            assert resp.status_code == 401
            resp = test_client.get("/api/auth/status")
            assert resp.status_code == 200
            assert resp.json()["required"] is True
            assert resp.json()["ok"] is False

            # Wrong token -> 401, never echoed back in body
            resp = test_client.get(
                "/api/overview", headers={"X-Gateway-Token": "wrong"}
            )
            assert resp.status_code == 401

            # Right token via X-Gateway-Token -> 200
            resp = test_client.get(
                "/api/overview",
                headers={"X-Gateway-Token": "supersecrettoken"},
            )
            assert resp.status_code == 200

            # Right token via Authorization: Bearer -> 200
            resp = test_client.get(
                "/api/overview",
                headers={"Authorization": "Bearer supersecrettoken"},
            )
            assert resp.status_code == 200

            # /health and / stay open even when the token is set (these
            # don't read user-config; the proxy needs them unlocked for
            # Docker's healthcheck and OpenAI-compatible clients).
            assert test_client.get("/health").status_code == 200
            assert test_client.get("/").status_code == 200
        finally:
            settings.gateway_admin_token = original

    @pytest.mark.asyncio
    async def test_settings_string_token_round_trip(self, tmp_path):
        import app.store as store
        from app import runtime_config

        original_dir = store.DATA_DIR
        original_token = settings.gateway_admin_token
        store.DATA_DIR = tmp_path / "data"
        store.DATA_DIR.mkdir()
        try:
            settings.gateway_admin_token = None
            updated = await runtime_config.update_settings(
                {"gateway_admin_token": "new-admin-token-12345"}
            )
            # The token isn't echoed back, only a boolean indicating it's set.
            assert updated["gateway_admin_token"] is True
            # ... and the live settings object has the real value.
            assert settings.gateway_admin_token == "new-admin-token-12345"

            # Clear by sending empty string.
            await runtime_config.update_settings({"gateway_admin_token": ""})
            assert settings.gateway_admin_token is None
        finally:
            settings.gateway_admin_token = original_token
            store.DATA_DIR = original_dir