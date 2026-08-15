from cryptography.fernet import Fernet
import base64
from app.config import settings


def derive_key(secret: str) -> bytes:
    """Derive a Fernet key from a secret string."""
    # Hash the secret and encode as base64-compatible key
    secret_bytes = secret.encode()
    # Pad to 32 bytes if needed
    key = base64.urlsafe_b64encode(
        (secret_bytes + b'\x00' * 32)[:32]
    )
    return key


def encrypt_value(value: str) -> str:
    """Encrypt a value using Fernet encryption."""
    key = derive_key(settings.SECRET_KEY)
    cipher = Fernet(key)
    encrypted = cipher.encrypt(value.encode())
    return encrypted.decode()


def decrypt_value(encrypted_value: str) -> str:
    """Decrypt a Fernet-encrypted value."""
    key = derive_key(settings.SECRET_KEY)
    cipher = Fernet(key)
    decrypted = cipher.decrypt(encrypted_value.encode())
    return decrypted.decode()
