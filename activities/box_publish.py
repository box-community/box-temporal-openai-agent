"""Box publishing and Box AI activities.

All Box network calls live in Temporal Activities. Credentials are read by the worker process and
never enter workflow history. This tutorial does pass report content through workflow history;
production systems should use external payload storage for large or sensitive artifacts.
"""

import asyncio
import io
import json
import os
import re
from typing import Any

from box_sdk_gen import (
    AiItemAsk,
    AiItemAskTypeField,
    BoxClient,
    BoxDeveloperTokenAuth,
    CreateAiAskMode,
    UploadFileAttributes,
    UploadFileAttributesParentField,
    UploadFileVersionAttributes,
)
from temporalio import activity

from agents.shared import (
    BoxAIDigest,
    BoxAIReviewRequest,
    BoxFileReference,
    PublishDigestRequest,
    PublishedResearchPack,
    PublishResearchPackRequest,
    TextArtifact,
)

BOX_AI_DIGEST_PROMPT = """
Compare the externally researched market report with the internal campaign documents supplied in
this request. Produce a decision brief that clearly distinguishes public evidence from internal
observations. Identify where they align, where they conflict, and what the distributor should
validate next.

Return valid JSON only, with these keys:
- executiveDigest: concise combined summary for a senior decision-maker
- externalSignals: list of important findings from the external research report
- internalSignals: list of relevant observations from internal documents
- alignments: list of places where external and internal evidence support each other
- tensions: list of contradictions, mismatches, or evidence gaps
- markets: list of countries or markets discussed
- recommendedActions: list of market-specific actions
- confidenceNotes: concise assessment of evidence strength and limitations
- followUpQuestions: list of useful next research questions

Use only the supplied Box files. Preserve uncertainty and do not invent claims. Cite the source
files used for each conclusion.
"""


def _box_client() -> BoxClient:
    token = os.getenv("BOX_DEVELOPER_TOKEN")
    if not token:
        raise RuntimeError("BOX_DEVELOPER_TOKEN is required by the Box activities")
    return BoxClient(BoxDeveloperTokenAuth(token=token))


def _destination_folder_id() -> str:
    folder_id = os.getenv("BOX_FOLDER_ID")
    if not folder_id:
        raise RuntimeError("BOX_FOLDER_ID is required by the Box activities")
    return folder_id


def _safe_segment(value: str, max_length: int = 70) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip()).strip("-._")
    return (value or "research")[:max_length]


def _existing_file(client: BoxClient, folder_id: str, filename: str) -> Any | None:
    """Find an exact filename in the configured folder for retry-safe uploads."""
    items = client.folders.get_folder_items(folder_id, limit=1000)
    return next(
        (
            item
            for item in (items.entries or [])
            if getattr(item, "type", None) == "file" and getattr(item, "name", None) == filename
        ),
        None,
    )


def _upsert_text_file(
    client: BoxClient,
    folder_id: str,
    artifact: TextArtifact,
) -> BoxFileReference:
    content = io.BytesIO(artifact.content.encode("utf-8"))
    existing = _existing_file(client, folder_id, artifact.filename)

    if existing:
        updated = client.uploads.upload_file_version(
            existing.id,
            UploadFileVersionAttributes(name=artifact.filename),
            content,
        )
        entry = updated.entries[0]
    else:
        uploaded = client.uploads.upload_file(
            UploadFileAttributes(
                name=artifact.filename,
                parent=UploadFileAttributesParentField(id=folder_id),
            ),
            content,
        )
        entry = uploaded.entries[0]

    if not entry.id or not entry.name:
        raise RuntimeError("Box upload returned a file without an ID or name")
    return BoxFileReference(id=entry.id, name=entry.name, parent_folder_id=folder_id)


def _publish_research_pack_sync(
    request: PublishResearchPackRequest,
) -> PublishedResearchPack:
    client = _box_client()
    folder_id = _destination_folder_id()
    prefix = _safe_segment(request.workflow_id)

    report = request.report.model_copy(update={"filename": f"{prefix}--{request.report.filename}"})
    sources = request.sources.model_copy(
        update={"filename": f"{prefix}--{request.sources.filename}"}
    )
    briefs = [
        artifact.model_copy(update={"filename": f"{prefix}--{artifact.filename}"})
        for artifact in request.localized_briefs
    ]

    report_ref = _upsert_text_file(client, folder_id, report)
    brief_refs = [_upsert_text_file(client, folder_id, brief) for brief in briefs]
    sources_ref = _upsert_text_file(client, folder_id, sources)

    return PublishedResearchPack(
        report=report_ref,
        localized_briefs=brief_refs,
        sources=sources_ref,
    )


