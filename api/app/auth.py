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
    def __init__(self, settings: Settings, participant_keys: dict[str, str] | None = None):
        self.key = settings.api_key
        self.secure = settings.environment == "production"
        if settings.environment not in {"local", "production"}:
            raise ValueError("SCRIBE_ENV must be local or production")
        if self.secure and (len(self.key) < 32 or self.key.startswith("replace-")):
            raise ValueError(
                "production requires a random SCRIBE_API_KEY of at least 32 characters"
            )
        self.keys = {"operator": self.key, **(participant_keys or {})}
        if participant_keys and (not self.secure or len(self.key) < 32):
            raise ValueError("authorised pilots require production mode, HTTPS and an operator key")
        if len(set(self.keys.values())) != len(self.keys):
            raise ValueError("operator and participant keys must be distinct")
        self.sessions: dict[str, tuple[float, str]] = {}
        self.failures: deque[float] = deque(maxlen=20)

    def authenticated(self, request: Request) -> bool:
        return self.identity(request) is not None

    def key_identity(self, key: str) -> str | None:
        identity = None
        for actor, expected in self.keys.items():
            if key and expected and hmac.compare_digest(key.encode(), expected.encode()):
                identity = actor
        return identity

    def identity(self, request: Request) -> str | None:
        if not self.key:
            return "local"
        supplied = request.headers.get("x-api-key", "")
        actor = self.key_identity(supplied)
        if actor:
            return actor
        token = request.cookies.get("scribe_session", "")
        expiry, actor = self.sessions.get(hashlib.sha256(token.encode()).hexdigest(), (0, ""))
        return actor if expiry > time.time() else None

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
        actor = self.key_identity(key)
        if not actor:
            self.failures.append(now)
            raise HTTPException(401, "invalid workspace key")
        self.sessions = {k: entry for k, entry in self.sessions.items() if entry[0] > now}
        if len(self.sessions) >= 100:
            raise HTTPException(429, "session capacity reached")
        token = secrets.token_urlsafe(32)
        self.sessions[hashlib.sha256(token.encode()).hexdigest()] = (now + 28800, actor)
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
