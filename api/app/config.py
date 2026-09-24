from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: Path
    data_path: Path
    api_key: str
    model_provider: str
    model_version: str
    model_base_url: str
    model_name: str
    model_api_key: str
    model_timeout_seconds: float
    queue_capacity: int
    max_retries: int
    workers: int
    seed_demo: bool
    retry_delay_seconds: float = 0.2
    environment: str = "local"
    model_output_mode: str = "json_schema"
    models_file: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        project_dir = Path(__file__).resolve().parents[1]
        return cls(
            db_path=Path(os.getenv("SCRIBE_DB_PATH", project_dir / "scribebench.db")),
            data_path=Path(
                os.getenv("SCRIBE_DATA_PATH", project_dir / "data" / "synthetic_cases.json")
            ),
            api_key=os.getenv("SCRIBE_API_KEY", ""),
            model_provider=os.getenv("SCRIBE_MODEL_PROVIDER", "ollama"),
            model_version=os.getenv("SCRIBE_MODEL_VERSION", "ollama-qwen3-4b-v1"),
            model_base_url=os.getenv("SCRIBE_MODEL_BASE_URL", "http://127.0.0.1:11434"),
            model_name=os.getenv("SCRIBE_MODEL_NAME", "qwen3:4b"),
            model_api_key=os.getenv("SCRIBE_MODEL_API_KEY", ""),
            model_timeout_seconds=float(os.getenv("SCRIBE_MODEL_TIMEOUT_SECONDS", "180")),
            queue_capacity=max(1, int(os.getenv("SCRIBE_QUEUE_CAPACITY", "32"))),
            max_retries=max(0, int(os.getenv("SCRIBE_MAX_RETRIES", "2"))),
            workers=max(1, int(os.getenv("SCRIBE_WORKERS", "1"))),
            seed_demo=_as_bool(os.getenv("SCRIBE_SEED_DEMO"), False),
            retry_delay_seconds=float(os.getenv("SCRIBE_RETRY_DELAY_SECONDS", "0.2")),
            environment=os.getenv("SCRIBE_ENV", "local"),
            model_output_mode=os.getenv("SCRIBE_MODEL_OUTPUT_MODE", "json_object"),
            models_file=os.getenv("SCRIBE_MODELS_FILE", ""),
        )
