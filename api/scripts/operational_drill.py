"""Isolated recovery + actual previous-release compatibility drill. Never touches the live DB."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from scripts.backup import backup
from scripts.monitor import Monitor
from scripts.restore import restore

PREVIOUS_RELEASE = "7191186c69c2ead95686784fd7eb6f9276e95f60"


def drill(previous: str):
    root = Path(__file__).resolve().parents[2]
    revision = subprocess.check_output(
        ["git", "rev-parse", "--verify", previous + "^{commit}"], cwd=root, text=True
    ).strip()
    with tempfile.TemporaryDirectory(prefix="scribebench-drill-") as scratch:
        directory = Path(scratch)
        settings = replace(
            Settings.from_env(),
            db_path=directory / "source.db",
            api_key="drill-" + "x" * 40,
            environment="production",
            model_provider="rule-based",
            model_name="test-baseline",
            model_base_url="http://localhost",
            models_file="",
            pilot_manifest="",
            seed_demo=False,
        )
        with TestClient(create_app(settings), base_url="https://testserver") as client:
            client.headers["X-API-Key"] = settings.api_key
            job = client.post(
                "/api/jobs",
                json={"transcript": "Patient: I have had a cough for two days.", "synthetic": True},
                headers={"Idempotency-Key": "operational-drill"},
            ).json()
            for _ in range(100):
                current = client.get(f"/api/jobs/{job['id']}").json()
                if current["draft"]:
                    break
                time.sleep(0.01)
            assert current["draft"], "drill fixture did not finish"
            assert client.post(f"/api/jobs/{job['id']}/approve").status_code == 200
            expected = client.get(f"/api/jobs/{job['id']}/export").json()
            snapshot = directory / "snapshot.db"
            backup(settings.db_path, snapshot)
        snapshot_hash = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        source_hash = hashlib.sha256(settings.db_path.read_bytes()).hexdigest()
        started = time.perf_counter()
        recovered = directory / "recovered.db"
        restore(snapshot, recovered)
        with TestClient(
            create_app(replace(settings, db_path=recovered)), base_url="https://testserver"
        ) as client:
            response = client.get(
                f"/api/jobs/{job['id']}/export", headers={"X-API-Key": settings.api_key}
            )
            assert response.status_code == 200 and response.json() == expected
        recovery_seconds = time.perf_counter() - started
        archive = directory / "previous.zip"
        subprocess.run(
            ["git", "archive", "--format=zip", "--output", str(archive), revision, "api"],
            cwd=root,
            check=True,
        )
        previous_dir = directory / "previous"
        with zipfile.ZipFile(archive) as source:
            source.extractall(previous_dir)
        rollback_db = directory / "rollback.db"
        restore(snapshot, rollback_db)
        environment = {k: v for k, v in os.environ.items() if not k.startswith("SCRIBE_")}
        environment.update(
            {
                "SCRIBE_DB_PATH": str(rollback_db),
                "SCRIBE_MODEL_PROVIDER": "rule-based",
                "SCRIBE_MODEL_BASE_URL": "http://localhost",
                "SCRIBE_SEED_DEMO": "false",
                "SCRIBE_API_KEY": settings.api_key,
                "SCRIBE_ENV": "production",
                "DRILL_JOB_ID": job["id"],
            }
        )
        code = """import json, os
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app, base_url='https://testserver') as client:
    assert client.get('/api/jobs').status_code == 401
    response = client.get('/api/jobs/' + os.environ['DRILL_JOB_ID'] + '/export',
        headers={'X-API-Key':os.environ['SCRIBE_API_KEY']})
    assert response.status_code == 200
    print(json.dumps(response.json()))
"""
        started = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=previous_dir / "api",
            env=environment,
            text=True,
            capture_output=True,
            timeout=30,
            check=True,
        )
        assert json.loads(result.stdout) == expected, (
            "previous release could not read restored export"
        )
        rollback_seconds = time.perf_counter() - started
        assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == snapshot_hash
        assert hashlib.sha256(settings.db_path.read_bytes()).hexdigest() == source_hash
        watcher = Monitor()
        events = []
        for ready in [True, False, False, False, False, True]:
            events.extend(watcher.observe(ready, {}))
        assert [event["state"] for event in events] == ["firing", "resolved"]
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "scope": (
                "isolated synthetic engineering drill, "
                "not a participant pilot or deployed infrastructure test"
            ),
            "previous_release": revision,
            "backup_sha256": snapshot_hash,
            "source_unchanged": True,
            "approved_export_equal_after_restore": True,
            "approved_export_equal_under_previous_release": True,
            "recovery_seconds": round(recovery_seconds, 3),
            "previous_release_start_and_export_seconds": round(rollback_seconds, 3),
            "monitor_fault_sequence": events,
            "limitations": [
                "tiny one-job SQLite fixture",
                "shared Python environment, not image rollback",
                "no DNS/TLS/host outage",
                "no external alert receiver",
                "no real pilot participants",
            ],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous", default=PREVIOUS_RELEASE)
    args = parser.parse_args()
    report = drill(args.previous)
    output = Path(__file__).resolve().parents[1] / "artifacts" / "operational-drill.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
