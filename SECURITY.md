# Security policy

ScribeBench is a portfolio deployment restricted to synthetic data. Do not submit real patient or health information.

Report vulnerabilities privately through the GitHub repository's security advisory feature. Do not include real patient data in a report, test fixture, screenshot, or log.

## Current controls

- optional deployment-injected API key;
- same-origin reverse proxy and restrictive browser headers;
- bounded input, queue, timeouts, and retries;
- server-side structured validation and evidence-line verification;
- human approval before export;
- deletion endpoint and documented backup retention caveat;
- request metadata logging without transcript or draft content;
- pinned container and training dependencies.

Before real-user use, add an identity provider, per-user and per-case authorisation, immutable audit records, TLS/ingress controls, dependency and image scanning, formal threat modelling, privacy review, clinical governance, and an external penetration test.

