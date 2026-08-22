"""
Ollama API Gateway
-------------------
A thin, self-hosted gateway that sits in front of your local Ollama server
and adds API-key authentication + a stable set of endpoints you can reuse
across multiple projects/apps.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Then call it like:
    curl http://localhost:8000/v1/chat \
      -H "Authorization: Bearer YOUR_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"model": "llama3.2", "messages": [{"role": "user", "content": "hi"}]}'
"""

import os
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv, set_key
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).parent / ".env"
load_dotenv(ENV_PATH)

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# How many requests each individual API key may make per rolling 60s window.
# Set to 0 to disable rate limiting entirely.
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))

# Load allowed API keys from the GATEWAY_API_KEYS variable in .env
# (comma-separated if you have more than one, e.g. one key per app/project).
def load_api_keys() -> set[str]:
    raw = os.environ.get("GATEWAY_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


API_KEYS = load_api_keys()

if not API_KEYS:
    # Auto-generate one key on first run so the gateway is never wide open,
    # and write it into .env so it persists across restarts.
    generated = secrets.token_urlsafe(32)
    API_KEYS = {generated}

    if not ENV_PATH.exists():
        ENV_PATH.touch()
    set_key(str(ENV_PATH), "GATEWAY_API_KEYS", generated)

    print("=" * 70)
    print("No API keys found. Generated a new one and saved it to .env:")
    print(f"  {generated}")
    print("Use it as: Authorization: Bearer <that key>")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Rate limiting (per key, in-memory sliding window)
# ---------------------------------------------------------------------------
# Each key gets its own timestamp deque. On each request we drop timestamps
# older than 60s, then check whether the remaining count is under the limit.
# This resets automatically if the server restarts (in-memory only).

_request_log: dict[str, deque] = defaultdict(deque)
WINDOW_SECONDS = 60


def check_rate_limit(key: str):
    if RATE_LIMIT_PER_MINUTE <= 0:
        return  # rate limiting disabled

    now = time.time()
    log = _request_log[key]

    while log and now - log[0] > WINDOW_SECONDS:
        log.popleft()

    if len(log) >= RATE_LIMIT_PER_MINUTE:
        retry_after = int(WINDOW_SECONDS - (now - log[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for this API key ({RATE_LIMIT_PER_MINUTE}/min). "
                    f"Try again in {retry_after}s, or use a different key.",
            headers={"Retry-After": str(retry_after)},
        )

    log.append(now)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Ollama Gateway", version="1.0.0")


def check_api_key(authorization: Optional[str]) -> str:
    """Validates the key and enforces its rate limit. Returns the key itself
    so callers can use it (e.g. for logging)."""
    token = check_api_key_no_increment(authorization)
    check_rate_limit(token)
    return token


def check_api_key_no_increment(authorization: Optional[str]) -> str:
    """Validates the key only, without counting it against the rate limit.
    Used by /v1/usage so checking your quota doesn't itself use up quota."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token not in API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return token


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: Optional[float] = None


class GenerateRequest(BaseModel):
    model: str
    prompt: str
    stream: bool = False
    temperature: Optional[float] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/v1/health")
async def health():
    """Check that the gateway is up and Ollama is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            r.raise_for_status()
            return {"gateway": "ok", "ollama": "ok", "models": r.json()}
    except Exception as e:
        return JSONResponse(status_code=503, content={"gateway": "ok", "ollama": "unreachable", "error": str(e)})


@app.get("/v1/usage")
async def usage(authorization: Optional[str] = Header(None)):
    """Check how many requests this key has used in the current window."""
    key = check_api_key_no_increment(authorization)
    now = time.time()
    log = _request_log[key]
    while log and now - log[0] > WINDOW_SECONDS:
        log.popleft()
    return {
        "limit_per_minute": RATE_LIMIT_PER_MINUTE,
        "used_in_window": len(log),
        "remaining": max(0, RATE_LIMIT_PER_MINUTE - len(log)) if RATE_LIMIT_PER_MINUTE > 0 else "unlimited",
    }


@app.get("/v1/models")
async def list_models(authorization: Optional[str] = Header(None)):
    check_api_key(authorization)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
        r.raise_for_status()
        return r.json()


@app.post("/v1/chat")
async def chat(body: ChatRequest, authorization: Optional[str] = Header(None)):
    check_api_key(authorization)

    payload = {
        "model": body.model,
        "messages": [m.model_dump() for m in body.messages],
        "stream": body.stream,
    }
    if body.temperature is not None:
        payload["options"] = {"temperature": body.temperature}

    if body.stream:
        async def event_stream():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as r:
                    async for line in r.aiter_lines():
                        if line:
                            yield line + "\n"
        return StreamingResponse(event_stream(), media_type="application/x-ndjson")

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        r.raise_for_status()
        return r.json()


@app.post("/v1/generate")
async def generate(body: GenerateRequest, authorization: Optional[str] = Header(None)):
    check_api_key(authorization)

    payload = {
        "model": body.model,
        "prompt": body.prompt,
        "stream": body.stream,
    }
    if body.temperature is not None:
        payload["options"] = {"temperature": body.temperature}

    if body.stream:
        async def event_stream():
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/generate", json=payload) as r:
                    async for line in r.aiter_lines():
                        if line:
                            yield line + "\n"
        return StreamingResponse(event_stream(), media_type="application/x-ndjson")

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
        r.raise_for_status()
        return r.json()
