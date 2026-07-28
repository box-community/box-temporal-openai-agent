from datetime import timedelta

from temporalio import workflow

from activities.invoke_model import InvokeModelRequest, invoke_model

from .config import EFFICIENT_PROCESSING_MODEL
from .shared import LocalizedBrief, ResearchReport

LOCALIZED_BRIEF_INSTRUCTIONS = """
You are a multilingual research editor. Create a concise executive briefing in the requested
language. Preserve names, numbers, uncertainty, and source meaning. Do not invent local facts or
claim that translation changes the underlying evidence. Use natural professional language rather
than literal translation.

OUTPUT REQUIREMENTS:
- language: requested language
- title: useful briefing title in the requested language
- executive_summary: concise synthesis for a decision-maker
- market_signals: 3-6 important signals
- implications: 2-5 practical implications
- source_note: state that the brief is derived from the cited master research report
"""


async def generate_localized_brief(
    original_query: str,
    report: ResearchReport,
    language: str,
) -> LocalizedBrief:
    brief_input = f"""
REQUESTED LANGUAGE: {language}
ORIGINAL RESEARCH QUESTION: {original_query}

EXECUTIVE SUMMARY:
{report.executive_summary}

KEY FINDINGS:
{chr(10).join(f"- {finding}" for finding in report.key_findings)}

CONFIDENCE ASSESSMENT:
{report.confidence_assessment}

CITATIONS:
{chr(10).join(f"- {citation}" for citation in report.citations)}
"""
    result = await workflow.execute_activity(
        invoke_model,
        InvokeModelRequest(
            model=EFFICIENT_PROCESSING_MODEL,
            instructions=LOCALIZED_BRIEF_INSTRUCTIONS,
            input=brief_input,
            response_format=LocalizedBrief,
        ),
        start_to_close_timeout=timedelta(seconds=300),
        summary=f"Creating {language} briefing",
    )
    return result.response
