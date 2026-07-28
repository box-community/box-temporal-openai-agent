"""Validate local configuration without printing secret values."""

import os
import sys

from dotenv import load_dotenv

REQUIRED = (
    "OPENAI_API_KEY",
    "BOX_DEVELOPER_TOKEN",
    "BOX_FOLDER_ID",
    "BOX_INTERNAL_FILE_IDS",
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
            for file_id in os.environ["BOX_INTERNAL_FILE_IDS"].split(",")
            if file_id.strip()
        )
    )
    if not internal_file_ids or any(not file_id.isdigit() for file_id in internal_file_ids):
        print("BOX_INTERNAL_FILE_IDS should contain comma-separated numeric Box file IDs.")
        return 1
    if len(internal_file_ids) > 24:
        print("BOX_INTERNAL_FILE_IDS supports at most 24 files (plus the generated report).")
        return 1

    print("Environment configuration is present.")
    print(f"Box folder ID: {folder_id}")
    print(f"Internal Box sources: {len(internal_file_ids)} file(s)")
    print(f"Temporal address: {os.getenv('TEMPORAL_ADDRESS', 'localhost:7233')}")
    print(f"Complex model: {os.getenv('OPENAI_COMPLEX_MODEL', 'gpt-5.6-sol')}")
    print(f"Fast model: {os.getenv('OPENAI_FAST_MODEL', 'gpt-5.6-terra')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
