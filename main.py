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
import asyncio
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

# Comma-separated Ollama Cloud keys. Requests retry with the next key after
# Ollama returns 429. An empty value keeps local, unauthenticated Ollama working.
def load_ollama_api_keys() -> list[str]:
    raw = os.environ.get("OLLAMA_API_KEYS", "")
    return [key.strip() for key in raw.split(",") if key.strip()]


OLLAMA_API_KEYS = load_ollama_api_keys()
_ollama_key_index = 0
_ollama_key_lock = asyncio.Lock()

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
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Ollama Gateway", version="1.0.0")


def check_api_key(authorization: Optional[str]) -> str:
    """Validate the key callers use to access this gateway."""
    return check_api_key_no_increment(authorization)


def check_api_key_no_increment(authorization: Optional[str]) -> str:
    """Validate the key without making an upstream Ollama request."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token not in API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return token


async def ollama_headers() -> dict[str, str]:
    """Return headers for the current Ollama key, if cloud keys are configured."""
    if not OLLAMA_API_KEYS:
        return {}
    async with _ollama_key_lock:
        return {"Authorization": f"Bearer {OLLAMA_API_KEYS[_ollama_key_index]}"}


async def rotate_ollama_key() -> None:
    global _ollama_key_index
    async with _ollama_key_lock:
        _ollama_key_index = (_ollama_key_index + 1) % len(OLLAMA_API_KEYS)


async def ollama_request(client: httpx.AsyncClient, method: str, path: str, **kwargs) -> httpx.Response:
    """Retry an upstream request once with every Ollama key after a 429."""
    attempts = max(1, len(OLLAMA_API_KEYS))
    for attempt in range(attempts):
        request_kwargs = dict(kwargs)
        request_kwargs["headers"] = await ollama_headers()
        response = await client.request(method, f"{OLLAMA_BASE_URL}{path}", **request_kwargs)
        if response.status_code != 429 or attempt == attempts - 1:
            return response
        await rotate_ollama_key()
    raise RuntimeError("Ollama request retry loop ended unexpectedly")


async def ollama_stream(client: httpx.AsyncClient, path: str, **kwargs):
    """Yield an upstream stream, rotating through all keys on 429 responses."""
    attempts = max(1, len(OLLAMA_API_KEYS))
    for attempt in range(attempts):
        request_kwargs = dict(kwargs)
        request_kwargs["headers"] = await ollama_headers()
        async with client.stream("POST", f"{OLLAMA_BASE_URL}{path}", **request_kwargs) as response:
            if response.status_code == 429 and attempt < attempts - 1:
                await rotate_ollama_key()
                continue
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    yield line + "\n"
            return


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
            r = await ollama_request(client, "GET", "/api/tags")
            r.raise_for_status()
            return {"gateway": "ok", "ollama": "ok", "models": r.json()}
    except Exception as e:
        return JSONResponse(status_code=503, content={"gateway": "ok", "ollama": "unreachable", "error": str(e)})


@app.get("/v1/usage")
async def usage(authorization: Optional[str] = Header(None)):
    """Report whether Ollama keys are configured for upstream rotation."""
    check_api_key_no_increment(authorization)
    return {"ollama_keys_configured": len(OLLAMA_API_KEYS), "rotation_on_429": len(OLLAMA_API_KEYS) > 1}


@app.get("/v1/models")
async def list_models(authorization: Optional[str] = Header(None)):
    check_api_key(authorization)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await ollama_request(client, "GET", "/api/tags")
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
                async for line in ollama_stream(client, "/api/chat", json=payload):
                    yield line
        return StreamingResponse(event_stream(), media_type="application/x-ndjson")

    async with httpx.AsyncClient(timeout=120) as client:
        r = await ollama_request(client, "POST", "/api/chat", json=payload)
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
                async for line in ollama_stream(client, "/api/generate", json=payload):
                    yield line
        return StreamingResponse(event_stream(), media_type="application/x-ndjson")

    async with httpx.AsyncClient(timeout=120) as client:
        r = await ollama_request(client, "POST", "/api/generate", json=payload)
        r.raise_for_status()
        return r.json()
