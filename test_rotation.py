"""
test_rotation.py
-----------------
Verifies that every gateway key can call the gateway and reports the
configured Ollama Cloud key rotation state.

Run this against a LIVE gateway (it makes real HTTP requests).

Usage:
    python test_rotation.py
    python test_rotation.py --base-url http://localhost:8000
    python test_rotation.py --keys key-one key-two key-three
"""

import argparse
import os
import sys

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

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


def test_ollama_rotation_configured(base_url: str, key: str) -> bool:
    print("\n== Test 3: Ollama Cloud key rotation is configured ==")
    r = requests.get(f"{base_url}/v1/usage", headers={"Authorization": f"Bearer {key}"}, timeout=5)
    if r.status_code != 200:
        return check(False, f"/v1/usage returned {r.status_code}")
    data = r.json()
    configured = data.get("ollama_keys_configured", 0)
    rotating = data.get("rotation_on_429", False)
    return check(configured >= 1, f"{configured} Ollama key(s) configured") and check(
        rotating == (configured > 1), "rotation state matches configured key count"
    )


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

    results.append(test_ollama_rotation_configured(args.base_url, keys[0]))

    print("\n" + "=" * 50)
    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"Result: {passed}/{total} test groups passed")
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
