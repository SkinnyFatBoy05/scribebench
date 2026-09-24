"""Explicit operator-authorised, time-bounded synthetic pilot policy and audit records."""

import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Participant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,60}$")
    key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,100}$")


class PilotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pilot_id: str = Field(min_length=1, max_length=100)
    owner: str = Field(min_length=1, max_length=100)
    authorised_by: str = Field(min_length=1, max_length=100)
    authorised_at: datetime
    expires_at: datetime
    synthetic_only: bool
    participants: list[Participant] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def validate_authorisation(self):
        if not self.synthetic_only:
            raise ValueError("pilot must remain synthetic-only")
        if self.authorised_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ValueError("pilot dates require timezone offsets")
        if self.authorised_at > datetime.now(UTC) or self.expires_at <= self.authorised_at:
            raise ValueError("invalid authorisation window")
        ids = [p.id for p in self.participants]
        if len(ids) != len(set(ids)) or "operator" in ids or "local" in ids:
            raise ValueError("participant IDs must be unique and cannot be reserved")
        return self


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str
    usability: int = Field(ge=1, le=5)
    accuracy: int = Field(ge=1, le=5)
    issue: str = Field(pattern=r"^(none|omission|unsupported_claim|citation|workflow|other)$")
    comment: str = Field(default="", max_length=2000)
    synthetic_confirmed: bool


class Pilot:
    def __init__(self, path: str, database: Path):
        self.database = database
        self.manifest = (
            PilotManifest.model_validate_json(Path(path).read_text("utf-8")) if path else None
        )
        self.keys: dict[str, str] = {}
        if self.manifest:
            for person in self.manifest.participants:
                key = os.getenv(person.key_env, "")
                if len(key) < 32:
                    raise ValueError(
                        "every pilot participant needs an independent strong server-side key"
                    )
                if key in self.keys.values():
                    raise ValueError("pilot participant keys must be unique")
                self.keys[person.id] = key

    def initialize(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS pilot_events (
                id TEXT PRIMARY KEY, pilot_id TEXT, actor TEXT NOT NULL, action TEXT NOT NULL,
                job_id TEXT, created_at TEXT NOT NULL, detail_json TEXT NOT NULL)""")

    def active(self):
        return self.manifest is not None and datetime.now(UTC) < self.manifest.expires_at

    def require_active(self):
        if not self.active():
            raise HTTPException(403, "pilot is not authorised or has expired")

    def status(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            rows = db.execute(
                "SELECT action, COUNT(*) FROM pilot_events WHERE pilot_id = ? GROUP BY action",
                (self.manifest.pilot_id if self.manifest else None,),
            ).fetchall()
        return {
            "status": "active"
            if self.active()
            else "awaiting_authorisation"
            if not self.manifest
            else "expired",
            "synthetic_only": True,
            "pilot_id": self.manifest.pilot_id if self.manifest else None,
            "expires_at": self.manifest.expires_at.isoformat() if self.manifest else None,
            "counts": dict(rows),
            "participant_count": len(self.keys),
        }

    def record(
        self, actor: str, action: str, job_id: str | None = None, detail: dict | None = None
    ):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(
                "INSERT INTO pilot_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    self.manifest.pilot_id if self.manifest else None,
                    actor,
                    action,
                    job_id,
                    datetime.now(UTC).isoformat(),
                    json.dumps(detail or {}),
                ),
            )

    def report(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM pilot_events WHERE pilot_id = ? ORDER BY created_at",
                (self.manifest.pilot_id if self.manifest else None,),
            ).fetchall()
        return {"pilot": self.status(), "events": [dict(row) for row in rows]}
