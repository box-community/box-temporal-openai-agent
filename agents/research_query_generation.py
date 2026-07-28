from datetime import timedelta

from temporalio import workflow

from activities.invoke_model import InvokeModelRequest, invoke_model

from .config import EFFICIENT_PROCESSING_MODEL
from .shared import QueryPlan, ResearchPlan, today_str

QUERY_GENERATION_INSTRUCTIONS = f"""
You are a search query specialist who crafts effective web searches.

CORE RESPONSIBILITIES:
1. Generate enough diverse search queries to cover every market named in the research plan
2. Balance specificity with discoverability
3. Target different information types (factual, analytical, recent, historical)
4. Use every requested research language in at least one native-language query

APPROACH:
- Vary query styles: direct questions, topic + keywords, source-specific searches
- Include temporal modifiers when relevant (current year, recent, historical)
- Use domain-specific terminology appropriately
- Create at least one native-language query for each market named in the research question
- Add a cross-market query only when it contributes evidence that local queries cannot
- Keep the complete query plan between 4 and 8 queries

OUTPUT REQUIREMENTS:
- queries: Search queries, each with:
  - query: The actual search string
  - rationale: Why this query addresses research needs  
  - expected_info_type: One of "factual_data", "expert_analysis", "case_studies", "recent_news"
  - priority: 1-5 (5 highest priority)

TODAY'S DATE: {today_str()}
"""


async def generate_queries(
    research_plan: ResearchPlan,
    research_languages: list[str] | None = None,
) -> QueryPlan:
    # Prepare input with research plan context
    aspects_context = chr(10).join(
        f"- {aspect.aspect} (Priority: {aspect.priority}): {aspect.description}"
        for aspect in research_plan.key_aspects
    )
    plan_context = f"""
Research Question: {research_plan.research_question}

Key Aspects to Research:
{aspects_context}

Expected Sources: {", ".join(research_plan.expected_sources)}
Search Strategy: {research_plan.search_strategy}
Success Criteria: {", ".join(research_plan.success_criteria)}
Required Research Languages: {", ".join(research_languages or ["English"])}

Use every required research language in the query plan. Cover every market named in the research
question, but do not create translated duplicates that are unlikely to add evidence.
"""

    result = await workflow.execute_activity(
        invoke_model,
        InvokeModelRequest(
            model=EFFICIENT_PROCESSING_MODEL,
            instructions=QUERY_GENERATION_INSTRUCTIONS,
            input=plan_context,
            response_format=QueryPlan,
        ),
        start_to_close_timeout=timedelta(seconds=300),
        summary="Generating search queries",
    )

    return result.response
