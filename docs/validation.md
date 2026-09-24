# Local validation — 2026-09-24

Environment: Windows, Python 3.11, Node.js 24.11.1.

## Build-only pilot/operations and visual refinement

No pilot was activated and no deployment/invitations were performed, per the user's build-only scope.
The existing design was refined with readable typography, larger controls, panel spacing and mobile
navigation, plus a Pilot & operations view backed by real status. Desktop (1440×1000) and mobile
(390×844) inspection found no horizontal document overflow. The inactive pilot shows no participants
or feedback and does not expose a feedback form to unauthorised users.

29 API tests cover the earlier functionality plus pilot admission/expiry/identity, operator-only
reporting/deletion, synthetic-library input restrictions, unsafe database admission, immutable
backup/restore, monitor fault/recovery transitions and deployment-configuration rejection.
Four frontend tests, frontend lint and the production build pass. Compose configuration parsing
passes with non-deployable test values; the Docker engine is not running, so containers/TLS are untested.

`api/artifacts/operational-drill.json` records an isolated backup, fresh-path restore and an actual
previous-release subprocess reading the same approved export. Source/snapshot hashes remain unchanged.
This drill discovered and fixed SQLite connection leaks. It does not claim a deployed image rollback,
an achieved production RTO, actual alert delivery, participant usage or human feedback.
See [operating and pilot gates](pilot-operations.md) for the explicit remaining acceptance work.

## Local-LLM hardening update

The default is now real Ollama Qwen3 4B Q4_K_M, not the rule baseline. The qualification artifact records
seven real sequential inference calls, actual token counts and GPU residency of approximately 4.18GB
on the RTX 3060 laptop 6GB. Median latency was 5.30 seconds and maximum 7.07 seconds in the recorded run.
All seven passed schema/quote-integrity checks after the explicit ambiguous-speaker abstention policy.
This does not establish semantic accuracy: the exact keyword check misses a dizziness paraphrase,
and manual inspection found that summaries can overstate absent examinations or omit a correction
from the history even when a separate contradiction flag is present. Human review remains mandatory.

Adapter tests exercise native Ollama and three OpenAI-compatible output modes with mocked HTTP;
only Ollama has also been exercised against a real model. Authentication tests cover cookies,
revocation, cross-origin writes, login rate limits and protected exports/metrics. Model selection,
configuration fingerprints, server-only secrets, bounded telemetry and truncated output are covered.
Browser checks exercise sign-in, local-model discovery, actual generation, review and approval.
The authenticated JSON download and logout were verified in the browser. A sidebar overlap hiding
the logout button was found and repaired. Review warnings are editable so reviewers can correct
unsupported model wording before approval. Desktop layout and mobile overflow were checked.

Final automated coverage: 21 API tests and frontend helper/transport tests, plus Ruff, frontend lint
and the TypeScript/Vite production build. CI repeats the offline tests; real inference is opt-in.

The current evidence is in `api/artifacts/local-model-qualification.json`. Local API charges are zero;
hardware/electricity were not measured. Hosted inference, LoRA training, public deployment and
container qualification are not claimed. HTTPS production cookies are tested in the test client,
not behind a deployed TLS ingress.

## Original baseline verification (historical)

The following checks were recorded before the local-LLM update, using the deterministic baseline:

- Eight API tests pass: synthetic confirmation, idempotent submission, edit/save, approval/export gate, quote validation, deletion, ambiguous-speaker abstention, instruction warning, bounded failure retries, queue recovery and backup integrity (some cases cover multiple behaviors).
- Two frontend helper tests pass; TypeScript/Vite production build and frontend lint pass.
- Python Ruff passes.
- Browser verification: a fresh library case generated a draft; editing the reason and saving changed its state to under review; approval enabled JSON export; the API returned the approved export.
- Desktop inspection at 1440×1000 and mobile inspection at 390×844 completed. Mobile document width matched the viewport with no horizontal overflow.
- The browser workflow confirmed the corrected missing-objective-observations warning, instead of incorrectly treating a medication as an observation.

## Limits

The evaluator's three held-out cases are smoke fixtures, not a meaningful clinical dataset. Quote integrity does not prove semantic support. The rule baseline uses deliberately simple extraction and contradiction heuristics. The API assumes a single server process; horizontal scaling requires a shared queue and transactional claims. The seven local-model cases are development smoke checks, not an independent holdout after prompt tuning.

Docker ports bind to loopback. The proxy no longer injects a service key. Enable the workspace key,
production mode and HTTPS before network exposure; add per-user identity for multi-user access.

## Visual reference

The built-in Image Gen tool generated `docs/design/app-concept.png` using a UI-mockup prompt for a full ScribeBench review workspace: transcript left, editable structured note right, teal/off-white palette, line citations, missing-information and contradiction warnings, approval and export controls. The code omits the concept's audio control because the brief requires text-only input.
