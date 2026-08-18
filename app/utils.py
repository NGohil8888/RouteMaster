"""Small shared helpers."""


def mask_key(key: str) -> str:
    """Mask an API key for safe display/logging, e.g. 'sk-a...9f2c'."""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}...{key[-4:]}"
