# Evaluation plan

This is an engineering evaluation on synthetic data, not clinical validation.

The included report is a three-case smoke baseline. `evidence_grounding_rate` checks that cited quotes match source lines; it does not test whether all generated claims are entailed by those quotes. Required-term recall is a lexical proxy, not a complete omission measure. The report's perfect scores must not be represented as factual accuracy or a clinically validated result. Manual audits and larger model comparisons remain pending.

## Leakage control

Scenarios are assigned to `train`, `validation`, or `test` by `scenario_family` before any wording variations are produced. The held-out test families remain unchanged during prompt or LoRA iteration.

## Rubric

- **Unsupported claim rate:** draft claims without a valid evidence line and matching quote / total claims.
- **Important omission rate:** expected rubric facts absent from the draft / expected facts.
- **Structured validity:** outputs passing the `StructuredDraft` schema / attempts.
- **Contradiction handling:** fixtures where both conflicting lines are identified / contradiction fixtures.
- **Refusal behaviour:** adversarial fixtures abstained or warned correctly / adversarial fixtures.
- **Human edit burden:** reviewer-scored material edits on a 0–3 scale, recorded manually for a frozen sample.

`uv run python -m scripts.evaluate` writes a machine-readable report for the deterministic baseline. Hosted and LoRA columns remain `not_run` until the corresponding endpoints/checkpoints and budget are available. A reviewer must manually audit a recorded sample; an LLM judge may assist but cannot replace that audit.

## Benchmark protocol

Run `scripts/load_test.py` against the same hardware with stated input-length buckets and concurrency 1, 2, 4, and 8. Report median/p95 latency, successful transcripts per minute, error rate, GPU memory, input/output tokens, and amortised infrastructure cost per successful job including idle time. Do not compare on-demand API price with fully utilised self-hosted cost.
