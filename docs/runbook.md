# Operating runbook

## Health and signals

- Liveness: `GET /api/health`
- Readiness: `GET /api/ready`
- Metrics: `GET /metrics`
- Key alerts: queue depth at capacity, sustained job failures, readiness false, p95 above the tested objective, and model-version drift.

Logs are JSON and exclude transcript, draft, and evidence content. Correlate by `request_id` and `job_id`.

## Model unavailable

1. Confirm `/api/ready` and the model container health.
2. Stop accepting new jobs if the queue is near capacity.
3. Restart only the model service; durable jobs remain in SQLite.
4. After bounded retries are exhausted, jobs remain `failed` with a non-sensitive error code.
5. Set `SCRIBE_MODEL_VERSION` and `SCRIBE_MODEL_NAME` back to the last qualified pair, then restart the API to roll back.

## API restart

The runner re-queues `queued`, `running`, and `retrying` rows at startup. Submitters may safely repeat the same idempotency key. Verify the job reaches exactly one terminal/review state.

## Backup and restore

1. Quiesce writes or use SQLite's online backup API.
2. Copy the database, `-wal`, and `-shm` files together when not using the online API.
3. Restore into a new volume, run `PRAGMA integrity_check`, then start one API instance.
4. Verify job counts and one approved export before cutting over.

`scripts/backup.py` uses SQLite's online backup API; `scripts/restore_check.py` verifies integrity without changing the source.

## Deletion

`DELETE /api/jobs/{id}` permanently removes the synthetic transcript and its draft. Confirm the job ID and scope before calling it. Database backup retention may delay full erasure; document the configured retention period.

## Secrets and access

Inject `SCRIBE_API_KEY` into the API through the deployment secret store; never bake it into images or commit `.env`. Rotate by restarting the API with the new key (all browser sessions are revoked). The web proxy must NOT inject a service key. Set `SCRIBE_ENV=production` and use TLS at the ingress for secure cookies. Shared-workspace sign-in is implemented; per-user authentication and authorisation remain required before multi-user clinical use. See [deployment details](models.md).
