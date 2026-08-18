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
from app.account_manager import Account, AccountPool, AccountState, get_account_pool
from app.models import ProxyRequest

logger = logging.getLogger(__name__)

# HTTP status codes that indicate transient failures worth retrying
TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}

# HTTP status codes that indicate auth/quota issues
AUTH_STATUS_CODES = {401, 403}
RATE_LIMIT_STATUS = 429

# Substrings (lowercased) the upstream uses when a model isn't available on
# the current plan. Anything matching here gets treated as a permanent,
# account-independent error: retrying on a second account wastes cooldowns
# and obscures the real cause from the caller.
PLAN_GATE_KEYWORDS = (
    "subscription",
    "upgrade for access",
    "upgrade your",
    "upgrade required",
    "requires a subscription",
    "not available on your plan",
    "not available with your",
    "plan tier",
    "feature_unavailable",
    "requires a higher",
    "not entitled",
)


def _ensure_include_usage(body: Optional[bytes]) -> Optional[bytes]:
    """For streaming requests, ensure the upstream body opts in to usage chunks.

    OpenAI-compatible APIs only emit a final chunk carrying the `usage` object
    when `stream_options.include_usage` is set. Without it, the proxy has no
    way to count tokens for streaming chat completions.
    """
    if not body:
        return body
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body
    if not isinstance(data, dict) or not data.get("stream"):
        return body

    opts = data.get("stream_options")
    if isinstance(opts, dict):
        opts["include_usage"] = True
    else:
        data["stream_options"] = {"include_usage": True}

    return json.dumps(data, separators=(",", ":")).encode("utf-8")


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


def _looks_plan_gated(message: str) -> bool:
    """Return True if `message` (already extracted from an upstream error body)
    looks like the account's plan tier isn't allowed to use this model.

    Compared case-insensitively. The previous implementation only matched a
    couple of phrases, so any other wording (e.g. "requires a higher plan")
    fell through into the generic AUTH_ERROR branch, which then cooled every
    account down indefinitely.
    """
    if not message:
        return False
    lowered = message.lower()
    return any(keyword in lowered for keyword in PLAN_GATE_KEYWORDS)


def _extract_error_message(response: httpx.Response) -> str:
    """Extract a human-readable error message from a response.

    Tries `response.json()` first (fast path for responses that haven't had
    their body consumed yet). If parsing fails - typically because the body
    has already been read via `response.aread()` upstream - falls back to
    `response.text` so we still surface whatever the upstream sent back.
    """
    try:
        data = response.json()
    except Exception:
        try:
            return response.text or f"HTTP {response.status_code}: {response.reason_phrase}"
        except Exception:
            return f"HTTP {response.status_code}: {response.reason_phrase}"

    if isinstance(data, dict):
        if "error" in data:
            err = data["error"]
            if isinstance(err, dict):
                return err.get("message", str(err))
            return str(err)
        return data.get("message", f"HTTP {response.status_code}")
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
    # Strip any client-supplied Authorization header before injecting our own
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


