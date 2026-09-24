"""Single-workspace authentication; sessions are revocable and expire after eight hours."""

import hashlib
import hmac
import secrets
import time
from collections import deque
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel, Field

from .config import Settings


class Login(BaseModel):
    key: str = Field(min_length=1, max_length=512)


class Auth:
    def __init__(self, settings: Settings):
        self.key = settings.api_key
        self.secure = settings.environment == "production"
        if settings.environment not in {"local", "production"}:
            raise ValueError("SCRIBE_ENV must be local or production")
        if self.secure and (len(self.key) < 32 or self.key.startswith("replace-")):
            raise ValueError(
                "production requires a random SCRIBE_API_KEY of at least 32 characters"
            )
        self.sessions: dict[str, float] = {}
        self.failures: deque[float] = deque(maxlen=20)

    def authenticated(self, request: Request) -> bool:
        if not self.key:
            return True
        supplied = request.headers.get("x-api-key", "")
        if supplied and hmac.compare_digest(supplied.encode(), self.key.encode()):
            return True
        token = request.cookies.get("scribe_session", "")
        return self.sessions.get(hashlib.sha256(token.encode()).hexdigest(), 0) > time.time()

    def origin(self, request: Request):
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "cross-origin request rejected")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "cross-site request rejected")

    async def require(self, request: Request):
        if not self.authenticated(request):
            raise HTTPException(401, "sign in required")
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            self.origin(request)

    def login(self, request: Request, response: Response, key: str):
        self.origin(request)
        now = time.time()
        while self.failures and self.failures[0] < now - 60:
            self.failures.popleft()
        if len(self.failures) >= 10:
            raise HTTPException(429, "too many sign-in attempts; wait one minute")
        if not self.key or not hmac.compare_digest(key.encode(), self.key.encode()):
            self.failures.append(now)
            raise HTTPException(401, "invalid workspace key")
        self.sessions = {k: expiry for k, expiry in self.sessions.items() if expiry > now}
        if len(self.sessions) >= 100:
            raise HTTPException(429, "session capacity reached")
        token = secrets.token_urlsafe(32)
        self.sessions[hashlib.sha256(token.encode()).hexdigest()] = now + 28800
        response.set_cookie(
            "scribe_session",
            token,
            httponly=True,
            secure=self.secure,
            samesite="strict",
            max_age=28800,
            path="/",
        )

    def logout(self, request: Request, response: Response):
        self.origin(request)
        token = request.cookies.get("scribe_session", "")
        self.sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
        response.delete_cookie(
            "scribe_session", path="/", secure=self.secure, httponly=True, samesite="strict"
        )
