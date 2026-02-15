"""Bearer token authentication for the Ember server.

Reuses the brother's Hearth API key — no separate Ember key needed.
The Ember server validates incoming requests against HEARTH_API_KEY
(with MAILBOX_API_KEY fallback for transition).
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException


def get_api_key() -> str:
    """Read the API key from the environment (HEARTH_API_KEY or MAILBOX_API_KEY).

    Raises RuntimeError if neither is set.
    """
    key = os.environ.get("HEARTH_API_KEY") or os.environ.get("MAILBOX_API_KEY")
    if not key:
        raise RuntimeError(
            "HEARTH_API_KEY (or MAILBOX_API_KEY) environment variable is required"
        )
    return key


async def verify_token(authorization: str = Header(...)) -> str:
    """FastAPI dependency that validates Bearer token against the Hearth API key.

    Returns the validated token on success.
    """
    expected = get_api_key()

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")

    token = authorization[7:]  # Strip "Bearer "
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return token
