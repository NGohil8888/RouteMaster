# Ollama Gateway

A small self-hosted API gateway that sits in front of your local Ollama
server. It adds:

- **API-key auth** — no more wide-open `localhost:11434` to every app on
  your machine.
- **Stable endpoints** (`/v1/chat`, `/v1/generate`, `/v1/models`,
  `/v1/health`) you can point any project at, regardless of which model
  or Ollama version is running underneath.
- **Streaming support** for both chat and generate.

## 1. Prerequisites

- Ollama installed and running (`ollama serve`, default port `11434`).
  At least one model pulled, e.g. `ollama pull llama3.2`.
- Python 3.10+

## 2. Setup

```bash
cd ollama-gateway
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

On first run, if no `.env` file exists yet (or `GATEWAY_API_KEYS` is
blank), the gateway auto-generates a key and writes it into `.env`:

```
No API keys found. Generated a new one and saved it to .env:
  8f3a1c9e...
Use it as: Authorization: Bearer <that key>
```

`.env` is already in `.gitignore` — never commit it.

### Adding your own keys

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Then edit `.env` and set one or more keys (comma-separated for multiple
apps/projects):

```
GATEWAY_API_KEYS=key-for-app-1,key-for-app-2
OLLAMA_BASE_URL=http://localhost:11434
```

Restart the server after editing `.env` for changes to take effect.

Different keys let you tell which app/project is calling if you later
add logging or rate limits — right now all valid keys have equal access.

## 4. Usage

### Health check (no key needed)

```bash
curl http://localhost:8000/v1/health
```

### List installed models

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Chat

```bash
curl http://localhost:8000/v1/chat \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.2",
    "messages": [{"role": "user", "content": "Give me a haiku about oceans."}]
  }'
```

### Generate (single prompt, no chat history)

```bash
curl http://localhost:8000/v1/generate \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2", "prompt": "Explain recursion in one sentence."}'
```

### Streaming

Set `"stream": true` in the request body. Responses come back as
newline-delimited JSON (`application/x-ndjson`), one chunk per line —
the same format Ollama itself uses.

## 5. Calling it from code

### Python

```python
import requests

resp = requests.post(
    "http://localhost:8000/v1/chat",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={
        "model": "llama3.2",
        "messages": [{"role": "user", "content": "Hello!"}],
    },
)
print(resp.json())
```

### JavaScript / Node

```javascript
const resp = await fetch("http://localhost:8000/v1/chat", {
  method: "POST",
  headers: {
    "Authorization": "Bearer YOUR_API_KEY",
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    model: "llama3.2",
    messages: [{ role: "user", content: "Hello!" }],
  }),
});
const data = await resp.json();
console.log(data);
```

## 6. Using it from multiple projects

Since the gateway runs once on `localhost:8000` (or a LAN IP if you set
`--host 0.0.0.0` and connect from another device on your network), every
project just needs:

1. The base URL (`http://localhost:8000` or `http://<your-machine-ip>:8000`)
2. Its API key

No project needs direct knowledge of Ollama, which model versions are
installed, or where it's hosted — the gateway is the single stable
interface.

## 7. Key rotation (multiple keys, automatic fallback)

You can give the gateway several keys and set a per-key rate limit. When one
key hits its limit, requests using that key get rejected with `429 Too Many
Requests` — your client can then automatically switch to the next key.

### Step 1 — Add multiple keys and a limit in `.env`

```
GATEWAY_API_KEYS=key-one,key-two,key-three
RATE_LIMIT_PER_MINUTE=60
```

Each key gets its own independent quota (60 requests/minute each, in this
example — 180 total across all three). Set `RATE_LIMIT_PER_MINUTE=0` to
disable rate limiting entirely.

### Step 2 — Use `gateway_client.py` for automatic rotation

The included `gateway_client.py` handles this for you:

```python
from gateway_client import GatewayClient

client = GatewayClient(
    base_url="http://localhost:8000",
    api_keys=["key-one", "key-two", "key-three"],
)

# If "key-one" is currently rate-limited, this call automatically
# retries with "key-two", then "key-three", before giving up.
response = client.chat(
    model="nemotron-3-super:cloud",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response["message"]["content"])
```

It keeps track of which key it's currently on and only moves to the next
one when it gets a `429`, so it doesn't waste quota switching unnecessarily.

### Checking remaining quota

```bash
curl http://localhost:8000/v1/usage -H "Authorization: Bearer YOUR_KEY"
```

```json
{"limit_per_minute": 60, "used_in_window": 12, "remaining": 48}
```

This endpoint doesn't count against the key's own quota, so checking your
usage never eats into it.

### Notes

- The rate limiter is **in-memory** — it resets if you restart the gateway.
  For a purely local single-user setup this is normally fine.
- This limits *your own client apps'* usage of the gateway. It's separate
  from any rate limits Ollama's cloud service itself might apply when a
  model runs remotely (e.g. `nemotron-3-super:cloud`) — those are enforced
  by Ollama, not by this gateway, and aren't something key rotation here
  can get around.

## 8. Notes on security

- This gateway is designed for **local/trusted-network use**. It does not
  do TLS out of the box.
- If you expose it beyond your LAN (e.g. via a tunnel or port forward),
  put it behind HTTPS (e.g. Caddy, Nginx, or Cloudflare Tunnel) and treat
  your API keys like real secrets.
- Anyone with a valid key currently has equal access — there's no
  per-key permission scoping. That's easy to add later in `check_api_key`
  if you need it.

