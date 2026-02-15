"""API key authentication."""

from fastapi import Header, HTTPException

from . import db
from .config import API_KEYS

ADMIN_NAMES = frozenset({"ian", "doot", "kamaji"})


async def resolve_sender(authorization: str = Header(...)) -> str:
    """Extract brother name from Authorization: Bearer <key> header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization[len("Bearer "):]
    # Check env-var keys first (fast, in-memory)
    name = API_KEYS.get(token)
    if name:
        return name
    # Fall back to DB-registered keys
    name = await db.get_api_key_by_key(token)
    if name:
        return name
    raise HTTPException(status_code=401, detail="Invalid API key")
