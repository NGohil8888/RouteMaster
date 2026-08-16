"""Proxy layer for forwarding requests to Ollama Cloud with failover support."""

import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.responses import Response

from app.config import settings
from app.account_manager import Account, AccountPool, AccountState, account_pool
from app.models import ProxyRequest

logger = logging.getLogger(__name__)

# HTTP status codes that indicate transient failures worth retrying
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

# HTTP status codes that indicate auth/quota issues
AUTH_STATUS_CODES = {401, 403}
RATE_LIMIT_STATUS = 429


def get_ollama_client(timeout: Optional[float] = None) -> httpx.AsyncClient:
    """Create an httpx client for Ollama Cloud requests."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout or settings.request_timeout_seconds),
        follow_redirects=True,
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
        ),
    )


def _is_streaming_request(body: bytes) -> bool:
    """Check if the request body indicates streaming."""
    try:
        data = json.loads(body)
        return data.get("stream", False)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return False


def _mask_key(key: str) -> str:
    """Mask an API key for safe logging."""
    if len(key) <= 8:
        return "***"
    return key[:4] + "..." + key[-4:]


def _extract_cooldown_from_headers(headers: Dict[str, str]) -> Optional[float]:
    """Extract cooldown duration from rate limit headers."""
    # Check common rate limit headers
    retry_after = headers.get("retry-after") or headers.get("x-ratelimit-reset")
    if retry_after:
        try:
            return float(retry_after)
        except (ValueError, TypeError):
            pass

    # Check x-ratelimit-remaining
    remaining = headers.get("x-ratelimit-remaining")
    if remaining is not None:
        try:
            if int(remaining) <= 0:
                # No remaining requests, use default cooldown
                return settings.account_cooldown_seconds
        except (ValueError, TypeError):
            pass

    return None


def _extract_error_message(response: httpx.Response) -> str:
    """Extract a human-readable error message from a response."""
    try:
        data = response.json()
        if "error" in data:
            err = data["error"]
            if isinstance(err, dict):
                return err.get("message", str(err))
            return str(err)
        return data.get("message", f"HTTP {response.status_code}")
    except Exception:
        return f"HTTP {response.status_code}: {response.reason_phrase}"


async def _make_request(
    client: httpx.AsyncClient,
    account: Account,
    method: str,
    url: str,
    headers: Dict[str, str],
    body: Optional[bytes],
    stream: bool = False,
) -> httpx.Response:
    """Make a single request to Ollama Cloud."""
    request_headers = dict(headers)
    request_headers["Authorization"] = f"Bearer {account.api_key}"
    # Remove any existing Authorization header from client
    request_headers.pop("authorization", None)
    request_headers.pop("Authorization", None)
    request_headers["Authorization"] = f"Bearer {account.api_key}"

    logger.debug(
        f"Account {account.index} -> {method} {url} (stream={stream})"
    )

    if stream:
        return await client.stream(
            method=method,
            url=url,
            headers=request_headers,
            content=body,
        ).__aenter__()
    else:
        return await client.request(
            method=method,
            url=url,
            headers=request_headers,
            content=body,
        )


async def _stream_response(
    response: httpx.Response,
    account: Account,
) -> AsyncGenerator[bytes, None]:
    """Stream response chunks from upstream to client."""
    try:
        async for chunk in response.aiter_bytes():
            yield chunk
    except Exception as e:
        logger.warning(f"Streaming error for account {account.index}: {e}")
        raise
    finally:
        await response.aclose()


async def proxy_request(
    method: str,
    path: str,
    request_headers: Dict[str, str],
    body: Optional[bytes],
    query_string: str = "",
) -> Response:
    """Proxy a request to Ollama Cloud with automatic failover."""
    if account_pool is None:
        raise HTTPException(status_code=503, detail="Account pool not initialized")

    stream = _is_streaming_request(body) if body else False
    target_path = path.lstrip("/")
    if not target_path.startswith("v1/"):
        target_path = f"v1/{target_path}"

    base_url = settings.ollama_openai_base
    url = f"{base_url}/{target_path}"
    if query_string:
        url = f"{url}?{query_string}"

    excluded_indices: List[int] = []
    last_error: Optional[str] = None
    last_status_code: int = 503

    for attempt in range(settings.max_retries):
        acct = await account_pool.get_next_account(excluded_indices=excluded_indices)
        if acct is None:
            logger.error("No available Ollama accounts for request")
            break

        client = get_ollama_client(
            timeout=settings.stream_timeout_seconds if stream else settings.request_timeout_seconds
        )

        try:
            response = await _make_request(
                client=client,
                account=acct,
                method=method,
                url=url,
                headers=request_headers,
                body=body,
                stream=stream,
            )

            if response.status_code < 400:
                # Success
                await account_pool.record_success(acct)
                logger.info(
                    f"Request successful via account {acct.index} "
                    f"(attempt {attempt + 1}, status={response.status_code})"
                )

                if stream:
                    # Return streaming response
                    return StreamingResponse(
                        content=_stream_response(response, acct),
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.headers.get("content-type", "text/event-stream"),
                    )
                else:
                    content = await response.aread()
                    return Response(
                        content=content,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                    )

            # Handle error response
            error_msg = _extract_error_message(response)
            last_error = error_msg
            last_status_code = response.status_code

            if response.status_code in AUTH_STATUS_CODES:
                await account_pool.record_failure(
                    acct,
                    f"Auth error: {error_msg}",
                    AccountState.AUTH_ERROR,
                    cooldown_seconds=settings.account_cooldown_seconds * 2,
                )
                excluded_indices.append(acct.index)

            elif response.status_code == RATE_LIMIT_STATUS:
                cooldown = _extract_cooldown_from_headers(dict(response.headers))
                await account_pool.record_failure(
                    acct,
                    f"Rate limited: {error_msg}",
                    AccountState.RATE_LIMITED,
                    cooldown_seconds=cooldown,
                )
                excluded_indices.append(acct.index)

            elif response.status_code in TRANSIENT_STATUS_CODES:
                await account_pool.record_failure(
                    acct,
                    f"Server error: {error_msg}",
                    AccountState.TEMPORARILY_UNAVAILABLE,
                )
                excluded_indices.append(acct.index)

            else:
                # Client errors (4xx) that aren't auth-related - don't retry
                await account_pool.record_failure(
                    acct,
                    f"Client error: {error_msg}",
                    AccountState.TEMPORARILY_UNAVAILABLE,
                )
                # Return the error to the client
                content = await response.aread()
                return Response(
                    content=content,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                )

            logger.warning(
                f"Account {acct.index} failed (attempt {attempt + 1}): "
                f"HTTP {response.status_code} - {error_msg}"
            )

        except httpx.TimeoutException as e:
            last_error = f"Timeout: {str(e)}"
            last_status_code = 504
            await account_pool.record_failure(
                acct,
                last_error,
                AccountState.TEMPORARILY_UNAVAILABLE,
            )
            excluded_indices.append(acct.index)
            logger.warning(f"Account {acct.index} timeout (attempt {attempt + 1})")

        except httpx.ConnectError as e:
            last_error = f"Connection error: {str(e)}"
            last_status_code = 502
            await account_pool.record_failure(
                acct,
                last_error,
                AccountState.TEMPORARILY_UNAVAILABLE,
            )
            excluded_indices.append(acct.index)
            logger.warning(f"Account {acct.index} connection error (attempt {attempt + 1})")

        except httpx.HTTPStatusError as e:
            last_error = f"HTTP error: {str(e)}"
            last_status_code = e.response.status_code
            await account_pool.record_failure(
                acct,
                last_error,
                AccountState.TEMPORARILY_UNAVAILABLE,
            )
            excluded_indices.append(acct.index)
            logger.warning(f"Account {acct.index} HTTP error (attempt {attempt + 1}): {e}")

        except Exception as e:
            last_error = f"Unexpected error: {str(e)}"
            last_status_code = 502
            await account_pool.record_failure(
                acct,
                last_error,
                AccountState.TEMPORARILY_UNAVAILABLE,
            )
            excluded_indices.append(acct.index)
            logger.warning(f"Account {acct.index} unexpected error (attempt {attempt + 1}): {e}")

        finally:
            await account_pool.release_account(acct)
            if not stream:
                await client.aclose()

    # All retries exhausted or no accounts available
    logger.error(f"All accounts failed for request to {path}. Last error: {last_error}")

    # Return OpenAI-compatible error
    error_body = json.dumps({
        "error": {
            "message": f"No upstream Ollama provider available. Last error: {last_error}",
            "type": "gateway_error",
            "code": "service_unavailable",
        }
    }).encode("utf-8")

    return Response(
        content=error_body,
        status_code=503,
        headers={"content-type": "application/json"},
    )