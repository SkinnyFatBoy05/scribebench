import json
import sqlite3
import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from scripts.backup import backup
from scripts.monitor import Monitor
from scripts.restore import restore


def pilot_settings(client, tmp_path, monkeypatch, expired=False):
    now = datetime.now(UTC)
    manifest = {
        "pilot_id": "isolated-test-pilot",
        "owner": "test-owner",
        "authorised_by": "test-fixture-not-a-real-authorisation",
        "authorised_at": (now - timedelta(days=2)).isoformat(),
        "expires_at": (now + timedelta(days=-1 if expired else 1)).isoformat(),
        "synthetic_only": True,
        "participants": [{"id": "tester-one", "key_env": "SCRIBE_TEST_PARTICIPANT"}],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    monkeypatch.setenv("SCRIBE_TEST_PARTICIPANT", "p" * 40)
    return replace(
        client.app.state.settings,
        db_path=tmp_path / "pilot.db",
        environment="production",
        api_key="o" * 40,
        pilot_manifest=str(path),
    )


def test_pilot_is_closed_by_default(client):
    status = client.get("/api/pilot").json()
    assert status["status"] == "awaiting_authorisation"
    assert status["counts"] == {} and not status["can_submit_feedback"]
    assert (
        client.post(
            "/api/pilot/feedback",
            json={
                "job_id": "missing",
                "usability": 5,
                "accuracy": 5,
                "issue": "none",
                "synthetic_confirmed": True,
            },
        ).status_code
        == 403
    )


def test_pilot_restricts_input_identity_and_records_real_actions(client, tmp_path, monkeypatch):
    settings = pilot_settings(client, tmp_path, monkeypatch)
    with TestClient(create_app(settings), base_url="https://testserver") as browser:
        assert browser.get("/api/jobs").status_code == 401
        assert browser.post("/api/auth/login", json={"key": "p" * 40}).status_code == 200
        assert browser.get("/api/pilot").json()["actor"] == "tester-one"
        assert browser.get("/api/operations").status_code == 403
        assert browser.get("/api/pilot/report").status_code == 403
        custom = {"synthetic": True, "transcript": "Patient: A user-typed transcript."}
        assert (
            browser.post(
                "/api/jobs", json=custom, headers={"Idempotency-Key": "custom-input"}
            ).status_code
            == 422
        )
        case = browser.get("/api/cases").json()[0]
        payload = {"synthetic": True, "transcript": case["transcript"], "case_id": case["id"]}
        created = browser.post(
            "/api/jobs", json=payload, headers={"Idempotency-Key": "pilot-library"}
        )
        assert created.status_code == 202
        job_id = created.json()["id"]
        for _ in range(100):
            job = browser.get(f"/api/jobs/{job_id}").json()
            if job["draft"]:
                break
            time.sleep(0.01)
        assert job["draft"]
        assert browser.post(f"/api/jobs/{job_id}/approve").status_code == 200
        assert browser.get(f"/api/jobs/{job_id}/export").status_code == 200
        feedback = {
            "job_id": job_id,
            "usability": 3,
            "accuracy": 4,
            "issue": "workflow",
            "comment": "Isolated automated test feedback, not participant evidence.",
            "synthetic_confirmed": False,
        }
        assert browser.post("/api/pilot/feedback", json=feedback).status_code == 422
        feedback["synthetic_confirmed"] = True
        assert browser.post("/api/pilot/feedback", json=feedback).status_code == 201
        assert browser.delete(f"/api/jobs/{job_id}").status_code == 403
        report = browser.get("/api/pilot/report", headers={"X-API-Key": "o" * 40}).json()
        assert report["pilot"]["counts"]["feedback"] == 1
        assert all(row["actor"] == "tester-one" for row in report["events"])
        assert "cough" not in json.dumps(report)
        assert "pppppp" not in json.dumps(report)


def test_pilot_expiration_revokes_participant_access(client, tmp_path, monkeypatch):
    with TestClient(
        create_app(pilot_settings(client, tmp_path, monkeypatch, expired=True)),
        base_url="https://testserver",
    ) as browser:
        assert browser.get("/api/jobs", headers={"X-API-Key": "p" * 40}).status_code == 403
        assert (
            browser.get("/api/pilot", headers={"X-API-Key": "o" * 40}).json()["status"] == "expired"
        )


def test_pilot_refuses_insecure_deployment(client, tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="production mode"):
        create_app(replace(pilot_settings(client, tmp_path, monkeypatch), environment="local"))


def test_backup_restore_is_safe_and_preserves_records(client, tmp_path):
    source = client.app.state.settings.db_path
    snapshot = tmp_path / "snapshot.db"
    destination = tmp_path / "restored.db"
    backup(source, snapshot)
    restore(snapshot, destination)
    with sqlite3.connect(destination) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
    with pytest.raises(FileExistsError):
        restore(snapshot, destination)
    with pytest.raises(FileExistsError):
        backup(source, snapshot)
    with pytest.raises(FileNotFoundError):
        backup(tmp_path / "missing.db", tmp_path / "new.db")
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a sqlite backup")
    with pytest.raises(sqlite3.DatabaseError):
        restore(corrupt, tmp_path / "bad-restore.db")


def test_monitor_alerts_and_resolves_without_repetition():
    watcher = Monitor()
    assert watcher.observe(False, {}) == []
    assert watcher.observe(False, {}) == []
    assert watcher.observe(False, {}) == [
        {"event": "alert", "state": "firing", "condition": "model_or_api_unavailable"}
    ]
    assert watcher.observe(False, {}) == []
    assert watcher.observe(True, {})[0]["state"] == "resolved"
    events = watcher.observe(True, {"oldest_pending_seconds": 301, "failed_last_15_minutes": 3})
    assert {event["condition"] for event in events} == {"stalled_jobs", "generation_failures"}
    assert watcher.observe(False, {}) == []
    assert all(event["state"] == "resolved" for event in watcher.observe(True, {}))


def test_deployment_gate_rejects_unpinned_or_http_configuration():
    from scripts.deployment_check import validate

    assert len(validate({})) == 5
    configured = {
        "SCRIBE_API_IMAGE": "registry/api@sha256:" + "a" * 64,
        "SCRIBE_WEB_IMAGE": "registry/web@sha256:" + "b" * 64,
        "SCRIBE_CADDY_IMAGE": "registry/caddy@sha256:" + "c" * 64,
        "SCRIBE_DOMAIN": "pilot.example.invalid",
        "SCRIBE_API_KEY": "x" * 40,
    }
    assert validate(configured) == []
    configured["SCRIBE_DOMAIN"] = "http://pilot.example.invalid"
    assert any("hostname" in issue for issue in validate(configured))


def test_pilot_refuses_a_non_library_development_database(client, tmp_path, monkeypatch):
    settings = pilot_settings(client, tmp_path, monkeypatch)
    from app.database import Database
    from app.service import create_job

    database = Database(settings.db_path)
    database.initialize()
    create_job(
        database,
        transcript="Patient: arbitrary synthetic text.",
        idempotency_key="old-dev-job",
        case_id=None,
        model_version="older-version",
    )
    with pytest.raises(ValueError, match="dedicated database"):
        with TestClient(create_app(settings)):
            pass
