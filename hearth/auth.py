"""API key authentication."""

from fastapi import Header, HTTPException

from .config import API_KEYS


def resolve_sender(authorization: str = Header(...)) -> str:
    """Extract brother name from Authorization: Bearer <key> header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization[len("Bearer ") :]
    name = API_KEYS.get(token)
    if name is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return name
