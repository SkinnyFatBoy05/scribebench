import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.connections import Connections
from app.main import create_app
from app.metrics import Metrics
from app.model import OllamaModel, OpenAICompatibleModel, RuleBasedModel


def test_production_requires_strong_key(client):
    with pytest.raises(ValueError, match="production requires"):
        create_app(replace(client.app.state.settings, environment="production"))


def test_sessions_authenticate_exports_metrics_and_revoke(client, tmp_path):
    settings = replace(
        client.app.state.settings,
        db_path=tmp_path / "auth.db",
        environment="production",
        api_key="x" * 40,
    )
    with TestClient(create_app(settings), base_url="https://testserver") as browser:
        assert browser.get("/api/jobs").status_code == 401
        assert browser.get("/metrics").status_code == 401
        assert browser.get("/api/jobs/anything/export").status_code == 401
        assert (
            browser.post(
                "/api/auth/login",
                json={"key": "x" * 40},
                headers={"Origin": "https://evil.invalid"},
            ).status_code
            == 403
        )
        response = browser.post(
            "/api/auth/login", json={"key": "x" * 40}, headers={"Origin": "https://testserver"}
        )
        assert response.status_code == 200
        cookie = response.headers["set-cookie"]
        assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
        token = browser.cookies.get("scribe_session")
        assert browser.get("/api/jobs").status_code == 200
        assert (
            browser.post(
                "/api/jobs", json={}, headers={"Origin": "https://evil.invalid"}
            ).status_code
            == 403
        )
        assert browser.post("/api/auth/logout").status_code == 200
        browser.cookies.set("scribe_session", token)
        assert browser.get("/api/jobs").status_code == 401
        assert browser.get("/api/jobs", headers={"X-API-Key": "x" * 40}).status_code == 200


def test_login_is_rate_limited(client, tmp_path):
    settings = replace(client.app.state.settings, db_path=tmp_path / "rate.db", api_key="secret")
    with TestClient(create_app(settings)) as browser:
        for _ in range(10):
            assert browser.post("/api/auth/login", json={"key": "wrong\u00e9"}).status_code == 401
        assert browser.post("/api/auth/login", json={"key": "wrong"}).status_code == 429


def test_connections_do_not_expose_secrets_and_identity_tracks_endpoint(
    client, tmp_path, monkeypatch
):
    path = tmp_path / "models.json"
    profile = {
        "id": "remote",
        "label": "Private provider",
        "provider": "openai-compatible",
        "base_url": "https://example.invalid/v1",
        "model": "chosen-model",
        "api_key_env": "TEST_MODEL_KEY",
    }
    path.write_text(json.dumps([profile]))
    monkeypatch.setenv("TEST_MODEL_KEY", "not-for-the-browser")
    settings = replace(client.app.state.settings, models_file=str(path))
    first = Connections(settings)
    assert "not-for-the-browser" not in json.dumps(first.public())
    assert first.public()[1]["external"] is True
    profile["base_url"] = "https://other.invalid/v1"
    path.write_text(json.dumps([profile]))
    second = Connections(settings)
    assert first.versions["remote"] != second.versions["remote"]
    profile["base_url"] = "http://other.invalid"
    path.write_text(json.dumps([profile]))
    with pytest.raises(ValueError, match="HTTPS"):
        Connections(settings)


@pytest.mark.parametrize(
    "provider,mode,base",
    [
        ("ollama", "json_object", "http://localhost:11434"),
        ("ollama", "json_schema", "http://localhost:11434"),
        ("openai-compatible", "json_schema", "https://example.invalid/v1"),
        ("openai-compatible", "json_object", "https://example.invalid"),
        ("openai-compatible", "prompt", "https://example.invalid/v1"),
    ],
)
def test_adapter_http_contracts(client, monkeypatch, provider, mode, base):
    transcript = "Patient: I have a cough today."
    draft = asyncio.run(RuleBasedModel().generate(transcript)).draft

    def handler(request):
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        if provider == "ollama":
            assert request.headers["Authorization"] == "Bearer server-secret"
            assert request.url.path == "/api/chat"
            assert body["think"] is False and body["stream"] is False
            assert body["format"] == (
                "json" if mode == "json_object" else draft.model_json_schema()
            )
            return httpx.Response(
                200,
                json={
                    "message": {"content": draft.model_dump_json()},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 10,
                    "eval_count": 20,
                },
            )
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer server-secret"
        assert ("response_format" in body) == (mode != "prompt")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": draft.model_dump_json()}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    settings = replace(
        client.app.state.settings,
        model_base_url=base,
        model_name="test-model",
        model_api_key="server-secret",
        model_output_mode=mode,
    )
    model = OllamaModel(settings) if provider == "ollama" else OpenAICompatibleModel(settings)
    result = asyncio.run(model.generate(transcript))
    assert result.draft == draft and result.input_tokens == 10 and result.output_tokens == 20


def test_rejects_truncated_output(client, monkeypatch):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"choices": [{"finish_reason": "length"}]})
            ),
            **kwargs,
        ),
    )
    with pytest.raises(ValueError, match="incomplete"):
        asyncio.run(OpenAICompatibleModel(client.app.state.settings).generate("Patient: cough"))


def test_metric_memory_and_labels_are_bounded():
    metrics = Metrics()
    for i in range(500):
        metrics.record_request("GET", f"/unknown/{i}", 404)
        metrics.record_job("draft_ready", 10, 1, 1)
    assert len(metrics.requests) == 1
    assert metrics.latency_count == 500
    assert metrics.latency_sum == 5000


def test_model_selection_and_idempotency(client, tmp_path):
    path = tmp_path / "models.json"
    path.write_text(
        json.dumps(
            [
                {
                    "id": "second",
                    "label": "Second baseline",
                    "provider": "rule-based",
                    "model": "second",
                    "base_url": "http://localhost",
                }
            ]
        )
    )
    settings = replace(
        client.app.state.settings, db_path=tmp_path / "selection.db", models_file=str(path)
    )
    with TestClient(create_app(settings)) as browser:
        payload = {
            "synthetic": True,
            "transcript": "Patient: I have a cough today.",
            "model_id": "second",
        }
        response = browser.post(
            "/api/jobs", json=payload, headers={"Idempotency-Key": "selected-model"}
        )
        assert response.status_code == 202
        assert response.json()["model_version"].startswith("second:second:")
        payload["model_id"] = "default"
        assert (
            browser.post(
                "/api/jobs", json=payload, headers={"Idempotency-Key": "selected-model"}
            ).status_code
            == 409
        )
        payload["model_id"] = "unknown"
        assert (
            browser.post(
                "/api/jobs", json=payload, headers={"Idempotency-Key": "unknown-model"}
            ).status_code
            == 422
        )


def test_ambiguous_speaker_policy_and_observation_evidence(client):
    from app.model import apply_safety_policy
    from app.schemas import Evidence, NoteSection
    from app.service import validate_grounding

    draft = asyncio.run(RuleBasedModel().generate("Patient: I have a cough today.")).draft
    abstained = apply_safety_policy("A cough started yesterday.", draft)
    assert abstained.abstained and abstained.reason_for_visit.text == ""
    assert "Safety policy" in abstained.warnings[0]
    draft.observations = NoteSection(
        text="Cough", evidence=[Evidence(line=1, quote="I have a cough today.")]
    )
    with pytest.raises(ValueError, match="clinician evidence"):
        validate_grounding("Patient: I have a cough today.", draft)
