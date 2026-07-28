import asyncio
import os

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from activities.box_publish import (
    analyze_with_box_ai,
    publish_box_ai_digest,
    publish_research_pack,
)
from activities.invoke_model import invoke_model
from workflows.deep_research_workflow import DeepResearchWorkflow


async def main() -> None:
    load_dotenv()
    client = await Client.connect(
        os.getenv("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.getenv("TEMPORAL_NAMESPACE", "default"),
        data_converter=pydantic_data_converter,
    )

    worker = Worker(
        client,
        task_queue=os.getenv("TEMPORAL_TASK_QUEUE", "global-signal-desk"),
        workflows=[DeepResearchWorkflow],
        activities=[
            invoke_model,
            publish_research_pack,
            analyze_with_box_ai,
            publish_box_ai_digest,
        ],
    )

    print("Global Signal Desk worker is ready.")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
