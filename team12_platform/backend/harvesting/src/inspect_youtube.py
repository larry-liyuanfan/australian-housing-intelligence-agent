# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Harvesting utility for inspecting or normalising collected source data."""

import json
import sys
from pathlib import Path
from collections import Counter


def inspect_youtube_jsonl(file_path: str) -> None:
    """Print a quick structure preview for YouTube JSONL data."""
    path = Path(file_path)

    total_videos = 0
    videos_with_comments = 0
    total_comments = 0
    skip_reasons = Counter()

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            total_videos += 1
            record = json.loads(line)

            comments = record.get("comments", []) or []
            comment_count = len(comments)

            if comment_count > 0:
                videos_with_comments += 1
                total_comments += comment_count

            comment_fetch = record.get("comment_fetch", {}) or {}
            skip_reason = comment_fetch.get("skip_reason")
            if skip_reason:
                skip_reasons[skip_reason] += 1

    print(f"File: {file_path}")
    print(f"Total videos: {total_videos}")
    print(f"Videos with comments: {videos_with_comments}")
    print(f"Total comments: {total_comments}")
    print("Skip reasons:")
    for reason, count in skip_reasons.most_common():
        print(f"- {reason}: {count}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python inspect_youtube.py <youtube_jsonl_file>")
        sys.exit(1)

    inspect_youtube_jsonl(sys.argv[1])
