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

1. Create the project folder and files from the copy/paste output.
2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt