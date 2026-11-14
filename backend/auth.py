import os
import sqlite3
import hashlib
import hmac
import time
import re
import secrets
from datetime import datetime
from typing import Optional, Dict
from fastapi import Request, Response, HTTPException, status, Depends
from pydantic import BaseModel

from backend.config import BASE_DIR, DATA_DIR, get_data_dir

COOKIE_NAME = "cashpilot_session"
SESSION_DURATION_SEC = 24 * 3600  # 24h

def get_db_path() -> str:
    return os.path.join(get_data_dir(), "app.db")

# In-memory rate limiter: {email: [timestamp, ...]}
FAILED_ATTEMPTS: Dict[str, list] = {}
MAX_FAILED_ATTEMPTS = 5
RATE_LIMIT_WINDOW = 300  # 5 minutes in seconds

def get_secret_key() -> bytes:
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key.encode("utf-8")
    d_dir = get_data_dir()
    os.makedirs(d_dir, exist_ok=True)
    secret_path = os.path.join(d_dir, ".secret")
    if os.path.exists(secret_path):
        try:
            with open(secret_path, "rb") as f:
                return f.read().strip()
        except Exception:
            pass
    new_secret = secrets.token_bytes(32)
    try:
        with open(secret_path, "wb") as f:
            f.write(new_secret)
    except Exception:
        pass
    return new_secret

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return f"{salt.hex()}:{dk.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, hash_hex = stored_hash.split(":")
        salt = bytes.fromhex(salt_hex)
        expected_dk = bytes.fromhex(hash_hex)
        actual_dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return hmac.compare_digest(actual_dk, expected_dk)
    except Exception:
        return False

def create_session_token(user_id: int) -> str:
    secret = get_secret_key()
    expiry = int(time.time()) + SESSION_DURATION_SEC
    payload = f"{user_id}:{expiry}".encode("utf-8")
    sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return f"{user_id}:{expiry}:{sig}"

def verify_session_token(token: str) -> Optional[int]:
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return None
        user_id_str, expiry_str, sig = parts
        user_id = int(user_id_str)
        expiry = int(expiry_str)
        if time.time() > expiry:
            return None
        secret = get_secret_key()
        expected_sig = hmac.new(secret, f"{user_id}:{expiry}".encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        return user_id
    except Exception:
        return None

def init_db():
    d_dir = get_data_dir()
    os.makedirs(d_dir, exist_ok=True)
    db_file = get_db_path()
    conn = sqlite3.connect(db_file)
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # Seed demo user: demo@cashpilot.app / demo1234
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE email = ?", ("demo@cashpilot.app",))
            row = cursor.fetchone()
            if not row:
                pw_hash = hash_password("demo1234")
                cursor.execute(
                    "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                    ("Demo User", "demo@cashpilot.app", pw_hash, datetime.utcnow().isoformat())
                )
                demo_id = cursor.lastrowid
                demo_dir = os.path.join(d_dir, "users", str(demo_id))
                os.makedirs(demo_dir, exist_ok=True)
    finally:
        conn.close()

def get_user_by_id(user_id: int) -> Optional[dict]:
    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "email": row[2], "created_at": row[3]}
        return None
    finally:
        conn.close()

def get_user_by_email(email: str) -> Optional[dict]:
    conn = sqlite3.connect(get_db_path())
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, password_hash, created_at FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "email": row[2], "password_hash": row[3], "created_at": row[4]}
        return None
    finally:
        conn.close()

def create_user(name: str, email: str, password: str) -> dict:
    conn = sqlite3.connect(get_db_path())
    try:
        with conn:
            cursor = conn.cursor()
            pw_hash = hash_password(password)
            cursor.execute(
                "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (name, email, pw_hash, datetime.utcnow().isoformat())
            )
            user_id = cursor.lastrowid
            # Create user data folder
            user_dir = os.path.join(get_data_dir(), "users", str(user_id))
            os.makedirs(user_dir, exist_ok=True)
            return {"id": user_id, "name": name, "email": email}
    finally:
        conn.close()

def check_rate_limit(email: str):
    now = time.time()
    attempts = FAILED_ATTEMPTS.get(email, [])
    # Filter attempts within RATE_LIMIT_WINDOW
    recent_attempts = [t for t in attempts if now - t < RATE_LIMIT_WINDOW]
    FAILED_ATTEMPTS[email] = recent_attempts
    if len(recent_attempts) >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please wait 5 minutes before trying again."
        )

def record_failed_attempt(email: str):
    now = time.time()
    attempts = FAILED_ATTEMPTS.get(email, [])
    attempts.append(now)
    FAILED_ATTEMPTS[email] = attempts

def clear_failed_attempts(email: str):
    if email in FAILED_ATTEMPTS:
        del FAILED_ATTEMPTS[email]

def validate_auth_input(email: str, password: str, is_signup: bool = False, name: Optional[str] = None):
    if is_signup and (not name or not name.strip()):
        raise HTTPException(status_code=400, detail="Name is required")
    
    email_regex = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if not email or not re.match(email_regex, email.strip()):
        raise HTTPException(status_code=400, detail="Please enter a valid email address")

    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = verify_session_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

def set_auth_cookie(response: Response, user_id: int):
    token = create_session_token(user_id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_DURATION_SEC,
        httponly=True,
        samesite="lax",
        path="/"
    )

def clear_auth_cookie(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
