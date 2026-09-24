# Build now, authorise the pilot later

Status: **prepared, not deployed or authorised**. The user requested build-only work on 2026-09-24
and will invite participants later. No invitations, purchases, public endpoints or real patient
information are part of this build. No automated test feedback counts as human pilot evidence.

## Deployment gate

`deploy/compose.secure.yaml` is a separate deployment definition, not an override of the local
Compose file. Only the ingress publishes ports. API, database and monitor remain on the container
network. It uses production authentication, Secure/HttpOnly cookies, no-new-privileges on application
services and bounded API/monitor logs. The API image now includes the operations scripts.

Before running it, the operator must approve the host, domain, image registry, alert recipient,
network exposure and budget. Build API/web images from the reviewed commit, scan them and record
immutable image digests for API, web and Caddy. Keep the model on the trusted host; do not publish
Ollama. Confirm Docker can reach it without opening it to other machines.

Set `SCRIBE_API_IMAGE`, `SCRIBE_WEB_IMAGE`, `SCRIBE_CADDY_IMAGE`, `SCRIBE_DOMAIN`, and a unique random
`SCRIBE_API_KEY` using the deployment secret manager. Run from `api`:

```text
python -m scripts.deployment_check
```

Then validate `docker compose -f deploy/compose.secure.yaml config --quiet` from the repository root.
The template requires a DNS hostname and uses Caddy's automatic HTTPS with a persistent certificate
volume. See [Caddy site addresses](https://caddyserver.com/docs/caddyfile/concepts#addresses) and
[reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy). Only after authorisation
run the deployment. `deployment_check` checks syntax, not registry existence, image safety or TLS.

Actual acceptance evidence must include trusted TLS without warnings, HTTP-to-HTTPS redirect,
unauthenticated API rejection, sign-in/logout, Secure cookie attributes, external port scan showing
no API/model/database ports, a successful synthetic case and an acknowledged monitoring alert.
The installed Docker engine was unavailable during this build; no container-runtime or TLS claim
is made. Production admission remains closed until the operator supplies this evidence.

## Recovery and rollback

Set a pilot objective before invitations: proposed RPO 24 hours (daily snapshots) and RTO 30 minutes.
These are **proposed targets, not achieved service guarantees**. Retain seven daily encrypted snapshots
and one pre-release snapshot outside the app volume; agree the actual retention/ownership first.

The backup command uses SQLite's online backup API, reads the source without creating a missing DB,
checks integrity and refuses to overwrite snapshots. Restore checks the jobs table and integrity,
requires a fresh destination with no SQLite sidecars, and never changes the live configuration.

```text
python -m scripts.backup /data/scribebench.db /backups/unique-release-and-date.db
python -m scripts.restore /backups/unique-release-and-date.db /recovery/restored-unique.db
python -m scripts.operational_drill
```

The drill creates only isolated synthetic temporary data. It backs up an approved draft, restores
to a new path, verifies identical export under the candidate code, then launches the actual previous
release (`7191186`) in a separate Python process against another restored copy and verifies the same
export and unauthenticated denial. It hashes the source and snapshot to verify neither changed.
This caught and fixed connection leaks that left Windows DB files locked. CI runs the drill and
uploads its JSON evidence. It is **code/database backward-read compatibility**, not a tested Docker
image rollback, disaster recovery or a production RTO measurement.

Operator release procedure:

1. Pause participant access/inference; capture pending IDs and announce the maintenance window.
2. Create and verify an immutable pre-release backup; record its hash and prior image digests.
3. Run restore/rollback qualification against a fresh copy before promoting the candidate images.
4. Deploy the pinned candidate; test health, auth, synthetic generation, review and export.
5. If qualification fails, keep access closed. Start the pinned previous API/web images against a
   **fresh restored copy** and the matching connection configuration. Verify exports and auth before
   changing ingress to it. Preserve the failed database for inspection; never overwrite it.
6. Record any post-snapshot submissions that must be replayed. Do not automatically replay paid or
   external requests. Reopen access only with the pilot owner's approval.

Important: `7191186` predates per-participant pilot controls. It must never be exposed to participants
as an active-pilot rollback. The demonstrated fallback is operator-only under maintenance, with
participant access closed. Before invitations, designate and rehearse a rollback release that
contains the pilot restrictions. Unexpected model fingerprints fail pending jobs rather than
silently switching their model. This behavior also needs explicit review during rollback.

## Monitoring

`python -m scripts.monitor` runs as a separate process; the secure deployment includes it as a
restarting service. It polls readiness and operator-protected `/api/operations` every 30 seconds.
Three unavailable checks trigger an API/model alert (roughly 90 seconds plus request latency).
Pending jobs older than 300 seconds or at least three failures in the previous 15 minutes trigger
separate alerts. Events are logged only on transitions; recovery emits `resolved`. Job alerts are
not falsely cleared when their source is unavailable. `/metrics` remains available for an existing
metrics stack. The UI's service snapshot is a point-in-time view, not an uptime monitor.

`SCRIBE_ALERT_WEBHOOK` is optional and must be an authorised HTTPS endpoint. Only timestamp,
condition and state are sent—no transcripts, model keys or feedback. Failed deliveries are logged
and retried while the monitor runs; newest state replaces older undelivered state for that condition.
The queue is in-memory, not durable. Logs alone do not constitute attended alerting. Before inviting
anyone, send a fault/recovery sequence to the selected receiver and record human acknowledgement.
Host failure can also kill this monitor: arrange an independent external heartbeat check before
calling the deployment production. No alert recipient or external uptime check has been connected.

Operator response: close admission if integrity/authentication fails; inspect bounded metadata logs;
restore model availability or roll back using the maintenance procedure; then record resolution.
Do not include transcript text in incident tickets.

## Authorise a synthetic-only pilot

Leave `SCRIBE_PILOT_MANIFEST` unset until approval. `deploy/pilot.template.json` deliberately contains
invalid placeholder dates and cannot activate a pilot accidentally. Copy it to a private file and
fill only actual approved owner/approver, pilot ID, approval timestamp, expiry and participant IDs.
Use pseudonymous IDs and distribute each independent random credential through an approved private
channel. Names/keys must not be committed. Set each `key_env` variable on the API server and mount
the manifest read-only, then set `SCRIBE_PILOT_MANIFEST` to that path. In Compose, use a private
override to mount the manifest and pass only the intended participant variables.

Requirements enforced by the API:

- Production mode, HTTPS-capable Secure cookies, strong distinct operator/participant keys.
- Expiry revokes participant access; operator access remains for closure and evidence collection.
- Dedicated pilot database containing only unchanged library transcripts. Arbitrary/custom input
  is rejected, even if labelled synthetic. Use a fresh pilot volume, not the development database.
- External model profiles are rejected during a pilot. Local gateways must also actually remain local.
- Usage identity comes from authentication, not a participant ID supplied in the request body.
- Only participants can submit pilot feedback; report export, metrics snapshot and deletion are
  operator-controlled. The synthetic workspace is shared, not multi-tenant storage.

Participants should use Case library, review every sentence/citation/contradiction, correct drafts,
approve only supported drafts, then record usability/accuracy ratings and an issue category in
Pilot & operations. Comments and edits must contain no real names, identifiers or patient information.
Input restriction is not a general DLP guarantee for arbitrary human edits/comments.

## Usage, feedback and closure record

The pilot report includes pilot ID, actor, action, job ID, timestamp and structured feedback.
Submission/edit/approval/export actions are recorded without copying the transcript. SQLite audit
records are operational evidence, not an immutable compliance ledger. They are backed up with the DB.

At closure export the report, reconcile observed failures with participant feedback, and have the
owner complete the following—leave blank until real evidence exists:

| Gate | Actual evidence | Owner decision |
| --- | --- | --- |
| Deployment and trusted TLS | Not yet run | Pending |
| Host restore / safe release rollback | Local code/DB drill only | Pending deployment drill |
| Alert delivered and acknowledged | Local fault-state tests only | Pending receiver |
| Authorised participants and dates | None configured | Pending invitation |
| Completed tasks, time spent, issues and corrections | No participant usage | Pending pilot |
| Feedback reviewed; critical issues resolved | No participant feedback | Pending pilot |

Do not promote on schema validity or a seven-case smoke score alone. Pause on any synthetic-boundary
breach, authentication failure, lost review data or unhandled critical feedback. At expiry revoke
credentials, export evidence, confirm agreed deletion/retention, and record go/no-go with limitations.
