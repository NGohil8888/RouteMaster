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
  - Hitting token/quota limits
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

1. Clone or create the project folder:
   ```bash
   mkdir ollama-gateway
   cd ollama-gateway

2. Create a virtual environment and install dependencies:
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

3. Copy the example environment file and add your API keys:
cp .env.example .env

4. Edit .env and set your Ollama Cloud API keys:
OLLAMA_API_KEYS=your_key_1,your_key_2,your_key_3

Configuration
All configuration is done via environment variables (.env file).
| Variable                              | Default              | Description                                   |
| ------------------------------------- | -------------------- | --------------------------------------------- |
| `HOST`                                | `0.0.0.0`            | Bind address                                  |
| `PORT`                                | `8000`               | Port to listen on                             |
| `OLLAMA_API_KEYS`                     | *(required)*         | Comma-separated list of Ollama Cloud API keys |
| `OLLAMA_BASE_URL`                     | `https://ollama.com` | Ollama Cloud base URL                         |
| `MAX_RETRIES`                         | `3`                  | Max retry attempts per request                |
| `REQUEST_TIMEOUT_SECONDS`             | `120`                | HTTP request timeout                          |
| `ACCOUNT_COOLDOWN_SECONDS`            | `60`                 | Base cooldown for failed accounts             |
| `HEALTH_CHECK_INTERVAL_SECONDS`       | `30`                 | How often to check account health             |
| `LOG_LEVEL`                           | `INFO`               | Logging level                                 |
| `STREAM_TIMEOUT_SECONDS`              | `300`                | Timeout for streaming requests                |
| `MAX_CONCURRENT_REQUESTS_PER_ACCOUNT` | `10`                 | Max parallel requests per account             |

How to Add Ollama API Accounts
Get API keys from https://ollama.com/settings for each account you want to use.

# Add them to .env as a comma-separated list:
OLLAMA_API_KEYS=key1,key2,key3,key4,key5
There is no limit to the number of accounts. The gateway will round-robin across all healthy accounts.
How to Start the Server

# Without Docker
python run.py

# Or directly with uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000

The server will start on http://localhost:8000.
How to Test It
Test the health endpoint

curl http://localhost:8000/health
List available models

curl http://localhost:8000/v1/models

Chat completion (non-streaming)

curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma3:4b",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": false
  }'
Chat completion (streaming)

curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma3:4b",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'

Check gateway status

curl http://localhost:8000/status
How to Configure AI Agents
Configure your agent to use the local gateway as an OpenAI-compatible endpoint:

| Setting  | Value                                                                     |
| -------- | ------------------------------------------------------------------------- |
| Base URL | `http://localhost:8000/v1`                                                |
| API Key  | `anything` (the gateway ignores this and uses configured keys internally) |

OpenClaw
Set your provider to use the local gateway base URL.
Hermes / Other Agents
Use OpenAI-compatible mode with:
1. Base URL: http://localhost:8000/v1
2. Model: Any model available on Ollama Cloud (e.g., gemma3:4b, qwen3-coder:480b)

How Failover Works
1. A request arrives at http://localhost:8000/v1/...
2. The gateway picks the next available account (round-robin)
3. If the request succeeds, the response is returned immediately
4. If the account fails:

    a. The failure is detected

    b. The account is marked with a cooldown

    c. The gateway immediately tries another account

    d. This continues until success or MAX_RETRIES is reached

5. The client receives the successful response transparently

Example:
Request -> Account 1 (fails, 429) -> Account 2 (fails, 503) -> Account 3 (success) -> Client

How to Troubleshoot Errors
Check logs

The gateway logs structured messages:
[INFO] Request successful via account 0
[WARN] Account 1 marked rate_limited: Rate limited. Cooldown until ...
[INFO] Retrying request using account 2

Check status endpoint
curl http://localhost:8000/status
Shows which accounts are healthy, rate-limited, or unavailable.

Common issues
| Issue                           | Solution                                               |
| ------------------------------- | ------------------------------------------------------ |
| `No Ollama API keys configured` | Set `OLLAMA_API_KEYS` in `.env`                        |
| All accounts unhealthy          | Verify API keys at <https://ollama.com/settings>       |
| 503 from gateway                | All accounts are down; wait for cooldown or check keys |
| Streaming not working           | Ensure `stream_timeout_seconds` is high enough         |

Running Tests
pytest tests/ -v


---

## Quick Start

1. Create the folder structure above
2. Copy all files into place
3. `cp .env.example .env` and add your real Ollama Cloud API keys
4. `pip install -r requirements.txt`
5. `python run.py`
6. Point your AI agent to `http://localhost:8000/v1`

The gateway is fully async, handles streaming, monitors health in the background, and will automatically route around any failing Ollama Cloud accounts.