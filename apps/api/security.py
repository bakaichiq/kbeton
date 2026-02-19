from __future__ import annotations

import secrets
from typing import Annotated, Optional

from fastapi import Header, HTTPException, status

from kbeton.core.config import settings


def _extract_bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return ""
    return token.strip()


def require_api_auth(
    authorization: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> None:
    if not settings.api_auth_enabled:
        return

    expected_token = settings.api_token.strip()
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API auth is enabled but API_TOKEN is not configured",
        )

    provided_token = x_api_key.strip() if x_api_key else _extract_bearer_token(authorization)
    if not provided_token or not secrets.compare_digest(provided_token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token",
            headers={"WWW-Authenticate": "Bearer"},
        )
