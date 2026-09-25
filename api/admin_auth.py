# api/admin_auth.py
"""Shared admin authentication dependency.

All management routes require a Bearer token (ADMIN_API_TOKEN). Two callers:

1. Machine clients (MCP, scripts): send ``Authorization: Bearer <token>`` directly.
2. Web panel: Kong terminates Basic-auth and a request-transformer injects the
   same Bearer token upstream, so the backend still performs a single, uniform
   check (defense in depth — the raw admin token never reaches the browser).
"""

import os
import secrets

from fastapi import Header, HTTPException

ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "")


def verify_admin_token(authorization: str = Header(None)) -> None:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise HTTPException(status_code=401, detail="Invalid Authorization format")
    token = authorization[len(prefix):]
    if not ADMIN_API_TOKEN or not secrets.compare_digest(token, ADMIN_API_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid admin token")
