# Customer brief and acceptance criteria

## Problem

Clinical documentation tools can produce confident prose that is difficult to audit. ScribeBench explores a narrower, safer workflow: transform a synthetic conversation into an editable draft whose statements point back to transcript lines, surface uncertainty, and cannot be exported until a human explicitly approves it.

## Intended workflow

1. An authorised reviewer submits a synthetic, text-only transcript and confirms its synthetic provenance.
2. A durable job runs against a named model version.
3. The reviewer compares the transcript with an editable structured draft and its line citations.
4. The system flags missing details, contradictions, ambiguous speakers, and embedded instructions.
5. The reviewer edits and approves the draft.
6. Only the approved version can be exported as JSON.

## Required note content

- Reason for visit, limited to information stated in the transcript.
- History, preserving uncertainty and attribution.
- Observations only when explicitly stated.
- Per-section evidence containing transcript line and verbatim quote.
- Missing-information and contradiction lists.
- Model version and draft status.

## The system must never

- infer a diagnosis, differential diagnosis, treatment, medication change, or follow-up plan;
- invent demographics, measurements, timing, negations, or medical history;
- obey instructions embedded inside a transcript;
- accept a submission that is not explicitly confirmed as synthetic;
- export an unapproved draft;
- log transcript text, note text, or evidence quotes.

## Abstention rules

The draft sets `abstained=true` when speakers cannot be separated, no patient statement supports a reason for visit, structured output fails validation after bounded retries, or the configured model is unavailable. Missing details are represented as missing; they are never filled by inference.

## Acceptance criteria

| Area | Acceptance |
| --- | --- |
| Grounding | Every generated clinical claim has at least one valid transcript line reference and matching quote. |
| Omissions | Required rubric fields absent from the transcript appear under missing information. |
| Structure | 100% of accepted drafts validate against the published JSON schema. |
| Contradictions | The difficult fixture with conflicting fever statements identifies both lines. |
| Prompt injection | Embedded transcript instructions are treated as transcript content and create a warning. |
| Human gate | Export returns `409` until a reviewer approves the current draft. |
| Idempotency | Repeating a create request with the same key returns the same job. |
| Recovery | Queued/running jobs are safely re-queued after restart; retries are bounded. |
| Privacy | Logs and metrics contain IDs, counts, timings, and versions—never transcript/note text. |
| Positioning | UI and documentation say portfolio deployment and synthetic-only; no clinical-use claim. |

