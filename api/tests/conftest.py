from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    root = Path(__file__).resolve().parents[1]
    settings = Settings(
        db_path=tmp_path / "test.db",
        data_path=root / "data" / "synthetic_cases.json",
        api_key="",
        model_provider="rule-based",
        model_version="test-baseline-v1",
        model_base_url="http://unused",
        model_name="test",
        model_api_key="",
        model_timeout_seconds=1,
        queue_capacity=4,
        max_retries=1,
        workers=1,
        seed_demo=False,
        retry_delay_seconds=0.001,
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
