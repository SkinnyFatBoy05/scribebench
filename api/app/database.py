from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import JobStatus, StructuredDraft


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._write_lock = threading.RLock()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._write_lock, self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    case_id TEXT,
                    transcript TEXT NOT NULL,
                    transcript_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    draft_json TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT,
                    latency_ms REAL,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_jobs_status_updated ON jobs(status, updated_at)"
            )

    def create_job(
        self,
        *,
        job_id: str,
        idempotency_key: str,
        case_id: str | None,
        transcript: str,
        transcript_sha256: str,
        model_version: str,
    ) -> tuple[dict[str, Any], bool]:
        timestamp = utc_now()
        with self._write_lock, self._connect() as connection:
            try:
                connection.execute(
                    """
                    INSERT INTO jobs (
                        id, idempotency_key, case_id, transcript, transcript_sha256,
                        status, model_version, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        job_id,
                        idempotency_key,
                        case_id,
                        transcript,
                        transcript_sha256,
                        JobStatus.QUEUED.value,
                        model_version,
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError:
                row = connection.execute(
                    "SELECT * FROM jobs WHERE idempotency_key = ?", (idempotency_key,)
                ).fetchone()
                if row is None:
                    raise
                return self._row(row), False
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            assert row is not None
            return self._row(row), True

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row(row) if row else None

    def get_by_key(self, key: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return self._row(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row(row) for row in rows]

    def pending_job_ids(self) -> list[str]:
        pending = (
            JobStatus.QUEUED.value,
            JobStatus.RUNNING.value,
            JobStatus.RETRYING.value,
        )
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id FROM jobs WHERE status IN (?, ?, ?) ORDER BY created_at", pending
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def set_running(self, job_id: str) -> int:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = ?, attempts = attempts + 1, error_code = NULL, updated_at = ?
                WHERE id = ?
                """,
                (JobStatus.RUNNING.value, utc_now(), job_id),
            )
            row = connection.execute("SELECT attempts FROM jobs WHERE id = ?", (job_id,)).fetchone()
            return int(row["attempts"]) if row else 0

    def save_draft(
        self,
        job_id: str,
        draft: StructuredDraft,
        *,
        status: JobStatus = JobStatus.DRAFT_READY,
        latency_ms: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET draft_json = ?, status = ?, updated_at = ?, error_code = NULL,
                    latency_ms = COALESCE(?, latency_ms),
                    input_tokens = COALESCE(?, input_tokens),
                    output_tokens = COALESCE(?, output_tokens)
                WHERE id = ?
                """,
                (
                    draft.model_dump_json(),
                    status.value,
                    utc_now(),
                    latency_ms,
                    input_tokens,
                    output_tokens,
                    job_id,
                ),
            )

    def set_status(self, job_id: str, status: JobStatus, error_code: str | None = None) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status = ?, error_code = ?, updated_at = ? WHERE id = ?",
                (status.value, error_code, utc_now(), job_id),
            )

    def approve(self, job_id: str) -> None:
        timestamp = utc_now()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs SET status = ?, approved_at = ?, updated_at = ?
                WHERE id = ? AND status IN (?, ?)
                """,
                (
                    JobStatus.APPROVED.value,
                    timestamp,
                    timestamp,
                    job_id,
                    JobStatus.DRAFT_READY.value,
                    JobStatus.UNDER_REVIEW.value,
                ),
            )

    def delete_job(self, job_id: str) -> bool:
        with self._write_lock, self._connect() as connection:
            cursor = connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            return cursor.rowcount > 0

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        value = dict(row)
        raw_draft = value.pop("draft_json")
        value["draft"] = json.loads(raw_draft) if raw_draft else None
        return value
