# Hermes Ollama Gateway

<p align="center">
  <b>Multi-Server Ollama API Router with Intelligent Load Balancing</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/React-61DAFB?style=flat&logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/Tailwind-06B6D4?style=flat&logo=tailwindcss&logoColor=white" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white" />
  <img src="https://img.shields.io/badge/Ollama-000000?style=flat" />
</p>

---

## What is Hermes?

Hermes is a **self-hosted API gateway** purpose-built for [Ollama](https://ollama.com). It sits between your applications and multiple Ollama instances, providing:

- **One unified API endpoint** for all your Ollama servers
- **7 intelligent routing modes** (Auto, Round Robin, Least Load, Fastest, Priority, Manual, Failover)
- **Automatic health monitoring** and failover
- **OpenAI-compatible API** (`/v1/chat/completions`, `/v1/models`)
- **Real-time dashboard** for cluster management
- **Built-in playground** for testing models across servers

Think of it as a load balancer specifically designed for Ollama's API.

---

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Your App      │────▶│  Hermes Gateway  │────▶│  Ollama Server 1│
│  (OpenAI SDK)   │     │   :8000 / :3000  │     │  :11434         │
└─────────────────┘     └──────────────────┘     ├─────────────────┤
                                                  │  Ollama Server 2│
                                                  │  :11434         │
                                                  ├─────────────────┤
                                                  │  Ollama Server 3│
                                                  │  :11434         │
                                                  └─────────────────┘
```

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- 1+ Ollama instances running somewhere accessible

### 1. Clone & Configure

```bash
git clone https://github.com/yourusername/hermes-ollama-gateway.git
cd hermes-ollama-gateway
cp .env.example .env
# Edit .env if needed
```

### 2. Launch

```bash
docker compose up -d
```

### 3. First-Time Setup

Visit `http://localhost:3000` and create your admin account.

### 4. Add Ollama Servers

Go to **Servers** in the dashboard and add your Ollama endpoints:
- `http://ollama-1:11434`
- `http://ollama-2:11434`
- etc.

---

## API Usage

Hermes exposes an **OpenAI-compatible API** at `http://localhost:8000/v1`.

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dummy"  # Not used but required by SDK
)

response = client.chat.completions.create(
    model="llama3.1",
    messages=[{"role": "user", "content": "Explain quantum computing"}],
    stream=False
)
print(response.choices[0].message.content)
```

### cURL

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3.1",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": false
  }'
```

### Streaming

```python
stream = client.chat.completions.create(
    model="llama3.1",
    messages=[{"role": "user", "content": "Hello!"}],
    stream=True
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

---

## Routing Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **AUTO** | Intelligent scoring based on load, latency, errors, priority, weight | Default, best for most cases |
| **ROUND_ROBIN** | Distribute requests evenly across healthy servers | Balanced load |
| **LEAST_LOAD** | Route to server with fewest active requests | Burst handling |
| **FASTEST_SERVER** | Route to lowest-latency server | Speed critical |
| **PRIORITY** | Always use highest-priority (lowest number) server | Tiered infrastructure |
| **MANUAL** | Use configured primary/fallback rules per model | Predictable routing |
| **FAILOVER_ONLY** | Use preferred server, only failover on failure | Stability focused |

Switch modes from the **Settings** page in the dashboard.

---

## Dashboard Features

### Overview
- Real-time server health, active requests, latency, error rates
- Traffic charts and server load distribution

### Server Management
- Add/remove Ollama servers
- Test connections and authentication
- View available models per server
- Enable/disable servers
- Configure priority, weight, concurrency limits

### Model Management
- See which models exist on which servers
- Compare model availability across cluster

### Playground
- Test individual models on specific servers
- **Cluster Test**: Send same prompt to all servers and compare responses & latency
- Test streaming responses

### Request Logs
- Filter by server, model, status, time range
- View routing decisions, retry counts, token usage

---

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(required)* | JWT signing key |
| `DATABASE_URL` | `sqlite:///./data/hermes.db` | Database connection |
| `DEBUG` | `false` | Enable debug mode |
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed frontend origins |
| `HEALTH_CHECK_INTERVAL_SECONDS` | `15` | How often to poll servers |
| `REQUEST_TIMEOUT_SECONDS` | `120` | Max request duration |
| `MAX_RETRIES` | `3` | Failover retry count |
| `RATE_LIMIT_REQUESTS` | `100` | Requests per window |
| `RATE_LIMIT_WINDOW` | `60` | Rate limit window (seconds) |

---

## Project Structure

```
hermes-ollama-gateway/
├── docker-compose.yml          # Docker orchestration
├── .env.example                # Environment template
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   └── app/
│       ├── main.py             # FastAPI entry point
│       ├── config.py           # Settings
│       ├── database.py         # SQLAlchemy setup
│       ├── models/             # Database models
│       ├── schemas/            # Pydantic schemas
│       ├── services/           # Business logic
│       │   ├── hermes_agent.py    # Routing engine
│       │   ├── ollama_client.py   # Ollama HTTP client
│       │   ├── health_monitor.py  # Background health checks
│       │   ├── metrics.py         # Stats collection
│       │   └── load_balancer.py   # LB algorithms
│       ├── routers/            # API endpoints
│       │   ├── auth.py
│       │   ├── servers.py
│       │   ├── models.py
│       │   ├── chat.py         # OpenAI-compatible endpoints
│       │   ├── dashboard.py
│       │   ├── logs.py
│       │   ├── health.py
│       │   └── test.py
│       ├── middleware/         # Auth, rate limiting
│       └── utils/              # Crypto, helpers
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── index.css
        ├── store/              # Zustand state
        ├── services/           # API client
        ├── components/         # Layout, shared
        └── pages/              # Dashboard, Servers, etc.
```

---

## Routing Algorithm (AUTO Mode)

The Hermes Agent scores each server using:

```
score = (load_factor × 0.35)
      + (latency_factor × 0.30)
      + (error_factor × 0.20)
      + (priority_factor × 0.10)
      + (weight_factor × 0.05)
```

Where:
- **load_factor** = 1 - (current_load / max_concurrent)
- **latency_factor** = 1 / (1 + latency_ms / 1000)
- **error_factor** = 1 - error_rate
- **priority_factor** = priority / 10
- **weight_factor** = weight / max_weight

The highest-scoring healthy server that has the requested model wins.

---

## Health Monitoring

Every `15 seconds` (configurable), Hermes:
1. Calls `/api/tags` on each Ollama server
2. Measures response latency
3. Updates model availability
4. Marks server unhealthy after 3 consecutive failures
5. Automatically recovers when health checks pass

Failed servers are removed from the routing pool immediately.

---

## Security

- **JWT authentication** for dashboard access
- **Fernet-encrypted** API keys for Ollama backends
- **Rate limiting** per IP address
- **CORS** configurable via environment
- **Input validation** via Pydantic schemas
- Secrets are never logged or sent to frontend

---

## Extending to New LLM Providers

Hermes is architected for extension. To add a new provider (e.g., vLLM, TGI):

1. Create a new client in `app/services/` implementing the same interface as `OllamaClient`
2. Add a provider type field to the `OllamaServer` model
3. Extend `HermesAgent.route_request()` to instantiate the correct client
4. No changes needed to the dashboard or API layer

---

## Development (Without Docker)

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## License

MIT
