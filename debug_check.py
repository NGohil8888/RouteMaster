"""
Standalone diagnostic for the double /v1 URL bug.
Run this from the project root with your venv active:

    python debug_check.py

It does NOT need the server running - it imports your local app code
directly and shows you exactly what URL it would build.
"""

import hashlib
import os
import sys

os.environ.setdefault("OLLAMA_API_KEYS", "debug_dummy_key")

print("=" * 70)
print("1. Which proxy.py is actually being imported?")
print("=" * 70)
import app.proxy as proxy
print("File path:", proxy.__file__)
with open(proxy.__file__, "rb") as f:
    content = f.read()
print("MD5 hash :", hashlib.md5(content).hexdigest())
print("Contains fixed strip logic:", b'target_path[len("v1/")' in content)
print()

print("=" * 70)
print("2. What does ollama_openai_base resolve to?")
print("=" * 70)
from app.config import settings
print("OLLAMA_BASE_URL   :", settings.ollama_base_url)
print("ollama_api_base   :", settings.ollama_api_base)
print("ollama_openai_base:", settings.ollama_openai_base)
print()

print("=" * 70)
print("3. Simulate the exact path FastAPI passes for /v1/chat/completions")
print("=" * 70)
# This mirrors main.py's proxy_v1(): path=f"v1/{path}" where the route
# variable `path` is "chat/completions" (FastAPI strips the /v1/ prefix)
incoming_path = "v1/chat/completions"
target_path = incoming_path.lstrip("/")
if target_path.startswith("v1/"):
    target_path = target_path[len("v1/") :]
base_url = settings.ollama_openai_base
final_url = f"{base_url}/{target_path}" if target_path else base_url

print("incoming_path (from main.py):", incoming_path)
print("target_path (after strip)   :", target_path)
print("FINAL URL THAT WOULD BE HIT :", final_url)
print()

if "/v1/v1/" in final_url:
    print("!!! BUG STILL PRESENT: double /v1 detected in the URL above.")
    print("    This means the OLD proxy.py is what's actually running/imported.")
    sys.exit(1)
else:
    print("OK: URL looks correct, single /v1.")
    print()
    print("If your live server is STILL 404ing with double /v1, the server")
    print("process itself has not been restarted with this file. Kill the")
    print("running `python run.py` process completely (Ctrl+C, then confirm")
    print("it's gone in Task Manager) and start it again.")
