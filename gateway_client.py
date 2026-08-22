"""
Example client for the Ollama Gateway that automatically rotates through
multiple API keys when one gets rate-limited (HTTP 429).

Usage:
    from gateway_client import GatewayClient

    client = GatewayClient(
        base_url="http://localhost:8000",
        api_keys=["key-one", "key-two", "key-three"],
    )

    response = client.chat(
        model="nemotron-3-super:cloud",
        messages=[{"role": "user", "content": "Hello!"}],
    )
    print(response["message"]["content"])
"""

import time
import requests


class GatewayClient:
    def __init__(self, base_url: str, api_keys: list[str]):
        if not api_keys:
            raise ValueError("Provide at least one API key")
        self.base_url = base_url.rstrip("/")
        self.api_keys = api_keys
        self._index = 0  # which key we're currently using

    def _current_key(self) -> str:
        return self.api_keys[self._index]

    def _rotate_key(self):
        self._index = (self._index + 1) % len(self.api_keys)

    def _request(self, method: str, path: str, **kwargs) -> dict:
        """Makes a request, rotating to the next key if the current one is
        rate-limited. Tries each key at most once per call."""
        attempts = 0
        last_error = None

        while attempts < len(self.api_keys):
            key = self._current_key()
            headers = kwargs.pop("headers", {})
            headers["Authorization"] = f"Bearer {key}"

            resp = requests.request(
                method, f"{self.base_url}{path}", headers=headers, **kwargs
            )

            if resp.status_code == 429:
                # This key is rate-limited — rotate to the next one and retry.
                retry_after = resp.headers.get("Retry-After", "?")
                print(f"Key ending in ...{key[-6:]} hit its rate limit "
                      f"(retry after {retry_after}s). Rotating to next key.")
                self._rotate_key()
                attempts += 1
                last_error = resp
                continue

            resp.raise_for_status()
            return resp.json()

        # Every key was rate-limited.
        raise RuntimeError(
            f"All {len(self.api_keys)} API keys are currently rate-limited. "
            f"Last response: {last_error.status_code} {last_error.text}"
        )

    def chat(self, model: str, messages: list[dict], stream: bool = False, temperature: float = None) -> dict:
        payload = {"model": model, "messages": messages, "stream": stream}
        if temperature is not None:
            payload["temperature"] = temperature
        return self._request("POST", "/v1/chat", json=payload)

    def generate(self, model: str, prompt: str, stream: bool = False, temperature: float = None) -> dict:
        payload = {"model": model, "prompt": prompt, "stream": stream}
        if temperature is not None:
            payload["temperature"] = temperature
        return self._request("POST", "/v1/generate", json=payload)

    def models(self) -> dict:
        return self._request("GET", "/v1/models")

    def usage(self) -> dict:
        """Check remaining quota for the currently active key."""
        return self._request("GET", "/v1/usage")


if __name__ == "__main__":
    # Quick demo — replace with your real keys.
    client = GatewayClient(
        base_url="http://localhost:8000",
        api_keys=["key-one", "key-two"],
    )

    result = client.chat(
        model="nemotron-3-super:cloud",
        messages=[{"role": "user", "content": "Say hello in five words."}],
    )
    print(result["message"]["content"])
