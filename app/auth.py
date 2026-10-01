from __future__ import annotations

import base64
import binascii
import getpass
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
from pathlib import Path

from .database import connection, init_db

ROOT = Path(__file__).resolve().parents[1]
SECRET_PATH = Path(os.environ.get("UFO_SESSION_KEY_PATH", ROOT / "data" / "session.key"))
COOKIE_NAME = "ufo_admin_session"
SESSION_SECONDS = 12 * 60 * 60
PBKDF2_ROUNDS = 600_000


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def signing_key() -> bytes:
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with SECRET_PATH.open("xb") as secret_file:
            secret_file.write(secrets.token_bytes(48))
    except FileExistsError:
        pass
    return SECRET_PATH.read_bytes()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${_b64(salt)}${_b64(derived)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(rounds))
        return hmac.compare_digest(actual, _unb64(expected))
    except (ValueError, TypeError):
        return False


def create_session(username: str) -> str:
    payload = _b64(json.dumps({"u": username, "e": int(time.time()) + SESSION_SECONDS}, separators=(",", ":")).encode())
    signature = _b64(hmac.new(signing_key(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def session_username(token: str | None) -> str | None:
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    expected = hmac.new(signing_key(), payload.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expected, _unb64(signature)):
            return None
        claims = json.loads(_unb64(payload))
        if int(claims["e"]) < time.time():
            return None
        with connection() as conn:
            user = conn.execute("SELECT username FROM users WHERE username = ?", (claims["u"],)).fetchone()
        return claims["u"] if user else None
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, binascii.Error):
        return None


def create_admin(username: str, password: str) -> None:
    normalized = username.strip()
    if not normalized or len(normalized) > 80:
        raise ValueError("Username must contain 1 to 80 characters.")
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters.")
    init_db()
    with connection() as conn:
        if conn.execute("SELECT 1 FROM admins WHERE id = 1").fetchone():
            raise ValueError("An admin account already exists.")
        password_hash = hash_password(password)
        conn.execute("INSERT INTO admins (id, username, password_hash) VALUES (1, ?, ?)", (normalized, password_hash))
        conn.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, 'admin')", (normalized, password_hash))
    signing_key()


def create_user(username: str, password: str) -> None:
    normalized = username.strip()
    if not normalized or len(normalized) > 80:
        raise ValueError("Username must contain 1 to 80 characters.")
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters.")
    init_db()
    with connection() as conn:
        if conn.execute("SELECT 1 FROM users WHERE username = ?", (normalized,)).fetchone():
            raise ValueError("That username is already in use.")
        conn.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'user')", (normalized, hash_password(password)))
    signing_key()


def _cli() -> None:
    if len(sys.argv) != 2 or sys.argv[1] != "create-admin":
        raise SystemExit("Usage: python -m app.auth create-admin")
    username = input("Admin username: ").strip()
    password = getpass.getpass("Admin password (12+ characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if not hmac.compare_digest(password, confirm):
        raise SystemExit("Passwords did not match.")
    try:
        create_admin(username, password)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print("Single admin account created. Sign in at /login.")


if __name__ == "__main__":
    _cli()
