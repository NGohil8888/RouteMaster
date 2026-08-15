# Hermes Ollama Gateway

A self-hosted API routing and load-balancing platform purpose-built for Ollama-based LLM APIs.

## Features

- **Multi-Server Routing**: Connect 3-5+ Ollama instances
- **Hermes Agent**: Intelligent routing with 7 modes (Auto, Round Robin, Least Load, Fastest, Priority, Manual, Failover)
- **OpenAI-Compatible API**: `/v1/chat/completions`, `/v1/models`
- **Real-time Dashboard**: Server health, metrics, model distribution
- **Playground**: Test models and compare cluster performance
- **Health Monitoring**: Automatic failover and recovery
- **Secure**: Encrypted API keys, JWT auth, rate limiting

## Quick Start

```bash
# 1. Clone and enter directory
cd hermes-ollama-gateway

# 2. Configure
cp .env.example .env

# 3. Launch
docker compose up -d

# 4. Access
# Dashboard: http://localhost:3000
# API: http://localhost:8000/v1

#API Usage
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dummy"
)

response = client.chat.completions.create(
    model="llama3.1",
    messages=[{"role": "user", "content": "Hello!"}]
)

# Architecture
Dashboard (React) → API Gateway (FastAPI) → Hermes Agent → Ollama Servers

Routing Modes
| Mode            | Description                                                  |
| --------------- | ------------------------------------------------------------ |
| AUTO            | Intelligent scoring based on load, latency, errors, priority |
| ROUND\_ROBIN    | Distribute evenly across healthy servers                     |
| LEAST\_LOAD     | Route to server with lowest active requests                  |
| FASTEST\_SERVER | Route to lowest latency server                               |
| PRIORITY        | Route to highest priority server                             |
| MANUAL          | Use configured primary/fallback rules                        |
| FAILOVER\_ONLY  | Use preferred server, fallback on failure                    |

hermes-ollama-gateway/
├── docker-compose.yml
├── .env.example
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   └── app/
│       ├── init.py
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── models/
│       │   ├── init.py
│       │   └── server.py
│       ├── schemas/
│       │   ├── init.py
│       │   └── server.py
│       ├── services/
│       │   ├── init.py
│       │   ├── hermes_agent.py
│       │   ├── ollama_client.py
│       │   ├── health_monitor.py
│       │   ├── load_balancer.py
│       │   └── metrics.py
│       ├── routers/
│       │   ├── init.py
│       │   ├── auth.py
│       │   ├── servers.py
│       │   ├── models.py
│       │   ├── chat.py
│       │   ├── dashboard.py
│       │   ├── logs.py
│       │   ├── health.py
│       │   └── test.py
│       ├── middleware/
│       │   ├── init.py
│       │   ├── auth.py
│       │   └── rate_limit.py
│       └── utils/
│           ├── init.py
│           └── crypto.py
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
├── store/
│   └── index.js
├── services/
│   └── api.js
├── components/
│   └── Layout.jsx
└── pages/
├── Login.jsx
├── Dashboard.jsx
├── Servers.jsx
├── Models.jsx
├── Playground.jsx
├── Logs.jsx
└── Settings.jsx

Key Architecture Decisions
FastAPI Backend: Async-native, handles streaming responses from Ollama perfectly
SQLite Default: Zero-config for single-node deployment; swap to PostgreSQL via DATABASE_URL
Hermes Agent: Singleton orchestrator with pluggable routing strategies
Encrypted Credentials: Fernet encryption for API keys at rest
Health Monitor: Background asyncio task polls every 15s, auto-recovery after 3 failures
React + Tailwind: Modern, responsive dashboard with real-time updates
To extend to new LLM providers (future), add a new client class in services/ implementing the same interface as OllamaClient, then extend the Hermes Agent's route_request method.