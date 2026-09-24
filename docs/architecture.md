# Architecture

```mermaid
flowchart LR
  U[Reviewer] --> W[React review UI]
  W -->|API key + idempotency key| A[FastAPI]
  A --> D[(SQLite WAL)]
  A --> Q[Bounded durable job runner]
  Q --> R[Rule baseline]
  Q -. OpenAI-compatible JSON .-> V[vLLM + selected open model]
  A --> M[Prometheus metrics]
  W -->|approved only| E[JSON export]
```

## Trust boundaries

- The browser holds synthetic content while a case is open. Browser storage is not used.
- The API stores synthetic transcripts and drafts in SQLite; database access is restricted to the service account.
- Logs intentionally receive request IDs, job IDs, status, counts, timings, and model versions only.
- Model requests stay inside the deployment network when vLLM is used.
- A single shared API key is suitable only for a portfolio deployment. Real multi-user use requires an identity provider, per-user authorisation, audit retention policy, and a privacy/security review.

## Job states

```mermaid
stateDiagram-v2
  [*] --> queued
  queued --> running
  running --> draft_ready
  running --> retrying: transient error
  retrying --> running
  running --> failed: retry budget exhausted
  draft_ready --> under_review: human edit
  under_review --> approved: explicit approval
  draft_ready --> approved: explicit approval
  approved --> exported
```

The database is authoritative. At startup, `queued`, `running`, and `retrying` jobs are re-queued. A unique idempotency key prevents duplicate submissions.

