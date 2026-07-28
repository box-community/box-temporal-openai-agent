import asyncio
import json
import re
from datetime import timedelta

from temporalio import workflow
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from agents.localized_brief import generate_localized_brief
    from agents.research_planning import plan_research
    from agents.research_query_generation import generate_queries
    from agents.research_report_synthesis import generate_synthesis
    from agents.research_web_search import search_web
    from agents.shared import (
        BoxAIDigest,
        BoxAIReviewRequest,
        BoxFileReference,
        GlobalSignalDeskResult,
        LocalizedBrief,
        PublishDigestRequest,
        PublishedResearchPack,
        PublishResearchPackRequest,
        ResearchReport,
        ResearchRequest,
        SearchResult,
        TextArtifact,
    )


@workflow.defn
class DeepResearchWorkflow:
    @workflow.run
    async def run(self, request: ResearchRequest) -> GlobalSignalDeskResult:
        # 1. Plan the investigation.
        research_plan = await plan_research(request.query)

        # 2. Create focused search queries.
        query_plan = await generate_queries(research_plan, request.research_languages)

        # 3. Run searches concurrently and keep useful partial results.
        search_results = await self._execute_searches(query_plan.queries)
        if not search_results:
            raise ApplicationError(
                "No web searches produced usable results",
                "NO_SEARCH_RESULTS",
                non_retryable=True,
            )

        # 4. Synthesize the cited master report.
        final_report = await generate_synthesis(
            request.query,
            research_plan,
            search_results,
        )
        formatted_report = self._format_final_report(request, final_report)

        # 5. Produce audience-ready briefs in the requested languages.
        localized_briefs = await asyncio.gather(
            *(
                generate_localized_brief(request.query, final_report, language)
                for language in request.output_languages
            )
        )

        workflow_id = workflow.info().workflow_id
        pack = await workflow.execute_activity(
            "publish_research_pack",
            PublishResearchPackRequest(
                workflow_id=workflow_id,
                research_query=request.query,
                industry=request.industry,
                report=TextArtifact(filename="master-report.md", content=formatted_report),
                localized_briefs=[
                    TextArtifact(
                        filename=f"brief-{self._filename_segment(brief.language)}.md",
                        content=self._format_localized_brief(brief),
                    )
                    for brief in localized_briefs
                ],
                sources=TextArtifact(
                    filename="sources.json",
                    content=self._format_source_manifest(search_results),
                ),
            ),
            result_type=PublishedResearchPack,
            start_to_close_timeout=timedelta(minutes=5),
            summary="Publishing research pack to Box",
        )

        # 6. Ask Box AI to compare the report with internal Box content, then publish its digest.
        box_ai_digest = await workflow.execute_activity(
            "analyze_with_box_ai",
            BoxAIReviewRequest(
                report_file_id=pack.report.id,
                internal_file_ids=request.internal_box_file_ids,
                research_question=request.query,
            ),
            result_type=BoxAIDigest,
            start_to_close_timeout=timedelta(minutes=5),
            summary="Creating Box AI research digest",
        )
        digest_file = await workflow.execute_activity(
            "publish_box_ai_digest",
            PublishDigestRequest(workflow_id=workflow_id, digest=box_ai_digest),
            result_type=BoxFileReference,
            start_to_close_timeout=timedelta(minutes=2),
            summary="Publishing Box AI digest",
        )

        return GlobalSignalDeskResult(
            research_question=request.query,
            report=pack.report,
            localized_briefs=pack.localized_briefs,
            sources=pack.sources,
            box_ai_digest=box_ai_digest,
            box_ai_digest_file=digest_file,
        )

    async def _execute_searches(self, search_queries) -> list[SearchResult]:
        async def execute_single_search(search_query):
            try:
                return await search_web(search_query)
            except Exception:
                workflow.logger.exception(
                    "Search did not complete for query %s",
                    search_query.query,
                )
                return None

        results = await asyncio.gather(*(execute_single_search(query) for query in search_queries))
        return [result for result in results if result is not None]

    @staticmethod
    def _format_final_report(request: ResearchRequest, report: ResearchReport) -> str:
        return f"""# Global Signal Desk Research Report

**Research question:** {request.query}

**Industry lens:** {request.industry}

## Executive Summary

{report.executive_summary}

## Detailed Analysis

{report.detailed_analysis}

## Key Findings

{chr(10).join(f"- {finding}" for finding in report.key_findings)}

## Confidence Assessment

{report.confidence_assessment}

## Sources and Citations

{chr(10).join(f"- {citation}" for citation in report.citations)}

## Recommended Follow-up Questions

{chr(10).join(f"- {question}" for question in report.follow_up_questions)}
"""

    @staticmethod
    def _format_localized_brief(brief: LocalizedBrief) -> str:
        return f"""# {brief.title}

**Language:** {brief.language}

## Executive Summary

{brief.executive_summary}

## Market Signals

{chr(10).join(f"- {signal}" for signal in brief.market_signals)}

## Implications

{chr(10).join(f"- {implication}" for implication in brief.implications)}

## Source Note

{brief.source_note}
"""

    @staticmethod
    def _format_source_manifest(search_results: list[SearchResult]) -> str:
        return json.dumps(
            [result.model_dump(mode="json") for result in search_results],
            ensure_ascii=False,
            indent=2,
        )

    @staticmethod
    def _filename_segment(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "brief"
