from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, closing

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .auth import Auth, Login
from .config import Settings
from .connections import Connections
from .database import Database
from .metrics import Metrics
from .model import build_model
from .pilot import Feedback, Pilot
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
    pilot = Pilot(configured.pilot_manifest, configured.db_path)
    auth = Auth(configured, pilot.keys)
    connections = Connections(configured)
    database = Database(configured.db_path)
    metrics = Metrics()
    runner = JobRunner(configured, database, build_model(configured), metrics)
    runner.models = connections.models

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database.initialize()
        pilot.initialize()
        if pilot.manifest:
            allowed = {case.id: case.transcript for case in load_cases(configured.data_path)}
            with closing(sqlite3.connect(configured.db_path)) as db:
                for case_id, transcript in db.execute("SELECT case_id, transcript FROM jobs"):
                    if allowed.get(case_id) != transcript:
                        raise ValueError(
                            "pilot requires a dedicated database of unchanged library cases"
                        )
        await runner.start()
        app.state.ready = True
        if configured.seed_demo and not database.list_jobs(limit=1):
            demo = load_cases(configured.data_path)[0]
            job, created = create_job(
                database,
                transcript=demo.transcript,
                idempotency_key=f"seed-{demo.id}",
                case_id=demo.id,
                model_version=connections.versions["default"],
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

    async def require_api_key(request: Request):
        await auth.require(request)
        if auth.identity(request) in pilot.keys:
            pilot.require_active()

    async def require_operator(request: Request):
        await require_api_key(request)
        if auth.identity(request) not in {"operator", "local"}:
            raise HTTPException(403, "operator access required")

    @app.get("/api/pilot", dependencies=[Depends(require_api_key)])
    async def pilot_status(request: Request):
        return {
            **pilot.status(),
            "actor": auth.identity(request),
            "can_submit_feedback": pilot.active() and auth.identity(request) in pilot.keys,
        }

    @app.post("/api/pilot/feedback", status_code=201, dependencies=[Depends(require_api_key)])
    async def pilot_feedback(payload: Feedback, request: Request):
        pilot.require_active()
        if auth.identity(request) not in pilot.keys:
            raise HTTPException(403, "only authorised participants may submit pilot feedback")
        if not payload.synthetic_confirmed:
            raise HTTPException(422, "confirm feedback contains no real patient information")
        job = job_or_404(payload.job_id)
        if not job["draft"]:
            raise HTTPException(409, "review a completed draft before giving feedback")
        pilot.record(
            auth.identity(request),
            "feedback",
            payload.job_id,
            payload.model_dump(exclude={"job_id"}),
        )
        return {"saved": True}

    @app.get("/api/pilot/report", dependencies=[Depends(require_operator)])
    async def pilot_report():
        return JSONResponse(
            pilot.report(),
            headers={"Content-Disposition": 'attachment; filename="synthetic-pilot-report.json"'},
        )

    @app.get("/api/operations", dependencies=[Depends(require_operator)])
    async def operations():
        with closing(sqlite3.connect(configured.db_path)) as db:
            counts = dict(
                db.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status").fetchall()
            )
            oldest = db.execute(
                "SELECT MIN(updated_at) FROM jobs WHERE status IN ('queued','running','retrying')"
            ).fetchone()[0]
            failures = db.execute(
                "SELECT COUNT(*) FROM jobs WHERE status='failed' "
                "AND julianday(updated_at) >= julianday('now','-15 minutes')"
            ).fetchone()[0]
        from datetime import UTC, datetime

        age = (
            max(0, (datetime.now(UTC) - datetime.fromisoformat(oldest)).total_seconds())
            if oldest
            else 0
        )
        return {
            "job_counts": counts,
            "oldest_pending_seconds": round(age, 1),
            "failed_last_15_minutes": failures,
            "queue_depth": runner.queue.qsize(),
            "authentication_required": bool(configured.api_key),
            "secure_cookies": auth.secure,
            "pilot": pilot.status()["status"],
        }

    @app.get("/api/auth/session")
    async def session(request: Request):
        return {"authenticated": auth.authenticated(request), "required": bool(configured.api_key)}

    @app.post("/api/auth/login")
    async def login(payload: Login, request: Request, response: Response):
        auth.login(request, response, payload.key)
        return {"authenticated": True}

    @app.post("/api/auth/logout")
    async def logout(request: Request, response: Response):
        auth.logout(request, response)
        return {"authenticated": False}

    @app.get("/api/models", dependencies=[Depends(require_api_key)])
    async def models():
        return connections.public()

    @app.get("/api/models/{model_id}/check", dependencies=[Depends(require_api_key)])
    async def check_model(model_id: str):
        if model_id not in connections.profiles:
            raise HTTPException(404, "model connection not found")
        return await connections.check(model_id)

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:100]
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            metrics.record_request(request.method, request.url.path, 500)
            logger.error(
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
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
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
        discovery = await connections.check("default")
        if not discovery["available"]:
            raise HTTPException(503, "default model unavailable or not discoverable")
        return {"ready": True, "queue_depth": runner.queue.qsize(), "inference_tested": False}

    @app.get("/metrics", response_class=PlainTextResponse, dependencies=[Depends(require_api_key)])
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
        request: Request,
        idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ) -> dict[str, object]:
        if pilot.manifest:
            pilot.require_active()
            allowed = {case.id: case.transcript for case in load_cases(configured.data_path)}
            if allowed.get(payload.case_id) != payload.transcript:
                raise HTTPException(422, "pilot accepts unchanged synthetic library cases only")
            if (
                connections.profiles.get(payload.model_id)
                and connections.profiles[payload.model_id].external
            ):
                raise HTTPException(
                    422, "pilot inference must remain on an approved local connection"
                )
        if payload.model_id not in connections.versions:
            raise HTTPException(422, "unknown model connection")
        version = connections.versions[payload.model_id]
        profile = connections.profiles[payload.model_id]
        if profile.provider == "ollama" and len(payload.transcript.encode("utf-8")) > 12000:
            raise HTTPException(422, "local model accepts at most 12000 UTF-8 bytes per transcript")
        existing = database.get_by_key(idempotency_key)
        if existing:
            if (
                existing["transcript"] != payload.transcript
                or existing["case_id"] != payload.case_id
                or existing["model_version"] != version
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
            model_version=version,
        )
        if created:
            pilot.record(
                auth.identity(request), "job_submitted", str(job["id"]), {"model_version": version}
            )
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
    async def edit_draft(
        job_id: str, payload: EditDraftRequest, request: Request
    ) -> dict[str, object]:
        job = job_or_404(job_id)
        if job["status"] not in {JobStatus.DRAFT_READY.value, JobStatus.UNDER_REVIEW.value}:
            raise HTTPException(status_code=409, detail="job is not editable")
        try:
            validate_grounding(str(job["transcript"]), payload.draft)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        database.save_draft(job_id, payload.draft, status=JobStatus.UNDER_REVIEW)
        pilot.record(auth.identity(request), "draft_edited", job_id)
        return job_or_404(job_id)

    @app.post(
        "/api/jobs/{job_id}/approve",
        response_model=JobView,
        dependencies=[Depends(require_api_key)],
    )
    async def approve_job(job_id: str, request: Request) -> dict[str, object]:
        job = job_or_404(job_id)
        if job["status"] not in {JobStatus.DRAFT_READY.value, JobStatus.UNDER_REVIEW.value}:
            raise HTTPException(status_code=409, detail="job is not ready for approval")
        if not job["draft"] or job["draft"].get("abstained"):
            raise HTTPException(status_code=409, detail="abstained drafts cannot be approved")
        database.approve(job_id)
        pilot.record(auth.identity(request), "draft_approved", job_id)
        return job_or_404(job_id)

    @app.get(
        "/api/jobs/{job_id}/export",
        dependencies=[Depends(require_api_key)],
    )
    async def export_job(job_id: str, request: Request) -> JSONResponse:
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
        pilot.record(auth.identity(request), "draft_exported", job_id)
        return JSONResponse(
            exported,
            headers={"Content-Disposition": f'attachment; filename="scribebench-{job_id}.json"'},
        )

    @app.delete(
        "/api/jobs/{job_id}",
        status_code=204,
        dependencies=[Depends(require_operator)],
    )
    async def delete_job(job_id: str) -> Response:
        if not database.delete_job(job_id):
            raise HTTPException(status_code=404, detail="job not found")
        return Response(status_code=204)

    return app


app = create_app()
