"""
test_rotation.py
-----------------
Verifies that:
  1. Every key in GATEWAY_API_KEYS is valid and can call the gateway.
  2. Each key's rate limit is enforced independently.
  3. GatewayClient correctly rotates to the next key once one is
     rate-limited, instead of failing.

Run this against a LIVE gateway (it makes real HTTP requests), ideally
with a low RATE_LIMIT_PER_MINUTE set in .env so the test finishes fast,
e.g.:

    RATE_LIMIT_PER_MINUTE=3

Usage:
    python test_rotation.py
    python test_rotation.py --base-url http://localhost:8000
    python test_rotation.py --keys key-one key-two key-three
"""

import argparse
import os
import sys
import time

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from gateway_client import GatewayClient


def get_keys_from_env() -> list[str]:
    raw = os.environ.get("GATEWAY_API_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]


def check(condition: bool, label: str):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}")
    return condition


def test_each_key_individually(base_url: str, keys: list[str]) -> bool:
    print("\n== Test 1: each key can independently call the gateway ==")
    all_ok = True
    for key in keys:
        try:
            r = requests.get(
                f"{base_url}/v1/usage",
                headers={"Authorization": f"Bearer {key}"},
                timeout=5,
            )
            ok = check(
                r.status_code == 200,
                f"key ...{key[-6:]} -> /v1/usage returned {r.status_code}",
            )
            all_ok = all_ok and ok
        except requests.RequestException as e:
            all_ok = check(False, f"key ...{key[-6:]} -> request failed ({e})")
    return all_ok


def test_invalid_key_rejected(base_url: str) -> bool:
    print("\n== Test 2: an invalid key is rejected ==")
    r = requests.get(
        f"{base_url}/v1/usage",
        headers={"Authorization": "Bearer not-a-real-key"},
        timeout=5,
    )
    return check(r.status_code == 403, f"invalid key -> got {r.status_code} (expected 403)")


def test_rate_limit_enforced(base_url: str, key: str) -> tuple[bool, int]:
    print(f"\n== Test 3: rate limit trips for a single key (...{key[-6:]}) ==")
    r = requests.get(f"{base_url}/v1/usage", headers={"Authorization": f"Bearer {key}"}, timeout=5)
    limit = r.json().get("limit_per_minute", 0)

    if limit <= 0:
        print("  Rate limiting is disabled (RATE_LIMIT_PER_MINUTE=0) — skipping this test.")
        print("  Set RATE_LIMIT_PER_MINUTE to a small number (e.g. 3) in .env to test rotation.")
        return True, limit

    print(f"  Configured limit: {limit}/min. Sending {limit + 2} requests with this key...")
    hit_429 = False
    for i in range(limit + 2):
        r = requests.post(
            f"{base_url}/v1/generate",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "does-not-matter-for-this-test", "prompt": "x"},
            timeout=5,
        )
        if r.status_code == 429:
            hit_429 = True
            print(f"  request {i+1}: 429 (rate limited) as expected")
            break
        else:
            print(f"  request {i+1}: {r.status_code}")

    return check(hit_429, "rate limit correctly triggered a 429"), limit


def test_client_rotation(base_url: str, keys: list[str]):
    print("\n== Test 4: GatewayClient rotates to the next key automatically ==")
    if len(keys) < 2:
        print("  Only one key configured — rotation needs at least 2. Skipping.")
        return True

    client = GatewayClient(base_url=base_url, api_keys=keys)

    print(f"  Client starting on key ...{client._current_key()[-6:]}")
    print("  Exhausting current key's quota via /v1/generate calls...")

    # Drain the first key's quota by hitting /v1/generate directly with it
    # (bypassing the client so we control exactly which key gets exhausted).
    first_key = client._current_key()
    r = requests.get(f"{base_url}/v1/usage", headers={"Authorization": f"Bearer {first_key}"}, timeout=5)
    limit = r.json().get("limit_per_minute", 0)

    if limit <= 0:
        print("  Rate limiting disabled — can't demonstrate rotation. Skipping.")
        return True

    for _ in range(limit):
        requests.post(
            f"{base_url}/v1/generate",
            headers={"Authorization": f"Bearer {first_key}"},
            json={"model": "does-not-matter-for-this-test", "prompt": "x"},
            timeout=5,
        )

    print(f"  Key ...{first_key[-6:]} should now be exhausted.")
    print("  Making one more call through GatewayClient — it should rotate automatically...")

    try:
        client._request(
            "POST", "/v1/generate",
            json={"model": "does-not-matter-for-this-test", "prompt": "x"},
        )
        rotated = client._current_key() != first_key
    except Exception as e:
        # Even if the upstream Ollama call fails (e.g. bad model name),
        # what we care about is whether it got PAST the rate limit check
        # by rotating — i.e. it didn't raise on 429.
        rotated = client._current_key() != first_key
        print(f"  (Note: request itself errored downstream, but that's OK for this test: {e})")

    return check(rotated, f"client rotated off the exhausted key (now on ...{client._current_key()[-6:]})")


def main():
    parser = argparse.ArgumentParser(description="Test gateway API keys and rotation")
    parser.add_argument("--base-url", default=os.environ.get("GATEWAY_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--keys", nargs="+", default=None, help="Override keys instead of reading from .env")
    args = parser.parse_args()

    keys = args.keys or get_keys_from_env()

    if not keys:
        print("No API keys found. Set GATEWAY_API_KEYS in .env, or pass --keys key1 key2 ...")
        sys.exit(1)

    print(f"Testing gateway at {args.base_url}")
    print(f"Keys under test: {[f'...{k[-6:]}' for k in keys]}")

    # Basic reachability check first. The gateway itself may return 200 or
    # 503 depending on whether Ollama is reachable — either means the
    # gateway process is up and responding, which is all we're checking here.
    try:
        r = requests.get(f"{args.base_url}/v1/health", timeout=5)
        check(
            r.status_code in (200, 503),
            f"gateway is reachable ({args.base_url}/v1/health -> {r.status_code})",
        )
        if r.status_code == 503:
            print("  Note: gateway is up, but Ollama itself isn't reachable right now.")
            print("  Key/rotation tests below don't require Ollama to succeed, so continuing.")
    except requests.RequestException as e:
        print(f"[FAIL] Could not reach gateway at {args.base_url}: {e}")
        print("Make sure `uvicorn main:app` is running first.")
        sys.exit(1)

    results = []
    results.append(test_each_key_individually(args.base_url, keys))
    results.append(test_invalid_key_rejected(args.base_url))

    rate_limit_ok, limit = test_rate_limit_enforced(args.base_url, keys[0])
    results.append(rate_limit_ok)

    # Give the window a moment before the rotation test reuses the same key,
    # only relevant if limit is very low and tests run back-to-back quickly.
    time.sleep(1)
    results.append(test_client_rotation(args.base_url, keys))

    print("\n" + "=" * 50)
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"Result: {passed}/{total} test groups passed")
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
