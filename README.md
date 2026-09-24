# ScribeBench

ScribeBench is a self-hosted portfolio deployment that turns **synthetic** clinician–patient transcripts into structured draft notes with line-level evidence, missing-information flags, editable review, explicit human approval, and JSON export.

It is an engineering demonstration—not a medical device, clinical validation, or record system. It must not receive real patient data and it does not diagnose or recommend treatment.

![ScribeBench design reference](docs/design/app-concept.png)

The image is a generated design reference. The implementation is code-native and its verified behavior is recorded in [validation evidence](docs/validation.md).

## What works now

- Durable, idempotent FastAPI jobs stored in SQLite/WAL.
- Bounded queue, timeouts, retries, restart recovery, model versioning, and rollback-by-configuration.
- A deterministic baseline that is runnable without a GPU and an OpenAI-compatible adapter for a self-hosted vLLM server.
- Structured validation, evidence references, contradictions, missing-information flags, and instruction-in-transcript handling.
- React review interface with edits, approval gate, deletion, job states, and approved-only JSON export.
- Request IDs, Prometheus-format metrics, latency/token counters, and transcript-free application logs.
- Synthetic scenario-family splits, a repeatable baseline evaluator, LoRA training scaffold, recovery tests, and operating docs.

The LoRA job and GPU benchmark are intentionally supplied but **not claimed as run**. They require approved GPU spend and recorded hardware details.

## Run locally

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node.js 22.12+ (validated with Node.js 24).

```bash
cd api
uv sync --group dev
uv run fastapi dev main.py
```

In another terminal:

```bash
cd web
npm install
npm run dev
```

Open `http://localhost:5173`. The local API is open only when `SCRIBE_API_KEY` is unset; set it outside loopback environments.

Docker baseline:

```bash
docker compose up --build
```

Open `http://localhost:4173`.

GPU-backed model serving (after reviewing image/model versions and accepting the model download):

```bash
SCRIBE_MODEL_PROVIDER=openai-compatible docker compose --profile gpu up --build
```

## Verify

```bash
make test
make check
make eval
```

See [customer brief](docs/customer-brief.md), [architecture](docs/architecture.md), [model selection](docs/model-selection.md), [evaluation plan](docs/evaluation.md), and [runbook](docs/runbook.md).
