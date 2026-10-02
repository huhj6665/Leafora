"""Opaque, high-entropy one-time token helpers."""
import hashlib
import hmac
import secrets


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, digest: str) -> bool:
    return hmac.compare_digest(token_hash(token), digest)
