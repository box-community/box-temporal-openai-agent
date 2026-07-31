"""Run the complete workflow with mocked OpenAI, Box, and Box AI Activities."""

from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from activities.invoke_model import InvokeModelRequest, InvokeModelResponse
from agents.shared import (
    BoxAIDigest,
    BoxAIReviewRequest,
    BoxFileReference,
    LocalizedBrief,
    PublishDigestRequest,
    PublishedResearchPack,
    PublishResearchPackRequest,
    QueryPlan,
    ResearchAspect,
    ResearchPlan,
    ResearchReport,
    ResearchRequest,
    SearchQuery,
    SearchResult,
)
from workflows.deep_research_workflow import DeepResearchWorkflow

TASK_QUEUE = "test-global-signal-desk"

MOCK_RESEARCH_PLAN = ResearchPlan(
    research_question="How does a global signal desk work?",
    key_aspects=[
        ResearchAspect(
            aspect="Research workflow",
            priority=5,
            description="Understand the durable research stages",
        )
    ],
    expected_sources=["primary documentation"],
    search_strategy="Search authoritative sources",
    success_criteria=["Produce a cited report"],
)

MOCK_QUERY_PLAN = QueryPlan(
    queries=[
        SearchQuery(
            query="durable multilingual research",
            rationale="Find a representative source",
            expected_info_type="factual_data",
            priority=5,
        )
    ]
)

MOCK_SEARCH_RESULT = SearchResult(
    query="durable multilingual research",
    sources=["https://example.com/research"],
    key_findings="Durable workflows preserve coordination across long-running research.",
    relevance_score=0.95,
    citations=["Example Research Source — https://example.com/research"],
)

MOCK_RESEARCH_REPORT = ResearchReport(
    executive_summary="A signal desk turns research into reusable knowledge.",
    detailed_analysis="Planning, parallel search, synthesis, and publication form the workflow.",
    key_findings=["Research becomes a durable shared artifact"],
    confidence_assessment="High confidence for the demonstrated architecture.",
    citations=["Example Research Source — https://example.com/research"],
    follow_up_questions=["Which additional markets should be added?"],
)


@activity.defn(name="invoke_model")
async def mock_invoke_model(request: InvokeModelRequest) -> InvokeModelResponse:
    if request.response_format is None:
        return InvokeModelResponse(response_model="mock text", response_format=None)

    response_type = request.response_format.__name__
    if response_type == "ResearchPlan":
        response = MOCK_RESEARCH_PLAN
    elif response_type == "QueryPlan":
        assert "Required Research Languages: French, Japanese" in request.input
        response = MOCK_QUERY_PLAN
    elif response_type == "SearchResult":
        response = MOCK_SEARCH_RESULT
    elif response_type == "ResearchReport":
        response = MOCK_RESEARCH_REPORT
    elif response_type == "LocalizedBrief":
        language = request.input.split("REQUESTED LANGUAGE:", 1)[1].splitlines()[0].strip()
        response = LocalizedBrief(
            language=language,
            title=f"Signal Desk Brief — {language}",
            executive_summary="Localized executive summary.",
            market_signals=["A useful market signal"],
            implications=["Share the finding with the local team"],
            source_note="Derived from the cited master report.",
        )
    else:
        raise ValueError(f"No mock configured for {response_type}")

    return InvokeModelResponse(
        response_model=response.model_dump(),
        response_format=request.response_format,
    )


@activity.defn(name="publish_research_pack")
async def mock_publish_research_pack(
    request: PublishResearchPackRequest,
) -> PublishedResearchPack:
    assert request.report.content.startswith("# Global Signal Desk Research Report")
    assert len(request.localized_briefs) == 2
    return PublishedResearchPack(
        report=BoxFileReference(
            id="1001",
            name="master-report.md",
            parent_folder_id="box-folder-1",
        ),
        localized_briefs=[
            BoxFileReference(
                id=f"box-brief-{index}",
                name=artifact.filename,
                parent_folder_id="box-folder-1",
            )
            for index, artifact in enumerate(request.localized_briefs, start=1)
        ],
        sources=BoxFileReference(
            id="box-sources-1",
            name="sources.json",
            parent_folder_id="box-folder-1",
        ),
    )


@activity.defn(name="analyze_with_box_ai")
async def mock_analyze_with_box_ai(request: BoxAIReviewRequest) -> BoxAIDigest:
    assert request.report_file_id == "1001"
    assert request.report_text.startswith("# Global Signal Desk Research Report")
    if request.internal_hub_id:
        assert request.internal_hub_id == "9001"
        assert request.internal_file_ids == []
    else:
        assert request.internal_file_ids == ["2001", "2002"]
    assert "internal Box" in request.research_question
    return BoxAIDigest(
        answer={
            "executiveDigest": "Box AI digest of external and internal evidence.",
            "externalSignals": ["durable research"],
            "internalSignals": ["institutional knowledge"],
            "markets": ["Poland", "France"],
            "confidenceNotes": "Grounded in the uploaded report.",
            "followUpQuestions": ["Which market is next?"],
        },
        citations=[{"id": "2001", "type": "file", "name": "internal-context.txt"}],
        completion_reason="done",
        created_at="2026-07-22T12:00:00Z",
    )


@activity.defn(name="publish_box_ai_digest")
async def mock_publish_box_ai_digest(request: PublishDigestRequest) -> BoxFileReference:
    assert request.digest.completion_reason == "done"
    return BoxFileReference(
        id="box-digest-1",
        name="box-ai-digest.md",
        parent_folder_id="box-folder-1",
    )


@pytest.mark.asyncio
@pytest.mark.timeout(30)
@pytest.mark.parametrize(
    "internal_context",
    [
        {"internal_box_file_ids": ["2001", "2002"]},
        {"internal_box_hub_id": "9001"},
    ],
    ids=["selected-files", "box-hub"],
)
async def test_global_signal_desk_workflow(internal_context: dict[str, object]) -> None:
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[DeepResearchWorkflow],
            activities=[
                mock_invoke_model,
                mock_publish_research_pack,
                mock_analyze_with_box_ai,
                mock_publish_box_ai_digest,
            ],
        ):
            result = await env.client.execute_workflow(
                DeepResearchWorkflow.run,
                ResearchRequest(
                    query=(
                        "How does a global signal desk combine external research with internal Box "
                        "evidence?"
                    ),
                    research_languages=["French", "Japanese"],
                    output_languages=["English", "Polish"],
                    industry="financial-services",
                    **internal_context,
                ),
                id=(
                    "test-global-signal-desk-"
                    + ("hub" if "internal_box_hub_id" in internal_context else "files")
                ),
                task_queue=TASK_QUEUE,
                run_timeout=timedelta(seconds=30),
            )

    assert result.report.id == "1001"
    assert len(result.localized_briefs) == 2
    assert result.sources.id == "box-sources-1"
    assert result.box_ai_digest.answer["externalSignals"][0] == "durable research"
    assert result.box_ai_digest_file.id == "box-digest-1"
