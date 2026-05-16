# core / security.py
from datetime import datetime, timedelta, timezone
from typing import Any
import uuid
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import HTTPException, Request, status
from core.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Password ──────────────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    # compare_digest is used internally by passlib — timing-safe
    return pwd_context.verify(plain, hashed)


# ── JWT ───────────────────────────────────────────────────────────────────────


def create_access_token(owner_id: str) -> tuple[str, str]:
    """Returns (token, jti). jti used for blocklist on logout."""
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": owner_id,
        "role": "owner",
        "iat": now,
        "exp": now + timedelta(hours=settings.JWT_EXPIRY_HOURS),
        "jti": jti,  # unique token id — used for blocklist
    }
    token = jwt.encode(payload, settings.JWT_PRIVATE_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, jti


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "TOKEN_INVALID", "message": "Invalid or expired token"},
        )


def get_token_from_request(request: Request) -> str | None:
    return request.cookies.get("token")


# ── Cookie helpers ────────────────────────────────────────────────────────────


def set_auth_cookie(response, token: str) -> None:
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        secure=settings.is_production,  # False in local (HTTP), True in prod (HTTPS)
        samesite="strict",
        max_age=settings.JWT_EXPIRY_HOURS * 3600,
        path="/",
    )


def clear_auth_cookie(response) -> None:
    response.delete_cookie(key="token", path="/")
