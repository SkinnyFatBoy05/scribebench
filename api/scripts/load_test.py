from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
import uuid

import httpx

TRANSCRIPT = """Clinician: What brings you in?
Patient: I have had a dry cough for five days.
Clinician: Any fever?
Patient: No fever.
Clinician: Do you take medication?
Patient: No regular medication.
Clinician: Any medication allergies?
Patient: No known medication allergies."""


async def run(base_url: str, api_key: str, requests: int, concurrency: int) -> None:
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    failures = 0
    headers = {"X-API-Key": api_key} if api_key else {}

    async with httpx.AsyncClient(base_url=base_url, timeout=120) as client:

        async def submit(index: int) -> None:
            nonlocal failures
            async with semaphore:
                started = time.perf_counter()
                response = await client.post(
                    "/api/jobs",
                    headers={**headers, "Idempotency-Key": f"load-{uuid.uuid4()}-{index}"},
                    json={"transcript": TRANSCRIPT, "synthetic": True},
                )
                if response.status_code != 202:
                    failures += 1
                    return
                job_id = response.json()["id"]
                while True:
                    job = await client.get(f"/api/jobs/{job_id}", headers=headers)
                    status = job.json()["status"]
                    if status in {"draft_ready", "failed"}:
                        break
                    await asyncio.sleep(0.05)
                if status == "failed":
                    failures += 1
                else:
                    latencies.append((time.perf_counter() - started) * 1000)

        await asyncio.gather(*(submit(index) for index in range(requests)))

    latencies.sort()
    p95_index = max(0, round(len(latencies) * 0.95) - 1)
    print(
        json.dumps(
            {
                "requests": requests,
                "concurrency": concurrency,
                "successes": len(latencies),
                "failures": failures,
                "median_latency_ms": statistics.median(latencies) if latencies else None,
                "p95_latency_ms": latencies[p95_index] if latencies else None,
                "hardware": "RECORD_BEFORE_PUBLISHING",
                "cost_per_success": "RECORD_AFTER_MEASUREMENT",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--requests", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=2)
    arguments = parser.parse_args()
    asyncio.run(
        run(arguments.base_url, arguments.api_key, arguments.requests, arguments.concurrency)
    )
