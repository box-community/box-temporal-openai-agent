"""Validate local configuration without printing secret values."""

import os
import sys

from dotenv import load_dotenv

REQUIRED = (
    "OPENAI_API_KEY",
    "BOX_DEVELOPER_TOKEN",
    "BOX_FOLDER_ID",
)


def main() -> int:
    load_dotenv()
    missing = [name for name in REQUIRED if not os.getenv(name)]
    if missing:
        print("Missing required environment variables:")
        for name in missing:
            print(f"- {name}")
        print("Copy .env.example to .env and fill in the missing values.")
        return 1

    folder_id = os.environ["BOX_FOLDER_ID"]
    if not folder_id.isdigit():
        print("BOX_FOLDER_ID should be the numeric ID from the Box folder URL.")
        return 1

    internal_file_ids = list(
        dict.fromkeys(
            file_id.strip()
            for file_id in os.getenv("BOX_INTERNAL_FILE_IDS", "").split(",")
            if file_id.strip()
        )
    )
    internal_hub_id = os.getenv("BOX_INTERNAL_HUB_ID", "").strip()

    if bool(internal_file_ids) == bool(internal_hub_id):
        print("Configure exactly one internal Box source:")
        print("- BOX_INTERNAL_FILE_IDS for 1-24 explicit files, or")
        print("- BOX_INTERNAL_HUB_ID for one curated Hub")
        return 1

    if any(not file_id.isdigit() for file_id in internal_file_ids):
        print("BOX_INTERNAL_FILE_IDS should contain comma-separated numeric Box file IDs.")
        return 1
    if len(internal_file_ids) > 24:
        print("BOX_INTERNAL_FILE_IDS supports at most 24 files (plus the generated report).")
        return 1
    if internal_hub_id and not internal_hub_id.isdigit():
        print("BOX_INTERNAL_HUB_ID should be the numeric ID from the Box Hub URL.")
        return 1

    print("Environment configuration is present.")
    print(f"Box folder ID: {folder_id}")
    if internal_hub_id:
        print(f"Internal Box source: Hub {internal_hub_id}")
    else:
        print(f"Internal Box sources: {len(internal_file_ids)} file(s)")
    print(f"Temporal address: {os.getenv('TEMPORAL_ADDRESS', 'localhost:7233')}")
    print(f"Complex model: {os.getenv('OPENAI_COMPLEX_MODEL', 'gpt-5.6-sol')}")
    print(f"Fast model: {os.getenv('OPENAI_FAST_MODEL', 'gpt-5.6-terra')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
