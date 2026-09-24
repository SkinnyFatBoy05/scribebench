"""Operator-owned connection allowlist. No user-supplied inference URLs or browser secrets."""

import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .model import SYSTEM_PROMPT, build_model


class Connection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    label: str = Field(min_length=1, max_length=120)
    provider: Literal["ollama", "openai-compatible", "rule-based"]
    base_url: str
    model: str = Field(min_length=1, max_length=200)
    api_key_env: str = ""
    output_mode: Literal["json_schema", "json_object", "prompt"] = "json_schema"
    external: bool = False


class Connections:
    def __init__(self, settings: Settings):
        default = Connection(
            id="default",
            label="Default model",
            provider=settings.model_provider,
            base_url=settings.model_base_url,
            model=settings.model_name,
            output_mode=settings.model_output_mode,
            external=False,
        )
        profiles = [default]
        if settings.models_file:
            profiles += [
                Connection.model_validate(item)
                for item in json.loads(Path(settings.models_file).read_text("utf-8"))
            ]
        self.profiles = {}
        self.models = {}
        self.versions = {}
        for profile in profiles:
            if profile.id in self.profiles:
                raise ValueError("duplicate model connection id")
            url = urlsplit(profile.base_url)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("model base URL must be an HTTP(S) URL without credentials/query")
            local = url.hostname in {
                "127.0.0.1",
                "localhost",
                "::1",
                "host.docker.internal",
                "model",
                "ollama",
            }
            if profile.provider != "rule-based" and not local and url.scheme != "https":
                raise ValueError("remote model connections require HTTPS")
            profile.external = profile.provider != "rule-based" and (profile.external or not local)
            secret = (
                settings.model_api_key
                if profile.id == "default"
                else os.getenv(profile.api_key_env, "")
            )
            if profile.api_key_env and not secret:
                raise ValueError(f"missing credential environment variable for {profile.id}")
            fingerprint = hashlib.sha256(
                (profile.model_dump_json() + settings.model_version + SYSTEM_PROMPT).encode()
            ).hexdigest()[:12]
            version = f"{profile.id}:{profile.model}:{fingerprint}"
            self.profiles[profile.id] = profile
            self.versions[profile.id] = version
            self.models[version] = build_model(
                replace(
                    settings,
                    model_provider=profile.provider,
                    model_base_url=profile.base_url,
                    model_name=profile.model,
                    model_api_key=secret,
                    model_output_mode=profile.output_mode,
                )
            )

    def public(self):
        return [
            {
                "id": p.id,
                "label": p.label,
                "provider": p.provider,
                "model": p.model,
                "external": p.external,
                "version": self.versions[p.id],
            }
            for p in self.profiles.values()
        ]

    async def check(self, connection_id: str):
        profile = self.profiles[connection_id]
        if profile.provider == "rule-based":
            return {
                "available": True,
                "inference_tested": False,
                "detail": "deterministic test baseline",
            }
        model = self.models[self.versions[connection_id]]
        base = profile.base_url.rstrip("/")
        endpoint = (
            base + "/api/tags"
            if profile.provider == "ollama"
            else (base if base.endswith("/v1") else base + "/v1") + "/models"
        )
        headers = (
            {"Authorization": f"Bearer {model.settings.model_api_key}"}
            if model.settings.model_api_key
            else {}
        )
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.get(endpoint, headers=headers)
                response.raise_for_status()
            body = response.json()
            names = (
                [m.get("name") for m in body.get("models", [])]
                if profile.provider == "ollama"
                else [m.get("id") for m in body.get("data", [])]
            )
            return {
                "available": profile.model in names,
                "inference_tested": False,
                "detail": "model listed"
                if profile.model in names
                else "model not listed; check model name or provider discovery support",
            }
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return {
                "available": False,
                "inference_tested": False,
                "detail": "model discovery unavailable; check server configuration",
            }
