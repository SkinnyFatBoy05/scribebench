from __future__ import annotations

import time

from fastapi.testclient import TestClient

TRANSCRIPT = """Clinician: What brings you in?
Patient: I have had a cough for one week.
Clinician: Any fever?
Patient: No fever.
Clinician: Are you sure?
Patient: Actually, I had a fever yesterday.
Clinician: What medications do you take?
Patient: No regular medication.
Clinician: Any medication allergies?
Patient: No known medication allergies."""


def wait_for_draft(client: TestClient, job_id: str) -> dict[str, object]:
    for _ in range(100):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"draft_ready", "failed"}:
            return job
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_requires_synthetic_confirmation(client: TestClient) -> None:
    response = client.post(
        "/api/jobs",
        headers={"Idempotency-Key": "not-synthetic"},
        json={"transcript": TRANSCRIPT, "synthetic": False},
    )
    assert response.status_code == 422


def test_idempotent_review_approval_and_export(client: TestClient) -> None:
    headers = {"Idempotency-Key": "same-request-key"}
    payload = {"transcript": TRANSCRIPT, "synthetic": True, "case_id": "test-case"}
    first = client.post("/api/jobs", headers=headers, json=payload)
    second = client.post("/api/jobs", headers=headers, json=payload)
    assert first.status_code == 202
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]

    job = wait_for_draft(client, first.json()["id"])
    assert job["status"] == "draft_ready"
    assert job["draft"]["contradictions"][0]["lines"] == [4, 6]
    assert client.get(f"/api/jobs/{job['id']}/export").status_code == 409

    edited = job["draft"]
    edited["reason_for_visit"]["text"] = "Cough for one week."
    saved = client.patch(f"/api/jobs/{job['id']}/draft", json={"draft": edited})
    assert saved.status_code == 200
    assert saved.json()["status"] == "under_review"

    approved = client.post(f"/api/jobs/{job['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    exported = client.get(f"/api/jobs/{job['id']}/export")
    assert exported.status_code == 200
    assert exported.json()["disclaimer"].startswith("Synthetic portfolio")
    assert "attachment" in exported.headers["content-disposition"]


def test_rejects_ungrounded_edit(client: TestClient) -> None:
    created = client.post(
        "/api/jobs",
        headers={"Idempotency-Key": "ungrounded-edit"},
        json={"transcript": TRANSCRIPT, "synthetic": True},
    ).json()
    job = wait_for_draft(client, created["id"])
    job["draft"]["reason_for_visit"]["evidence"][0]["quote"] = "Invented quote"
    response = client.patch(f"/api/jobs/{job['id']}/draft", json={"draft": job["draft"]})
    assert response.status_code == 422


def test_delete_and_metrics_do_not_echo_content(client: TestClient) -> None:
    created = client.post(
        "/api/jobs",
        headers={"Idempotency-Key": "delete-example"},
        json={"transcript": TRANSCRIPT, "synthetic": True},
    ).json()
    metrics = client.get("/metrics").text
    assert "cough for one week" not in metrics
    assert client.delete(f"/api/jobs/{created['id']}").status_code == 204
    assert client.get(f"/api/jobs/{created['id']}").status_code == 404
