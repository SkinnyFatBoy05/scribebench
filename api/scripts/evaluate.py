from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from app.model import RuleBasedModel, parse_transcript
from app.schemas import StructuredDraft
from app.service import load_cases, validate_grounding

ROOT = Path(__file__).resolve().parents[1]


async def evaluate() -> dict[str, object]:
    model = RuleBasedModel()
    cases = load_cases(ROOT / "data" / "synthetic_cases.json")
    held_out = [case for case in cases if case.split == "test"]
    rows: list[dict[str, object]] = []

    for case in held_out:
        result = await model.generate(case.transcript)
        valid = True
        grounded = True
        try:
            StructuredDraft.model_validate(result.draft.model_dump())
        except Exception:
            valid = False
        try:
            validate_grounding(case.transcript, result.draft)
        except ValueError:
            grounded = False

        expected = case.expected
        combined = " ".join(
            (
                result.draft.reason_for_visit.text,
                result.draft.history.text,
                result.draft.observations.text,
            )
        ).lower()
        reason_terms = [str(term).lower() for term in expected.get("reason_terms", [])]
        required_terms_present = all(term in combined for term in reason_terms)
        contradiction_expected = bool(expected.get("contradiction", False))
        contradiction_correct = bool(result.draft.contradictions) == contradiction_expected
        warning_term = str(expected.get("warning", "")).lower()
        warning_correct = not warning_term or any(
            warning_term in warning.lower() for warning in result.draft.warnings
        )
        forbidden = [str(term).lower() for term in expected.get("forbidden_terms", [])]
        forbidden_absent = all(
            term not in result.draft.reason_for_visit.text.lower() for term in forbidden
        )
        rows.append(
            {
                "case_id": case.id,
                "scenario_family": case.scenario_family,
                "structured_valid": valid,
                "evidence_grounded": grounded,
                "required_terms_present": required_terms_present,
                "contradiction_correct": contradiction_correct,
                "warning_correct": warning_correct,
                "forbidden_reason_terms_absent": forbidden_absent,
                "transcript_lines": len(parse_transcript(case.transcript)),
            }
        )

    def rate(key: str) -> float:
        return round(sum(bool(row[key]) for row in rows) / len(rows), 4)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "system": "rule-based-baseline-v1",
        "scope": "engineering evaluation on held-out synthetic scenario families",
        "held_out_cases": len(rows),
        "metrics": {
            "structured_validity_rate": rate("structured_valid"),
            "evidence_grounding_rate": rate("evidence_grounded"),
            "required_term_recall_rate": rate("required_terms_present"),
            "contradiction_accuracy": rate("contradiction_correct"),
            "warning_accuracy": rate("warning_correct"),
            "forbidden_reason_term_absence_rate": rate("forbidden_reason_terms_absent"),
        },
        "cases": rows,
        "comparisons": {"qwen_base": "not_run", "qwen_lora": "not_run", "hosted": "not_run"},
    }


if __name__ == "__main__":
    report = asyncio.run(evaluate())
    output = ROOT / "artifacts" / "baseline-evaluation.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], indent=2))
    print(f"Wrote {output}")
