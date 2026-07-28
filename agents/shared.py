from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ResearchRequest(BaseModel):
    query: str = Field(min_length=8)
    research_languages: list[str] = Field(default_factory=lambda: ["English"])
    output_languages: list[str] = Field(default_factory=lambda: ["English", "Polish"])
    internal_box_file_ids: list[str] = Field(min_length=1, max_length=24)
    industry: str = "cross-industry"

    @field_validator("research_languages", "output_languages")
    @classmethod
    def normalize_languages(cls, languages: list[str]) -> list[str]:
        normalized: list[str] = []
        for language in languages:
            value = language.strip()
            if value and value.casefold() not in {item.casefold() for item in normalized}:
                normalized.append(value)
        if not normalized:
            raise ValueError("At least one language is required")
        return normalized

    @field_validator("internal_box_file_ids")
    @classmethod
    def normalize_box_file_ids(cls, file_ids: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(file_id.strip() for file_id in file_ids if file_id.strip()))
        if not normalized:
            raise ValueError("At least one internal Box file ID is required")
        if any(not file_id.isdigit() for file_id in normalized):
            raise ValueError("Internal Box file IDs must be numeric")
        if len(normalized) > 24:
            raise ValueError("At most 24 internal Box files are supported")
        return normalized


class ResearchAspect(BaseModel):
    aspect: str
    priority: int
    description: str


class ResearchPlan(BaseModel):
    research_question: str
    key_aspects: list[ResearchAspect]
    expected_sources: list[str]
    search_strategy: str
    success_criteria: list[str]


class SearchQuery(BaseModel):
    query: str
    rationale: str
    expected_info_type: str
    priority: int


class QueryPlan(BaseModel):
    queries: list[SearchQuery]


class SearchResult(BaseModel):
    query: str
    sources: list[str]
    key_findings: str
    relevance_score: float
    citations: list[str]


class ResearchReport(BaseModel):
    executive_summary: str
    detailed_analysis: str
    key_findings: list[str]
    confidence_assessment: str
    citations: list[str]
    follow_up_questions: list[str]


class LocalizedBrief(BaseModel):
    language: str
    title: str
    executive_summary: str
    market_signals: list[str]
    implications: list[str]
    source_note: str


class BoxFileReference(BaseModel):
    id: str
    name: str
    parent_folder_id: str


class TextArtifact(BaseModel):
    filename: str
    content: str


class PublishResearchPackRequest(BaseModel):
    workflow_id: str
    research_query: str
    industry: str
    report: TextArtifact
    localized_briefs: list[TextArtifact]
    sources: TextArtifact


class BoxAIReviewRequest(BaseModel):
    report_file_id: str
    internal_file_ids: list[str]
    research_question: str


class PublishedResearchPack(BaseModel):
    report: BoxFileReference
    localized_briefs: list[BoxFileReference]
    sources: BoxFileReference


class BoxAIDigest(BaseModel):
    answer: dict[str, Any]
    citations: list[dict[str, Any]] = Field(default_factory=list)
    completion_reason: str | None = None
    created_at: str | None = None


class PublishDigestRequest(BaseModel):
    workflow_id: str
    digest: BoxAIDigest


class GlobalSignalDeskResult(BaseModel):
    research_question: str
    report: BoxFileReference
    localized_briefs: list[BoxFileReference]
    sources: BoxFileReference
    box_ai_digest: BoxAIDigest
    box_ai_digest_file: BoxFileReference


def today_str() -> str:
    # Use Temporal workflow time when running inside a workflow.
    # Fall back to the system clock when outside a workflow context.
    try:
        from temporalio import workflow  # type: ignore

        now = workflow.now()
    except Exception:
        now = datetime.now()
    return f"{now:%a} {now:%b} {now.day}, {now:%Y}"
