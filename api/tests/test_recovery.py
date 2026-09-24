import asyncio
from dataclasses import replace

from app.database import Database
from app.metrics import Metrics
from app.model import RuleBasedModel
from app.service import JobRunner, create_job
from scripts.backup import backup


def test_restart_drains_more_jobs_than_queue_capacity(client, tmp_path):
    settings = replace(client.app.state.settings, db_path=tmp_path / "recover.db", queue_capacity=1)
    database = Database(settings.db_path)
    database.initialize()
    ids = []
    for index in range(5):
        job, _ = create_job(
            database,
            transcript="Patient: I have a cough today.",
            idempotency_key=f"recovery-{index}",
            case_id=None,
            model_version=settings.model_version,
        )
        ids.append(job["id"])

    async def recover():
        runner = JobRunner(settings, database, RuleBasedModel(), Metrics())
        await runner.start()
        await asyncio.wait_for(runner.queue.join(), timeout=5)
        await runner.stop()

    asyncio.run(recover())
    assert all(database.get_job(job_id)["status"] == "draft_ready" for job_id in ids)
    destination = tmp_path / "backup.db"
    backup(settings.db_path, destination)
    assert len(Database(destination).list_jobs()) == 5


def test_retry_budget_is_bounded(client, tmp_path):
    settings = replace(client.app.state.settings, db_path=tmp_path / "fail.db")
    database = Database(settings.db_path)
    database.initialize()
    job, _ = create_job(
        database,
        transcript="Patient: I have a cough today.",
        idempotency_key="failure-case",
        case_id=None,
        model_version=settings.model_version,
    )

    class Unavailable:
        async def generate(self, transcript):
            raise TimeoutError("model offline")

    async def run():
        runner = JobRunner(settings, database, Unavailable(), Metrics())
        await runner.start()
        await asyncio.wait_for(runner.queue.join(), timeout=5)
        await runner.stop()

    asyncio.run(run())
    recovered = database.get_job(job["id"])
    assert recovered["status"] == "failed"
    assert recovered["attempts"] == settings.max_retries + 1
