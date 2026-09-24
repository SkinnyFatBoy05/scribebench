from __future__ import annotations

import hmac
import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .config import Settings
from .database import Database
from .metrics import Metrics
from .model import build_model
from .schemas import (
    CreateJobRequest,
    EditDraftRequest,
    HealthResponse,
    JobStatus,
    JobView,
    SyntheticCase,
)
from .service import JobRunner, create_job, load_cases, validate_grounding

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("scribebench.http")


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings.from_env()
    database = Database(configured.db_path)
    metrics = Metrics()
    runner = JobRunner(configured, database, build_model(configured), metrics)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database.initialize()
        await runner.start()
        app.state.ready = True
        if configured.seed_demo and not database.list_jobs(limit=1):
            demo = load_cases(configured.data_path)[0]
            job, created = create_job(
                database,
                transcript=demo.transcript,
                idempotency_key=f"seed-{demo.id}",
                case_id=demo.id,
                model_version=configured.model_version,
            )
            if created:
                runner.submit(str(job["id"]))
        yield
        app.state.ready = False
        await runner.stop()

    app = FastAPI(
        title="ScribeBench API",
        version="0.1.0",
        description="Synthetic transcript-to-draft portfolio service.",
        lifespan=lifespan,
    )
    app.state.settings = configured
    app.state.database = database
    app.state.runner = runner
    app.state.metrics = metrics
    app.state.ready = False
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key", "Idempotency-Key", "X-Request-ID"],
    )

    async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
        if configured.api_key and (
            not x_api_key or not hmac.compare_digest(x_api_key, configured.api_key)
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:100]
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            metrics.record_request(request.method, request.url.path, 500)
            logger.exception(
                json.dumps(
                    {
                        "event": "request_failed",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                    }
                )
            )
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        metrics.record_request(request.method, request.url.path, response.status_code)
        logger.info(
            json.dumps(
                {
                    "event": "request_completed",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                }
            )
        )
        return response

    def job_or_404(job_id: str) -> dict[str, object]:
        job = database.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            model_provider=configured.model_provider,
            model_version=configured.model_version,
        )

    @app.get("/api/ready")
    async def ready() -> dict[str, object]:
        if not app.state.ready:
            raise HTTPException(status_code=503, detail="service is starting")
        return {"ready": True, "queue_depth": runner.queue.qsize()}

    @app.get("/metrics", response_class=PlainTextResponse)
    async def prometheus_metrics() -> str:
        return metrics.render(runner.queue.qsize())

    @app.get(
        "/api/cases",
        response_model=list[SyntheticCase],
        dependencies=[Depends(require_api_key)],
    )
    async def cases() -> list[SyntheticCase]:
        return load_cases(configured.data_path)

    @app.post(
        "/api/jobs",
        response_model=JobView,
        status_code=202,
        dependencies=[Depends(require_api_key)],
    )
    async def submit_job(
        payload: CreateJobRequest,
        response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ) -> dict[str, object]:
        existing = database.get_by_key(idempotency_key)
        if existing:
            if (
                existing["transcript"] != payload.transcript
                or existing["case_id"] != payload.case_id
            ):
                raise HTTPException(status_code=409, detail="idempotency key has different input")
            response.status_code = 200
            return existing
        if runner.queue.full():
            raise HTTPException(status_code=503, detail="job queue is at capacity")
        job, created = create_job(
            database,
            transcript=payload.transcript,
            idempotency_key=idempotency_key,
            case_id=payload.case_id,
            model_version=configured.model_version,
        )
        if created:
            runner.submit(str(job["id"]))
        else:
            response.status_code = 200
        return job

    @app.get(
        "/api/jobs",
        response_model=list[JobView],
        dependencies=[Depends(require_api_key)],
    )
    async def list_job_views(
        limit: int = Query(default=50, ge=1, le=100),
    ) -> list[dict[str, object]]:
        return database.list_jobs(limit)

    @app.get(
        "/api/jobs/{job_id}",
        response_model=JobView,
        dependencies=[Depends(require_api_key)],
    )
    async def get_job(job_id: str) -> dict[str, object]:
        return job_or_404(job_id)

    @app.patch(
        "/api/jobs/{job_id}/draft",
        response_model=JobView,
        dependencies=[Depends(require_api_key)],
    )
    async def edit_draft(job_id: str, payload: EditDraftRequest) -> dict[str, object]:
        job = job_or_404(job_id)
        if job["status"] not in {JobStatus.DRAFT_READY.value, JobStatus.UNDER_REVIEW.value}:
            raise HTTPException(status_code=409, detail="job is not editable")
        try:
            validate_grounding(str(job["transcript"]), payload.draft)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        database.save_draft(job_id, payload.draft, status=JobStatus.UNDER_REVIEW)
        return job_or_404(job_id)

    @app.post(
        "/api/jobs/{job_id}/approve",
        response_model=JobView,
        dependencies=[Depends(require_api_key)],
    )
    async def approve_job(job_id: str) -> dict[str, object]:
        job = job_or_404(job_id)
        if job["status"] not in {JobStatus.DRAFT_READY.value, JobStatus.UNDER_REVIEW.value}:
            raise HTTPException(status_code=409, detail="job is not ready for approval")
        if not job["draft"] or job["draft"].get("abstained"):
            raise HTTPException(status_code=409, detail="abstained drafts cannot be approved")
        database.approve(job_id)
        return job_or_404(job_id)

    @app.get(
        "/api/jobs/{job_id}/export",
        dependencies=[Depends(require_api_key)],
    )
    async def export_job(job_id: str) -> JSONResponse:
        job = job_or_404(job_id)
        if job["status"] != JobStatus.APPROVED.value:
            raise HTTPException(status_code=409, detail="human approval is required before export")
        exported = {
            "job_id": job["id"],
            "case_id": job["case_id"],
            "model_version": job["model_version"],
            "transcript_sha256": job["transcript_sha256"],
            "approved_at": job["approved_at"],
            "draft": job["draft"],
            "disclaimer": "Synthetic portfolio output; not for clinical use.",
        }
        return JSONResponse(
            exported,
            headers={"Content-Disposition": f'attachment; filename="scribebench-{job_id}.json"'},
        )

    @app.delete(
        "/api/jobs/{job_id}",
        status_code=204,
        dependencies=[Depends(require_api_key)],
    )
    async def delete_job(job_id: str) -> Response:
        if not database.delete_job(job_id):
            raise HTTPException(status_code=404, detail="job not found")
        return Response(status_code=204)

    return app


app = create_app()
