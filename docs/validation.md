# Local validation — 2026-09-24

Environment: Windows, Python 3.11, Node.js 24.11.1. Provider: deterministic rule-based baseline. No GPU, hosted inference, or paid deployment was used.

- Eight API tests pass: synthetic confirmation, idempotent submission, edit/save, approval/export gate, quote validation, deletion, ambiguous-speaker abstention, instruction warning, bounded failure retries, queue recovery and backup integrity (some cases cover multiple behaviors).
- Two frontend helper tests pass; TypeScript/Vite production build and frontend lint pass.
- Python Ruff passes.
- Browser verification: a fresh library case generated a draft; editing the reason and saving changed its state to under review; approval enabled JSON export; the API returned the approved export.
- Desktop inspection at 1440×1000 and mobile inspection at 390×844 completed. Mobile document width matched the viewport with no horizontal overflow.
- The browser workflow confirmed the corrected missing-objective-observations warning, instead of incorrectly treating a medication as an observation.

## Limits

The evaluator's three held-out cases are smoke fixtures, not a meaningful clinical dataset. Quote integrity does not prove semantic support. The rule baseline uses deliberately simple extraction and contradiction heuristics. Model adapter integration, GPU serving, LoRA training, hosted comparisons, container runtime, production authentication, operational cost, and clinical quality have not been qualified. The API currently assumes a single server process; horizontal scaling requires a shared queue and transactional claims.

Docker ports bind to loopback. The proxy injects a service key, so it does not authenticate individual browser users. Put an authenticated ingress in front of any remotely accessible deployment.

## Visual reference

The built-in Image Gen tool generated `docs/design/app-concept.png` using a UI-mockup prompt for a full ScribeBench review workspace: transcript left, editable structured note right, teal/off-white palette, line citations, missing-information and contradiction warnings, approval and export controls. The code omits the concept's audio control because the brief requires text-only input.
