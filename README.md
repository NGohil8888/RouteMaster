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

## 7. Notes on security

- This gateway is designed for **local/trusted-network use**. It does not
  do TLS, rate limiting, or per-key usage tracking out of the box.
- If you expose it beyond your LAN (e.g. via a tunnel or port forward),
  put it behind HTTPS (e.g. Caddy, Nginx, or Cloudflare Tunnel) and treat
  your API keys like real secrets.
- Anyone with a valid key currently has equal access — there's no
  per-key permission scoping. That's easy to add later in `check_api_key`
  if you need it.
