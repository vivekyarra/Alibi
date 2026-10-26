"""Cognito reviewer authentication for AWS mode (SPEC 10.1, 13). Verifies the ID token signature against the
user pool JWKS and requires membership of the `reviewer` group."""

from __future__ import annotations

import os
from functools import lru_cache

import jwt
from fastapi import HTTPException


@lru_cache(maxsize=1)
def _jwks() -> jwt.PyJWKClient:
    region = os.environ["COGNITO_REGION"]
    pool = os.environ["COGNITO_USER_POOL_ID"]
    return jwt.PyJWKClient(f"https://cognito-idp.{region}.amazonaws.com/{pool}/.well-known/jwks.json")


def verify_cognito_reviewer(token: str) -> str:
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=os.environ["COGNITO_CLIENT_ID"])
    except Exception as e:
        raise HTTPException(401, f"invalid token: {type(e).__name__}") from e
    if "reviewer" not in (claims.get("cognito:groups") or []):
        raise HTTPException(403, "not in reviewer group")
    return str(claims.get("email") or claims.get("cognito:username") or claims.get("sub"))
