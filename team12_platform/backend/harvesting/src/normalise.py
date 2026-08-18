# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Harvesting utility for inspecting or normalising collected source data."""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from html import unescape


def strip_html(html_text: str) -> str:
    """Remove HTML tags and decode entities from source text."""
    if not html_text:
        return ""

    text = re.sub(r"<[^>]+>", " ", html_text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def now_utc() -> str:
    """Return the current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def safe_doc_id(platform: str, raw_id: str) -> str:
    """Build a stable document id while avoiding unsafe characters."""
    raw_id = str(raw_id or "").strip()
    raw_id = re.sub(r"\s+", "_", raw_id)
    raw_id = raw_id.replace("/", "_")
    raw_id = raw_id.replace(":", "_")

    return f"{platform}_{raw_id}"


def to_int(value, default: int = 0) -> int:
    """Convert a value to an integer with a safe fallback."""
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_gdelt_date(seendate: str) -> str:
    """Convert a GDELT seen-date value into a readable timestamp."""
    if not seendate:
        return ""

    try:
        dt = datetime.strptime(seendate, "%Y%m%dT%H%M%SZ")
        return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return seendate


def normalise_bluesky(record: dict) -> dict:
    """Convert a BlueSky record into the shared housing-post schema."""
    post = record.get("post", {}) or {}
    raw_id = post.get("uri") or post.get("cid")

    return {
        "doc_id": safe_doc_id("bluesky", raw_id),
        "platform": "bluesky",
        "source": post.get("author_handle", ""),
        "query_keyword": record.get("search_query", ""),
        "title": "",
        "text": post.get("text", ""),
        "created_at": post.get("created_at", ""),
        "collected_at": record.get("harvested_at", now_utc()),
        "url": "",
        "city_context": "australia",
        "topic": "housing",
        "australia_connection": record.get("query_group", "unknown"),
        "content_type": "bluesky_post",
        "parent_id": "",
        "video_id": "",
        "channel_title": "",
        "like_count": to_int(post.get("like_count")),
        "raw_metadata": {
            "uri": post.get("uri", ""),
            "cid": post.get("cid", ""),
            "author_handle": post.get("author_handle", ""),
            "author_display_name": post.get("author_display_name", ""),
            "author_bio": post.get("author_bio", ""),
            "like_count": post.get("like_count", 0),
            "repost_count": post.get("repost_count", 0),
            "reply_count": post.get("reply_count", 0),
            "langs": post.get("langs", []),
            "search_query": record.get("search_query", ""),
            "query_group": record.get("query_group", ""),
        },
    }


def normalise_mastodon(record: dict) -> dict:
    """Convert a Mastodon record into the shared housing-post schema."""
    status = record.get("status", {}) or {}
    raw_id = status.get("uri") or status.get("id")
    html_content = status.get("content", "")

    return {
        "doc_id": safe_doc_id("mastodon", raw_id),
        "platform": "mastodon",
        "source": record.get("instance", ""),
        "query_keyword": record.get("search_hashtag", ""),
        "title": "",
        "text": strip_html(html_content),
        "created_at": status.get("created_at", ""),
        "collected_at": record.get("harvested_at", now_utc()),
        "url": status.get("url", ""),
        "city_context": record.get("filter_region") or "australia",
        "topic": "housing",
        "australia_connection": record.get("query_kind", "unknown"),
        "content_type": "mastodon_post",
        "parent_id": "",
        "video_id": "",
        "channel_title": "",
        "like_count": to_int(status.get("favourites_count")),
        "raw_metadata": {
            "id": status.get("id", ""),
            "uri": status.get("uri", ""),
            "url": status.get("url", ""),
            "language": status.get("language", ""),
            "tags": status.get("tags", []),
            "account_acct": status.get("account_acct", ""),
            "account_display_name": status.get("account_display_name", ""),
            "reblogs_count": status.get("reblogs_count", 0),
            "favourites_count": status.get("favourites_count", 0),
            "replies_count": status.get("replies_count", 0),
            "sensitive": status.get("sensitive", False),
            "visibility": status.get("visibility", ""),
            "instance": record.get("instance", ""),
            "search_hashtag": record.get("search_hashtag", ""),
            "query_kind": record.get("query_kind", ""),
            "filter_region": record.get("filter_region"),
        },
    }


def normalise_gdelt(record: dict) -> dict:
    """Convert a GDELT/news record into the shared housing-post schema."""
    article = record.get("article", {}) or {}
    url = article.get("url", "")

    return {
        "doc_id": safe_doc_id("gdelt_doc", url),
        "platform": "gdelt_doc",
        "source": article.get("domain", ""),
        "query_keyword": record.get("search_query", ""),
        "title": article.get("title", ""),
        "text": record.get("article_text", ""),
        "created_at": parse_gdelt_date(article.get("seendate", "")),
        "collected_at": record.get("harvested_at", now_utc()),
        "url": url,
        "city_context": "australia",
        "topic": "housing",
        "australia_connection": article.get("sourcecountry", "Australia"),
        "content_type": "gdelt_article",
        "parent_id": "",
        "video_id": "",
        "channel_title": "",
        "like_count": 0,
        "raw_metadata": {
            "url": article.get("url", ""),
            "url_mobile": article.get("url_mobile", ""),
            "title": article.get("title", ""),
            "seendate": article.get("seendate", ""),
            "domain": article.get("domain", ""),
            "language": article.get("language", ""),
            "sourcecountry": article.get("sourcecountry", ""),
            "gdelt_sort": record.get("gdelt_sort", ""),
            "date_slice_index": record.get("date_slice_index"),
            "date_slice_start_utc": record.get("date_slice_start_utc"),
            "date_slice_end_utc": record.get("date_slice_end_utc"),
            "timespan": record.get("timespan"),
            "text_chars": record.get("text_chars"),
            "fetch_status": record.get("fetch_status", ""),
            "fetch_seconds": record.get("fetch_seconds"),
        },
    }


def get_youtube_query_keywords(record: dict) -> str:
    """Extract the YouTube query keyword from collection metadata."""
    queries = record.get("search_queries", []) or []
    keywords = []

    for query in queries:
        if isinstance(query, dict):
            keyword = query.get("query") or query.get("search_query") or ""
        else:
            keyword = str(query)

        if keyword:
            keywords.append(keyword)

    return ", ".join(dict.fromkeys(keywords))


def get_youtube_collected_at(record: dict) -> str:
    """Extract the collection timestamp for a YouTube record."""
    return record.get("last_updated_at") or record.get("first_seen_at") or now_utc()


def normalise_youtube_video(record: dict) -> dict:
    """Convert YouTube video metadata into a housing-post document."""
    video = record.get("video", {}) or {}

    video_id = video.get("id", "")
    title = video.get("title", "") or ""
    description = video.get("description", "") or ""
    combined_text = f"{title}. {description}".strip()

    return {
        "doc_id": safe_doc_id("youtube_video", video_id),
        "platform": "youtube",
        "source": video.get("channelTitle", ""),
        "query_keyword": get_youtube_query_keywords(record),
        "title": title,
        "text": combined_text,
        "created_at": video.get("publishedAt", ""),
        "collected_at": get_youtube_collected_at(record),
        "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
        "city_context": "australia",
        "topic": "housing",
        "australia_connection": "youtube_housing_video",
        "content_type": "youtube_video",
        "parent_id": "",
        "video_id": video_id,
        "channel_title": video.get("channelTitle", ""),
        "like_count": to_int(video.get("likeCount")),
        "raw_metadata": {
            "video_id": video_id,
            "channel_id": video.get("channelId", ""),
            "channel_title": video.get("channelTitle", ""),
            "category_id": video.get("categoryId", ""),
            "default_language": video.get("defaultLanguage", ""),
            "default_audio_language": video.get("defaultAudioLanguage", ""),
            "duration": video.get("duration", ""),
            "view_count": video.get("viewCount"),
            "like_count": video.get("likeCount"),
            "comment_count": video.get("commentCount"),
            "tags": video.get("tags") or [],
            "thumbnail_url": video.get("thumbnails_default_url", ""),
            "comment_fetch": record.get("comment_fetch", {}),
            "first_seen_at": record.get("first_seen_at", ""),
            "last_updated_at": record.get("last_updated_at", ""),
        },
    }


def normalise_youtube_comment(comment: dict, video: dict, record: dict) -> dict:
    """Convert a YouTube comment into a housing-post document linked to its video."""
    comment_id = comment.get("commentId", "")
    video_id = video.get("id", "")
    text = comment.get("textOriginal") or comment.get("textDisplay") or ""

    return {
        "doc_id": safe_doc_id("youtube_comment", comment_id),
        "platform": "youtube",
        "source": video.get("channelTitle", ""),
        "query_keyword": get_youtube_query_keywords(record),
        "title": video.get("title", ""),
        "text": text,
        "created_at": comment.get("publishedAt", ""),
        "collected_at": get_youtube_collected_at(record),
        "url": f"https://www.youtube.com/watch?v={video_id}&lc={comment_id}" if video_id and comment_id else "",
        "city_context": "australia",
        "topic": "housing",
        "australia_connection": "youtube_housing_comment",
        "content_type": "youtube_comment",
        "parent_id": video_id,
        "video_id": video_id,
        "channel_title": video.get("channelTitle", ""),
        "like_count": to_int(comment.get("likeCount")),
        "raw_metadata": {
            "video_id": video_id,
            "comment_id": comment_id,
            "is_reply": comment.get("isReply", False),
            "parent_comment_id": comment.get("parentCommentId"),
            "author_display_name": comment.get("authorDisplayName", ""),
            "like_count": comment.get("likeCount", 0),
        },
    }


def normalise_youtube(record: dict) -> list[dict]:
    """Convert a YouTube source record into the shared housing-post schema."""
    video = record.get("video", {}) or {}
    comments = record.get("comments", []) or []

    results = []

    video_doc = normalise_youtube_video(record)
    if video_doc.get("text", "").strip():
        results.append(video_doc)

    for comment in comments:
        text = comment.get("textOriginal") or comment.get("textDisplay") or ""
        if text and text.strip():
            results.append(normalise_youtube_comment(comment, video, record))

    return results


def normalise_record(record: dict) -> list[dict]:
    """Dispatch one raw record to the correct source-specific normaliser."""
    platform = record.get("platform")

    if platform == "bluesky":
        return [normalise_bluesky(record)]

    if platform == "mastodon":
        return [normalise_mastodon(record)]

    if platform == "gdelt_doc":
        return [normalise_gdelt(record)]

    if platform == "youtube":
        return normalise_youtube(record)

    return []


def normalise_file(input_path: str, output_path: str) -> None:
    """Normalise one input file and write JSONL output records."""
    input_file = Path(input_path)
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    total = 0
    written = 0
    skipped = 0
    seen_doc_ids = set()

    with input_file.open("r", encoding="utf-8") as fin, output_file.open("w", encoding="utf-8") as fout:
        for line in fin:
            if not line.strip():
                continue

            total += 1

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue

            normalised_records = normalise_record(record)

            if not normalised_records:
                skipped += 1
                continue

            for normalised in normalised_records:
                if not normalised.get("text", "").strip():
                    skipped += 1
                    continue

                doc_id = normalised.get("doc_id")
                if not doc_id or doc_id in seen_doc_ids:
                    skipped += 1
                    continue

                seen_doc_ids.add(doc_id)
                fout.write(json.dumps(normalised, ensure_ascii=False) + "\n")
                written += 1

    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Total records: {total}")
    print(f"Written records: {written}")
    print(f"Skipped records: {skipped}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python normalise.py <input_jsonl> <output_jsonl>")
        sys.exit(1)

    normalise_file(sys.argv[1], sys.argv[2])
