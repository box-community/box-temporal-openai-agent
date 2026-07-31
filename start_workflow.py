import argparse
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from agents.shared import ResearchRequest
from workflows.deep_research_workflow import DeepResearchWorkflow

DEFAULT_QUERY = (
    "Research current local-language industry publications, national film institute reports, "
    "festival programs, cinema association data, and platform research to compare how audiences "
    "in France, Japan, Brazil, and Poland discover independent films. Assess the roles of "
    "festivals, theatrical release, streaming platforms, critics, creators, and social "
    "communities. The final Box AI decision brief must compare this external evidence with the "
    "internal Box context selected for this project—either explicit files or a curated Box Hub—"
    "clearly distinguishing public findings from internal context. Identify evidence gaps and "
    "implications for market-specific release strategies."
)


def _configured_internal_file_ids() -> list[str]:
    value = os.getenv("BOX_INTERNAL_FILE_IDS", "")
    return [file_id.strip() for file_id in value.split(",") if file_id.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run durable multilingual research and publish it to Box."
    )
    parser.add_argument("query", nargs="?", default=DEFAULT_QUERY)
    parser.add_argument(
        "--research-languages",
        nargs="+",
        default=["French", "Japanese", "Portuguese", "Polish"],
        help="Languages the research plan should cover in external-source searches.",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=["English", "French", "Japanese", "Portuguese", "Polish"],
        help="Languages for the executive briefs.",
    )
    internal_context = parser.add_mutually_exclusive_group()
    internal_context.add_argument(
        "--internal-file-ids",
        nargs="+",
        help="Internal Box file IDs. Defaults to comma-separated BOX_INTERNAL_FILE_IDS.",
    )
    internal_context.add_argument(
        "--internal-hub-id",
        help="Internal Box Hub ID. Defaults to BOX_INTERNAL_HUB_ID.",
    )
    parser.add_argument(
        "--industry",
        default="creative-industries",
        help="Industry lens recorded in the report.",
    )
    parser.add_argument("--workflow-id", help="Optional stable workflow ID.")
    return parser.parse_args()


async def main() -> None:
    load_dotenv()
    args = parse_args()
    client = await Client.connect(
        os.getenv("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
        data_converter=pydantic_data_converter,
    )

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    workflow_id = args.workflow_id or f"global-signal-{timestamp}-{uuid.uuid4().hex[:8]}"

    if args.internal_file_ids is not None:
        internal_file_ids = args.internal_file_ids
        internal_hub_id = None
    elif args.internal_hub_id is not None:
        internal_file_ids = []
        internal_hub_id = args.internal_hub_id
    else:
        internal_file_ids = _configured_internal_file_ids()
        internal_hub_id = os.getenv("BOX_INTERNAL_HUB_ID")

    request = ResearchRequest(
        query=args.query,
        research_languages=args.research_languages,
        output_languages=args.languages,
        internal_box_file_ids=internal_file_ids,
        internal_box_hub_id=internal_hub_id,
        industry=args.industry,
    )

    print(f"Starting Global Signal Desk workflow: {workflow_id}")
    print(f"Research question: {request.query}")
    print(f"Research languages: {', '.join(request.research_languages)}")
    print(f"Brief languages: {', '.join(request.output_languages)}")
    if request.internal_box_hub_id:
        print(f"Internal Box source: Hub {request.internal_box_hub_id}")
    else:
        print(f"Internal Box sources: {len(request.internal_box_file_ids)} file(s)")

    result = await client.execute_workflow(
        DeepResearchWorkflow.run,
        request,
        id=workflow_id,
        task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "global-signal-desk"),
    )

    print("\nResearch pack published to Box:")
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