def _extract_streaming_usage(chunks: List[bytes]) -> Optional[Dict]:
    """Scan accumulated SSE chunks for the trailing `usage` object.

    OpenAI-compatible streaming responses end with a final chunk shaped like
    `data: {"choices": [], "usage": {...}}` when include_usage is enabled.
    Some upstreams split a single JSON payload across multiple `data:` lines,
    so we parse each non-empty payload individually and return the LAST one
    that carries a usage block.
    """
    last_usage: Optional[Dict] = None
    for chunk in chunks:
        try:
            text = chunk.decode("utf-8", errors="ignore")
        except Exception:
            continue
        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped.startswith("data:"):
                continue
            payload = stripped[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                obj = json.loads(payload)
            except json.JSONDecodeError:
                continue
            usage = obj.get("usage") if isinstance(obj, dict) else None
            if isinstance(usage, dict):
                last_usage = usage
    return last_usage


async def _stream_response(
    response: httpx.Response,
    account: Account,
    client: httpx.AsyncClient,
) -> AsyncGenerator[bytes, None]:
    """Stream response chunks from upstream to client.

    Keeps a rolling tail buffer of the last ~64 KB of bytes so we can extract
    the trailing `usage` object once the stream finishes, without pinning
    arbitrarily large streams in memory. The upstream only emits usage in the
    last `data:` line, so the tail is all we ever need to scan.
    """
    tail = bytearray()
    tail_capacity = 64 * 1024
    try:
        async for chunk in response.aiter_bytes():
            tail.extend(chunk)
            if len(tail) > tail_capacity:
                # Keep only the last `tail_capacity` bytes.
                del tail[: len(tail) - tail_capacity]
            yield chunk
    except Exception as e:
        logger.warning(f"Streaming error for account {account.index}: {e}")
        raise
    finally:
        try:
            usage = _extract_streaming_usage([bytes(tail)])
            if usage:
                pool = get_account_pool()
                if pool is not None:
                    await pool.record_usage(account, usage)
        except Exception as e:
            logger.debug(f"Could not record streaming usage: {e}")
        await response.aclose()
        await client.aclose()


async def proxy_request(
    method: str,
    path: str,
    request_headers: Dict[str, str],
    body: Optional[bytes],
    query_string: str = "",
) -> Response:
    """Proxy a request to Ollama Cloud with automatic failover."""
    account_pool = get_account_pool()
    if account_pool is None:
        raise HTTPException(status_code=503, detail="Account pool not initialized")

    stream = _is_streaming_request(body) if body else False
    upstream_body = _ensure_include_usage(body) if stream else body
    target_path = path.lstrip("/")
    if target_path.startswith("v1/"):
        # settings.ollama_openai_base already ends in /v1 - strip any
        # duplicate v1/ prefix from the incoming path before appending.
        target_path = target_path[len("v1/"):]

    base_url = settings.ollama_openai_base
    url = f"{base_url}/{target_path}" if target_path else base_url
    logger.info(f"Proxying {method} {path!r} -> {url}")
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
        client_handed_off = False

        try:
            response = await _make_request(
                client=client,
                account=acct,
                method=method,
                url=url,
                headers=request_headers,
                body=upstream_body,
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
                    # Return streaming response; the generator now owns the client
                    client_handed_off = True
                    return StreamingResponse(
                        content=_stream_response(response, acct, client),
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.headers.get("content-type", "text/event-stream"),
                    )
                else:
                    content = await response.aread()
                    try:
                        usage = json.loads(content).get("usage")
                        if usage:
                            await account_pool.record_usage(acct, usage)
                    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
                        pass
                    return Response(
                        content=content,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                    )

            # Handle error response - the body must be explicitly read before it can be
            # parsed. For streaming requests the response arrives unread, and calling
            # .json() on it before .aread() silently fails, swallowing the real upstream
            # error message and leaving only a generic "HTTP 403: Forbidden" behind.
            await response.aread()
            error_msg = _extract_error_message(response)
            last_error = error_msg
            last_status_code = response.status_code

            if response.status_code in AUTH_STATUS_CODES:
                if _looks_plan_gated(error_msg):
                    # Model not available on this plan tier - it will fail
                    # identically on every other account on the same tier, so
                    # retrying is pointless and would just needlessly cool
                    # down every account. Return the real upstream message
                    # straight to the client instead.
                    logger.warning(
                        f"Model not available on account {acct.index}'s plan: {error_msg}"
                    )
                    return Response(
                        content=response.content,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                    )
                await account_pool.record_failure(
                    acct,
                    f"Auth error: {error_msg}",
                    AccountState.AUTH_ERROR,
                    cooldown_seconds=settings.account_cooldown_seconds * 2,
                )
                excluded_indices.append(acct.index)

            elif response.status_code == RATE_LIMIT_STATUS:
                cooldown = _extract_cooldown_from_headers(dict(response.headers))
                is_quota_exhausted = any(
                    kw in error_msg.lower() for kw in ("quota", "token limit", "credit")
                )
                state = AccountState.TOKEN_EXHAUSTED if is_quota_exhausted else AccountState.RATE_LIMITED
                await account_pool.record_failure(
                    acct,
                    f"{state.value.replace('_', ' ').title()}: {error_msg}",
                    state,
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
            if not client_handed_off:
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