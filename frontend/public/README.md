#!/bin/bash
# Copy this script to your Ollama server to enable CORS for Hermes Gateway

set -e

# Stop the Ollama service
sudo systemctl stop ollama

# Wait a moment
sleep 2

# Start Ollama with CORS enabled
# For Linux/Mac:
OLLAMA_ORIGINS="*" ollama serve &

# Wait for server to start
sleep 5

echo "Ollama started with CORS enabled for all origins (*)"
echo "Press Ctrl+C to stop the server"

wait
