"""External process watchdog. Emits actionable state changes; optional operator-owned webhook."""

import asyncio
import json
import os
from datetime import UTC, datetime

import httpx


class Monitor:
    def __init__(self, failures_to_alert=3):
        self.unavailable = 0
        self.failures_to_alert = failures_to_alert
        self.active: set[str] = set()

    def observe(self, ready: bool, stats: dict) -> list[dict]:
        self.unavailable = 0 if ready else self.unavailable + 1
        conditions = set()
        if self.unavailable >= self.failures_to_alert:
            conditions.add("model_or_api_unavailable")
        if stats.get("oldest_pending_seconds", 0) >= 300:
            conditions.add("stalled_jobs")
        if stats.get("failed_last_15_minutes", 0) >= 3:
            conditions.add("generation_failures")
        # Do not mark job alerts recovered while their source is unavailable.
        if not ready:
            conditions |= self.active - {"model_or_api_unavailable"}
        events = [
            {"event": "alert", "state": "firing", "condition": code}
            for code in sorted(conditions - self.active)
        ]
        events += [
            {"event": "alert", "state": "resolved", "condition": code}
            for code in sorted(self.active - conditions)
        ]
        self.active = conditions
        return events


async def run():
    base = os.getenv("SCRIBE_MONITOR_URL", "http://127.0.0.1:8000").rstrip("/")
    webhook = os.getenv("SCRIBE_ALERT_WEBHOOK", "")
    if webhook and not webhook.startswith("https://"):
        raise ValueError("alert webhook must use HTTPS")
    headers = {"X-API-Key": os.getenv("SCRIBE_API_KEY", "")}
    watcher = Monitor()
    pending = {}
    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        while True:
            try:
                ready = (await client.get(base + "/api/ready", headers=headers)).is_success
                response = await client.get(base + "/api/operations", headers=headers)
                response.raise_for_status()
                stats = response.json()
            except (httpx.HTTPError, ValueError):
                ready, stats = False, {}
            for event in watcher.observe(ready, stats):
                event["at"] = datetime.now(UTC).isoformat()
                print(json.dumps(event), flush=True)
                if webhook:
                    pending[event["condition"]] = event
            if webhook:
                for condition, event in list(pending.items()):
                    try:
                        delivered = await client.post(webhook, json=event)
                        delivered.raise_for_status()
                        del pending[condition]
                    except httpx.HTTPError:
                        print(
                            json.dumps(
                                {"event": "alert_delivery_failed", "condition": event["condition"]}
                            ),
                            flush=True,
                        )
            await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(run())