@activity.defn
async def publish_research_pack(
    request: PublishResearchPackRequest,
) -> PublishedResearchPack:
    return await asyncio.to_thread(_publish_research_pack_sync, request)


def _coerce_answer(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        return {"executiveDigest": value}
    return {"executiveDigest": str(value)}


def _box_ai_file_ids(request: BoxAIReviewRequest) -> list[str]:
    file_ids = list(dict.fromkeys([request.report_file_id, *request.internal_file_ids]))
    if len(file_ids) < 2:
        raise ValueError("Box AI review requires the generated report and internal Box content")
    if len(file_ids) > 25:
        raise ValueError("Box AI review supports at most 25 files")
    return file_ids


def _analyze_with_box_ai_sync(request: BoxAIReviewRequest) -> BoxAIDigest:
    client = _box_client()
    prompt = f"""
BUSINESS RESEARCH QUESTION:
{request.research_question}

{BOX_AI_DIGEST_PROMPT}
"""
    response = client.ai.create_ai_ask(
        CreateAiAskMode.MULTIPLE_ITEM_QA,
        prompt,
        [
            AiItemAsk(id=file_id, type=AiItemAskTypeField.FILE)
            for file_id in _box_ai_file_ids(request)
        ],
        include_citations=True,
    )
    if response is None:
        raise RuntimeError("Box AI returned no response")
    payload = response.to_dict()
    return BoxAIDigest(
        answer=_coerce_answer(payload.get("answer", {})),
        citations=payload.get("citations") or [],
        completion_reason=payload.get("completion_reason"),
        created_at=payload.get("created_at"),
    )


@activity.defn
async def analyze_with_box_ai(request: BoxAIReviewRequest) -> BoxAIDigest:
    return await asyncio.to_thread(_analyze_with_box_ai_sync, request)


def format_box_ai_digest(digest: BoxAIDigest) -> str:
    answer = digest.answer

    def section(title: str, value: Any) -> str:
        if isinstance(value, list):
            body = "\n".join(
                (
                    f"- **{item.get('name') or item.get('id') or 'Box source'}:** "
                    f"{item.get('content') or 'Referenced by Box AI'}"
                    if isinstance(item, dict)
                    else f"- {item}"
                )
                for item in value
            )
        elif isinstance(value, dict):
            body = "\n".join(f"- **{key}:** {item}" for key, item in value.items())
        else:
            body = str(value or "Not provided")
        return f"## {title}\n\n{body}"

    return (
        "\n\n".join(
            [
                "# Box AI Research Digest",
                section("Executive Digest", answer.get("executiveDigest")),
                section("External Signals", answer.get("externalSignals", [])),
                section("Internal Signals", answer.get("internalSignals", [])),
                section("Alignments", answer.get("alignments", [])),
                section("Tensions and Evidence Gaps", answer.get("tensions", [])),
                section("Markets", answer.get("markets", [])),
                section("Recommended Actions", answer.get("recommendedActions", [])),
                section("Confidence Notes", answer.get("confidenceNotes")),
                section("Follow-up Questions", answer.get("followUpQuestions", [])),
                section("Box AI Citations", digest.citations),
                section("Box AI Completion", digest.completion_reason or "Not provided"),
            ]
        )
        + "\n"
    )


def _publish_box_ai_digest_sync(request: PublishDigestRequest) -> BoxFileReference:
    client = _box_client()
    folder_id = _destination_folder_id()
    prefix = _safe_segment(request.workflow_id)
    return _upsert_text_file(
        client,
        folder_id,
        TextArtifact(
            filename=f"{prefix}--box-ai-digest.md",
            content=format_box_ai_digest(request.digest),
        ),
    )


@activity.defn
async def publish_box_ai_digest(request: PublishDigestRequest) -> BoxFileReference:
    return await asyncio.to_thread(_publish_box_ai_digest_sync, request)
