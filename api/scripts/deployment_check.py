"""Fail-closed configuration gate. Does not deploy, contact hosts, or print credentials."""

import os
import re


def validate(environment: dict[str, str]) -> list[str]:
    errors = []
    for name in ("SCRIBE_API_IMAGE", "SCRIBE_WEB_IMAGE", "SCRIBE_CADDY_IMAGE"):
        if not re.fullmatch(r"[^\s]+@sha256:[a-f0-9]{64}", environment.get(name, "")):
            errors.append(f"{name} must identify an immutable image digest")
    domain = environment.get("SCRIBE_DOMAIN", "")
    if not re.fullmatch(
        r"[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?)+",
        domain,
    ):
        errors.append("SCRIBE_DOMAIN must be a DNS hostname, without scheme or path")
    key = environment.get("SCRIBE_API_KEY", "")
    if len(key) < 32 or key.startswith("replace-"):
        errors.append(
            "SCRIBE_API_KEY must be a strong non-placeholder key of at least 32 characters"
        )
    return errors


if __name__ == "__main__":
    issues = validate(dict(os.environ))
    if issues:
        for issue in issues:
            print(issue)
        raise SystemExit(1)
    print("Configuration syntax passes. Host/TLS/image/alert qualification is still required.")
