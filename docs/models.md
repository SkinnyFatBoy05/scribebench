# Local models, user-chosen APIs and deployment

## Default: local Ollama

Install Ollama, run `ollama pull qwen3:4b`, then start the API and frontend as described in README.
The native API defaults to `http://127.0.0.1:11434`. No hosted service or paid fallback is enabled.
The validated installation used Qwen3 4B Q4_K_M, Ollama 0.24.0, NVIDIA RTX 3060 laptop 6GB,
8192 context, temperature 0, thinking disabled, JSON mode with server-side Pydantic validation.
Schema-constrained Ollama mode failed with a vocabulary-loading error on this installation;
`json_object` is therefore the default. Other installations can opt into `json_schema`.
API reference: [Ollama structured outputs](https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx).

Local input is capped at 12000 UTF-8 bytes to keep source plus schema/output within the configured
context budget. This is conservative, not an exact tokenizer count. Output is capped at 2200 tokens.
Timeouts and malformed, truncated or incorrectly quoted results fail closed, never silently use the baseline.
Ambiguous-speaker inputs are forced to abstain by a deterministic safety policy after inference.
All notes still need human review: exact quotations do not establish that every summary claim is entailed.

## Attach your own model/API

For one connection, set `SCRIBE_MODEL_PROVIDER`, `SCRIBE_MODEL_BASE_URL`, `SCRIBE_MODEL_NAME`,
`SCRIBE_MODEL_API_KEY` (optional) and `SCRIBE_MODEL_OUTPUT_MODE` in the **API server environment**.
Supported protocols are native `ollama` and `openai-compatible` Chat Completions; not every arbitrary
vendor API is the same protocol. Use an OpenAI-compatible gateway for unsupported provider protocols,
or implement the small `DraftModel` interface in `api/app/model.py`. No vendor credential is required
for local inference. Provider terms, model licenses and API charges remain the operator's responsibility.

For several selectable connections:

1. Copy `models.example.json` to a private configuration file and keep only desired entries.
2. Set `SCRIBE_MODELS_FILE` to its absolute server path. Additional IDs must be unique, not `default`.
3. For hosted entries set the named environment variable (e.g. `MY_MODEL_API_KEY`) on the API server.
   Put the **variable name**, not the key value, in the JSON file. Missing credentials fail startup.
4. Restart the API. Choose the new connection in the browser's model selector. Existing jobs retain
   their model identity. Changing endpoint/model/prompt configuration fails incompatible pending jobs
   explicitly instead of rerouting them. Rotating an API secret does not change identity.

The operator owns this allowlist: browser users cannot make the server call arbitrary URLs.
Remote URLs require HTTPS and cannot embed credentials. Private-network endpoints other than the
documented local hostnames should also use HTTPS. `external` can conservatively mark a local gateway
as external when it forwards to a hosted provider. External submissions ask for confirmation in the UI.

OpenAI-compatible URLs accept either a service root or a base ending `/v1`; the adapter calls
`/v1/chat/completions`. Select `json_schema`, `json_object`, or `prompt` output mode according to the
provider. Prompt-only output is still parsed and validated; Markdown fences or malformed JSON fail.
Use a compatible gateway to normalize other route layouts or provider-specific token parameters.
Neither provider acceptance nor quality of arbitrary user-selected models can be guaranteed.

`GET /api/models/{id}/check` performs model discovery only, no generation/billable test. A provider that
does not support `/v1/models` may still accept inference; discovery reports unavailable in that case.
`/api/health` is process liveness. `/api/ready` requires default model discovery and does not promise
that inference will succeed. `/api/models` exposes no URL, key value or credential variable name.

## Single-workspace production hardening

- Set `SCRIBE_ENV=production` and a high-entropy `SCRIBE_API_KEY` of at least 32 characters.
  Placeholder/short keys fail startup. Generate a key with a password manager; do not commit it.
- Terminate HTTPS at your reverse proxy. Production cookies are Secure, HttpOnly, SameSite=Strict,
  expire after eight hours and are revoked on logout. Restarting the API signs out every session.
  This is one shared workspace with one operator key, not multi-tenant RBAC or enterprise SSO.
- Keep the API, SQLite and model server on private/loopback interfaces. Do not publish Ollama publicly.
  Local mode with no key is **unauthenticated** and only suitable for an isolated trusted workstation.
- Nginx/Vite no longer inject a service key for anonymous visitors. Authenticate in the UI or use
  `X-API-Key` for automation. Protect and rotate that header credential; it has full workspace access.
- Use one API process with bounded internal workers. SQLite queue recovery is not a distributed queue.
  Session/login limits are in-process; enforce an additional edge rate limit for internet exposure.
- Provider secrets belong in a secret manager/server environment. In Docker, explicitly mount the
  profiles file read-only and pass each referenced credential into the API container using a local
  Compose override. The sample does not inject arbitrary host secrets into containers.
- Back up the database using the supplied backup script; test restore and set a retention policy.
  SQLite is not encrypted by the app; use encrypted disks and strict host filesystem permissions.
- The supplied Compose deployment stays loopback-bound and does not provision TLS, DNS or hosted
  infrastructure. Docker and vLLM-container startup were not exercised in this Windows session.

## Reproduce validation

`cd api` then `.venv/Scripts/python -m scripts.qualify_local` (Windows) or
`.venv/bin/python -m scripts.qualify_local` (Unix). This is opt-in and refuses non-loopback/non-Ollama
providers. It runs the seven tiny synthetic development fixtures sequentially and writes
`api/artifacts/local-model-qualification.json` with actual tokens, elapsed times, model digest and GPU
residency. It is not an independent holdout study, production load test or clinical safety evaluation.
Exact keyword checks can fail on harmless paraphrases; read the stored notes, not just Boolean results.
API charge is zero for this local run; hardware and electricity costs are not measured.

Still required before real clinical use: substantially broader expert-reviewed evaluation, governance,
data/privacy review, access auditing, identity integration and operational qualification. LoRA training,
hosted inference, paid cost comparisons and public deployment have not been performed.
