# Ollama Cloud API Failover Gateway

A production-ready, OpenAI-compatible local API gateway that sits between your AI agents and multiple Ollama Cloud API accounts. It provides **automatic failover**, **health monitoring**, **rate-limit handling**, and **streaming support** so that multiple Ollama Cloud accounts behave like one reliable API service.

## What This Project Does

- Exposes a single local OpenAI-compatible endpoint at `http://localhost:8000/v1`
- Forwards requests to multiple Ollama Cloud API accounts
- Automatically fails over when an account is:
  - Temporarily unavailable
  - Rate limited (HTTP 429)
  - Returning server errors (HTTP 500/502/503/504)
  - Timing out
  - Has an invalid/expired API key
- Supports streaming responses (`stream: true`)
- Background health checks automatically recover failed accounts
- Never exposes your API keys to downstream clients

## Requirements

- Python 3.10+
- pip
- (Optional) Docker & Docker Compose

## Installation

### Without Docker

1. Clone the repo and `cd` into it.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate      # on Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copy the example env file and fill in your Ollama Cloud API keys:
   ```bash
   cp .env.example .env
   # edit .env and set OLLAMA_API_KEYS=key1,key2,key3
   ```
4. Run the gateway:
   ```bash
   python run.py
   ```
   The gateway will be available at `http://localhost:8000`.

### With Docker

1. Copy `.env.example` to `.env` and fill in your API keys (same as above).
2. Build and start the container:
   ```bash
   docker compose up --build -d
   ```
3. Check it's running:
   ```bash
   curl http://localhost:8000/health
   ```
4. Stop it with:
   ```bash
   docker compose down
   ```

## Usage

Point any OpenAI-compatible client at the gateway instead of Ollama Cloud directly:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma3:4b",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

No client-side API key is required — the gateway injects one of your configured Ollama Cloud keys on your behalf and rotates/retries across accounts automatically.

### Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Basic gateway info |
| `GET /health` | Liveness/readiness check, used by Docker's healthcheck |
| `GET /status` | Detailed per-account status (requests, failures, cooldowns) |
| `/v1/*` | Proxied to Ollama Cloud's OpenAI-compatible API, with failover |

## Configuration

All configuration is via environment variables (see `.env.example` for the full list and defaults):

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_API_KEYS` | *(required)* | Comma-separated list of Ollama Cloud API keys |
| `OLLAMA_BASE_URL` | `https://ollama.com` | Ollama Cloud base URL |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Bind address for the gateway |
| `MAX_RETRIES` | `3` | Max accounts to try per request before giving up |
| `REQUEST_TIMEOUT_SECONDS` | `120` | Timeout for non-streaming requests |
| `STREAM_TIMEOUT_SECONDS` | `300` | Timeout for streaming requests |
| `ACCOUNT_COOLDOWN_SECONDS` | `60` | Base cooldown after a failure (grows with exponential backoff) |
| `HEALTH_CHECK_INTERVAL_SECONDS` | `30` | How often the background health monitor checks accounts |
| `MAX_CONCURRENT_REQUESTS_PER_ACCOUNT` | `10` | Concurrency cap per account |

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## Do You Need Docker?

Docker is optional. This is a lightweight pure-Python app with no system-level dependencies, so a plain virtualenv works fine for local/single-machine use. Docker mainly buys you automatic restarts (`restart: unless-stopped`) and environment isolation — useful if you're deploying this to a server, but not required for running it on your own machine.

## Project Structure

```
app/
  main.py              FastAPI app, routes
  proxy.py             Request forwarding + failover logic
  account_manager.py   Account pool, state tracking, cooldowns
  health.py            Background health monitoring
  config.py            Settings loaded from environment
  models.py            Pydantic data models
tests/
  test_gateway.py       Test suite
run.py                  Entry point
Dockerfile / docker-compose.yml
```
