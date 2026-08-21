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
import json
import secrets
from typing import Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Load allowed API keys from env var (comma-separated) or a keys.json file.
# You control who/what can call your gateway via these keys.
def load_api_keys() -> set[str]:
    keys = set()

    env_keys = os.environ.get("GATEWAY_API_KEYS", "")
    if env_keys:
        keys.update(k.strip() for k in env_keys.split(",") if k.strip())

    keys_file = os.path.join(os.path.dirname(__file__), "keys.json")
    if os.path.exists(keys_file):
        with open(keys_file) as f:
            data = json.load(f)
            keys.update(data.get("keys", []))

    return keys


API_KEYS = load_api_keys()

if not API_KEYS:
    # Auto-generate one key on first run so the gateway is never wide open.
    generated = secrets.token_urlsafe(32)
    API_KEYS = {generated}
    with open(os.path.join(os.path.dirname(__file__), "keys.json"), "w") as f:
        json.dump({"keys": [generated]}, f, indent=2)
    print("=" * 70)
    print("No API keys found. Generated a new one and saved it to keys.json:")
    print(f"  {generated}")
    print("Use it as: Authorization: Bearer <that key>")
    print("=" * 70)


# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Ollama Gateway", version="1.0.0")


def check_api_key(authorization: Optional[str]):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token not in API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")


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
