from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    DRAFT_READY = "draft_ready"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    FAILED = "failed"


class Evidence(BaseModel):
    line: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=1000)


class NoteSection(BaseModel):
    text: str = Field(default="", max_length=12_000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=100)


class MissingInformation(BaseModel):
    field: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)


class Contradiction(BaseModel):
    summary: str = Field(min_length=1, max_length=500)
    lines: list[int] = Field(min_length=2, max_length=8)


class StructuredDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason_for_visit: NoteSection
    history: NoteSection
    observations: NoteSection
    missing_information: list[MissingInformation] = Field(default_factory=list, max_length=50)
    contradictions: list[Contradiction] = Field(default_factory=list, max_length=20)
    warnings: list[str] = Field(default_factory=list, max_length=20)
    abstained: bool = False


class CreateJobRequest(BaseModel):
    transcript: str = Field(min_length=20, max_length=50_000)
    synthetic: Literal[True]
    case_id: str | None = Field(default=None, max_length=100)

    @field_validator("transcript")
    @classmethod
    def reject_null_bytes(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("transcript contains a null byte")
        return value.strip()


class EditDraftRequest(BaseModel):
    draft: StructuredDraft


class JobView(BaseModel):
    id: str
    case_id: str | None
    transcript: str
    transcript_sha256: str
    status: JobStatus
    model_version: str
    attempts: int
    draft: StructuredDraft | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None
    latency_ms: float | None
    input_tokens: int
    output_tokens: int


class SyntheticCase(BaseModel):
    id: str
    title: str
    scenario_family: str
    split: Literal["train", "validation", "test"]
    difficulty: str
    transcript: str
    expected: dict[str, object]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    model_provider: str
    model_version: str
