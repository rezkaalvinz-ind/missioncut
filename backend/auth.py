"""Neon-backed authentication for MissionCut."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import UTC
from pathlib import Path

import psycopg
from fastapi import HTTPException
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, ConfigDict, Field


def _load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"')


_load_local_env()


class AuthPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=5, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(default="", max_length=80)


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    created_at: str


class AuthResponse(BaseModel):
    user: UserResponse
    token: str


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise HTTPException(status_code=503, detail="Authentication database is not configured")
    return value


def _auth_secret() -> bytes:
    value = os.getenv("MISSIONCUT_AUTH_SECRET", "").strip()
    if len(value) < 32:
        raise HTTPException(status_code=503, detail="Authentication secret is not configured")
    return value.encode()


def _connect():
    return psycopg.connect(_database_url(), connect_timeout=10)


def ensure_schema() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS missioncut_users (
                id BIGSERIAL PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL DEFAULT '',
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        connection.commit()


def _hash_password(password: str) -> str:
    iterations = 310_000
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)

    def encode(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).decode().rstrip("=")

    return f"pbkdf2_sha256${iterations}${encode(salt)}${encode(digest)}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False

        def padding(value: str) -> str:
            return value + "=" * (-len(value) % 4)

        salt = base64.urlsafe_b64decode(padding(salt_text))
        expected = base64.urlsafe_b64decode(padding(digest_text))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations_text))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _encode_token(user_id: int, email: str) -> str:
    header = {"alg": "HS256", "typ": "MCSession"}
    payload = {"sub": user_id, "email": email, "exp": int(time.time()) + 60 * 60 * 24 * 7}

    def encode(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    unsigned = f"{encode(header)}.{encode(payload)}"
    signature = hmac.new(_auth_secret(), unsigned.encode(), hashlib.sha256).digest()
    return f"{unsigned}.{base64.urlsafe_b64encode(signature).decode().rstrip('=')}"


def _decode_token(token: str) -> dict:
    try:
        header, payload, signature = token.split(".", 2)
        unsigned = f"{header}.{payload}"

        def padding(value: str) -> str:
            return value + "=" * (-len(value) % 4)

        expected = hmac.new(_auth_secret(), unsigned.encode(), hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(padding(signature))
        if not hmac.compare_digest(actual, expected):
            raise ValueError("invalid signature")
        data = json.loads(base64.urlsafe_b64decode(padding(payload)))
        if int(data.get("exp", 0)) < int(time.time()):
            raise ValueError("expired token")
        return data
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Invalid or expired session") from None


def _user(row) -> UserResponse:
    return UserResponse(id=row[0], email=row[1], name=row[2], created_at=row[3].astimezone(UTC).isoformat())


def register(payload: AuthPayload) -> AuthResponse:
    email = str(payload.email).lower().strip()
    name = payload.name.strip() or email.split("@", 1)[0]
    password_hash = _hash_password(payload.password)
    try:
        with _connect() as connection:
            row = connection.execute(
                """
                INSERT INTO missioncut_users (email, name, password_hash)
                VALUES (%s, %s, %s)
                RETURNING id, email, name, created_at
                """,
                (email, name, password_hash),
            ).fetchone()
            connection.commit()
    except UniqueViolation:
        raise HTTPException(status_code=409, detail="An account with this email already exists") from None
    user = _user(row)
    return AuthResponse(user=user, token=_encode_token(user.id, user.email))


def login(payload: AuthPayload) -> AuthResponse:
    email = str(payload.email).lower().strip()
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, email, name, created_at, password_hash FROM missioncut_users WHERE email = %s",
            (email,),
        ).fetchone()
    if not row or not _verify_password(payload.password, row[4]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    user = _user(row)
    return AuthResponse(user=user, token=_encode_token(user.id, user.email))


def current_user(authorization: str | None) -> UserResponse:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    data = _decode_token(authorization.split(" ", 1)[1].strip())
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, email, name, created_at FROM missioncut_users WHERE id = %s",
            (int(data["sub"]),),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return _user(row)
