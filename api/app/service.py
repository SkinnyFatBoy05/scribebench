from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from pathlib import Path

import httpx

from .config import Settings
from .database import Database
from .metrics import Metrics
from .model import DraftModel, parse_transcript
from .schemas import JobStatus, StructuredDraft, SyntheticCase

logger = logging.getLogger("scribebench.jobs")


def load_cases(path: Path) -> list[SyntheticCase]:
    return [SyntheticCase.model_validate(item) for item in json.loads(path.read_text("utf-8"))]


def validate_grounding(transcript: str, draft: StructuredDraft) -> None:
    source = {line.number: line.text for line in parse_transcript(transcript)}
    speakers = {line.number: line.speaker for line in parse_transcript(transcript)}
    if "Patient" not in speakers.values() and not draft.abstained:
        raise ValueError("ambiguous transcripts must abstain")
    for evidence in draft.observations.evidence:
        if speakers.get(evidence.line) != "Clinician":
            raise ValueError("observations require clinician evidence")
    for section in (draft.reason_for_visit, draft.history, draft.observations):
        if section.text and not section.evidence:
            raise ValueError("grounded sections require evidence")
        for evidence in section.evidence:
            if source.get(evidence.line) != evidence.quote:
                raise ValueError("evidence quote does not match the referenced transcript line")
    for contradiction in draft.contradictions:
        if any(line not in source for line in contradiction.lines):
            raise ValueError("contradiction references an unknown transcript line")


class JobRunner:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        model: DraftModel,
        metrics: Metrics,
    ):
        self.settings = settings
        self.database = database
        self.model = model
        self.models: dict[str, DraftModel] | None = None
        self.metrics = metrics
        self.queue: asyncio.Queue[str | None] = asyncio.Queue(settings.queue_capacity)
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._worker(index), name=f"scribebench-worker-{index}")
            for index in range(self.settings.workers)
        ]
        for job_id in self.database.pending_job_ids():
            await self.queue.put(job_id)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    def submit(self, job_id: str) -> None:
        self.queue.put_nowait(job_id)

    async def _worker(self, worker_index: int) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                if job_id is None:
                    return
                await self._process(job_id, worker_index)
            except Exception:
                logger.error(json.dumps({"event": "worker_error", "job_id": job_id}))
            finally:
                self.queue.task_done()

    async def _process(self, job_id: str, worker_index: int) -> None:
        job = self.database.get_job(job_id)
        if not job:
            return
        model = self.model
        if self.models is not None:
            model = self.models.get(str(job["model_version"]))
            if model is None:
                self.database.set_status(job_id, JobStatus.FAILED, "model_configuration_changed")
                return
        if int(job["attempts"]) > self.settings.max_retries:
            self.database.set_status(job_id, JobStatus.FAILED, "retry_budget_exhausted")
            return
        while True:
            attempt = self.database.set_running(job_id)
            started = time.perf_counter()
            try:
                result = await asyncio.wait_for(
                    model.generate(str(job["transcript"])),
                    timeout=self.settings.model_timeout_seconds,
                )
                validate_grounding(str(job["transcript"]), result.draft)
                latency_ms = (time.perf_counter() - started) * 1000
                self.database.save_draft(
                    job_id,
                    result.draft,
                    latency_ms=latency_ms,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )
                self.metrics.record_job(
                    "draft_ready", latency_ms, result.input_tokens, result.output_tokens
                )
                logger.info(
                    json.dumps(
                        {
                            "event": "job_completed",
                            "job_id": job_id,
                            "worker": worker_index,
                            "attempt": attempt,
                            "model_version": job["model_version"],
                            "latency_ms": round(latency_ms, 2),
                            "input_tokens": result.input_tokens,
                            "output_tokens": result.output_tokens,
                        }
                    )
                )
                return
            except Exception as error:  # bounded and converted to a non-sensitive code
                latency_ms = (time.perf_counter() - started) * 1000
                error_code = type(error).__name__.lower()
                permanent = isinstance(
                    error, httpx.HTTPStatusError
                ) and error.response.status_code not in {408, 429, 500, 502, 503, 504}
                if attempt <= self.settings.max_retries and not permanent:
                    self.database.set_status(job_id, JobStatus.RETRYING, error_code)
                    await asyncio.sleep(self.settings.retry_delay_seconds * attempt)
                    continue
                self.database.set_status(job_id, JobStatus.FAILED, error_code)
                self.metrics.record_job("failed", latency_ms, 0, 0)
                logger.error(
                    json.dumps(
                        {
                            "event": "job_failed",
                            "job_id": job_id,
                            "worker": worker_index,
                            "attempts": attempt,
                            "model_version": job["model_version"],
                            "error_code": error_code,
                        }
                    )
                )
                return


def create_job(
    database: Database,
    *,
    transcript: str,
    idempotency_key: str,
    case_id: str | None,
    model_version: str,
) -> tuple[dict[str, object], bool]:
    digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
    return database.create_job(
        job_id=str(uuid.uuid4()),
        idempotency_key=idempotency_key,
        case_id=case_id,
        transcript=transcript,
        transcript_sha256=digest,
        model_version=model_version,
    )
