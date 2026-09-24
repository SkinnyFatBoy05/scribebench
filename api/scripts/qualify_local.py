"""Opt-in real local inference smoke/latency benchmark. Never calls hosted providers."""

import asyncio
import json
import platform
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.model import build_model
from app.service import load_cases, validate_grounding


async def qualify():
    settings = Settings.from_env()
    if settings.model_provider != "ollama" or urlsplit(settings.model_base_url).hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("qualification is restricted to loopback Ollama; no paid calls allowed")
    model = build_model(settings)
    rows = []
    for case in load_cases(settings.data_path):
        started = time.perf_counter()
        row = {"case_id": case.id, "split": case.split}
        try:
            result = await model.generate(case.transcript)
            validate_grounding(case.transcript, result.draft)
            draft = result.draft
            text = " ".join(
                [draft.reason_for_visit.text, draft.history.text, draft.observations.text]
            ).lower()
            row.update(
                {
                    "schema_and_quote_integrity": True,
                    "reason_terms_present": all(
                        str(term).lower() in text for term in case.expected.get("reason_terms", [])
                    ),
                    "contradiction_correct": bool(draft.contradictions)
                    == bool(case.expected.get("contradiction", False)),
                    "abstention_correct": draft.abstained
                    == bool(case.expected.get("abstained", False)),
                    "forbidden_note_terms_absent": all(
                        str(term).lower() not in text
                        for term in case.expected.get("forbidden_terms", [])
                    ),
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "draft": draft.model_dump(),
                }
            )
        except Exception as error:
            row.update({"schema_and_quote_integrity": False, "error_code": type(error).__name__})
        row["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        rows.append(row)
        print(case.id, row["schema_and_quote_integrity"], row["latency_ms"], flush=True)
    async with httpx.AsyncClient(trust_env=False) as client:
        running = (await client.get(settings.model_base_url + "/api/ps")).json()
        version = (await client.get(settings.model_base_url + "/api/version")).json()
    latencies = [r["latency_ms"] for r in rows]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "ollama",
        "model": settings.model_name,
        "output_mode": settings.model_output_mode,
        "runtime": version,
        "platform": platform.platform(),
        "resident_models": running,
        "scope": (
            "Seven synthetic development fixtures, sequential single-attempt real inference; "
            "not independent clinical validation or a load test. "
            "Prompt was tuned on development examples."
        ),
        "api_charge_usd": 0,
        "electricity_and_hardware_cost": "not measured",
        "median_latency_ms": statistics.median(latencies),
        "max_latency_ms": max(latencies),
        "cases": rows,
    }
    output = Path(__file__).resolve().parents[1] / "artifacts" / "local-model-qualification.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    asyncio.run(qualify())
