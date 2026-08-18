# Unified Document Schema

This document defines the normalised schema used for all harvested posts
before ingestion into ElasticSearch. All platforms (BlueSky, Mastodon,
GDELT, and YouTube) are mapped to this common structure.

## Field Definitions

| Field | ES Type | Nullable | Description |
|---|---|---|---|
| `doc_id` | keyword | No | Unique document ID: `{platform}_{raw_id}` |
| `platform` | keyword | No | Source platform: `bluesky` / `mastodon` / `gdelt_doc` / `youtube` |
| `source` | keyword | Yes | Author handle, Mastodon instance, news domain, or YouTube channel name |
| `query_keyword` | keyword | Yes | The search term, hashtag, or query string used to collect this record |
| `title` | text | Yes | Article headline or YouTube video title; empty for most social posts |
| `text` | text | No | Main content used for analysis, such as post text, article body, video description, or comment text |
| `created_at` | date | Yes | When the post, article, video, or comment was originally published |
| `collected_at` | date | No | When this record was harvested or last updated by our pipeline |
| `url` | keyword | Yes | Permalink to the original post, article, video, or comment |
| `city_context` | keyword | No | Geographic scope: city name or `"australia"` for national-level records |
| `topic` | keyword | No | Fixed as `"housing"` for this project |
| `australia_connection` | keyword | Yes | Query group or connection type, e.g. `au_only`, `au_housing`, `youtube_housing_video` |
| `content_type` | keyword | Yes | Type of content, e.g. `bluesky_post`, `mastodon_post`, `gdelt_article`, `youtube_video`, `youtube_comment` |
| `parent_id` | keyword | Yes | Parent object ID, mainly used to link YouTube comments to their source video |
| `video_id` | keyword | Yes | YouTube video ID if applicable |
| `channel_title` | keyword | Yes | YouTube channel title if applicable |
| `like_count` | integer | Yes | Like count, favourite count, or equivalent engagement metric if available |
| `raw_metadata` | object | Yes | Selected fields from the original raw record, not necessarily the full payload |

## Date Format

All `created_at` and `collected_at` values should be valid date strings that
can be parsed by ElasticSearch.

Preferred examples include `2026-05-03T11:16:46.870Z` and
`2026-05-08T12:47:06.888168+00:00`.

The letter `T` separates the date and time according to ISO-style datetime
format. For example, `2026-05-03T11:16:46` means 11:16:46 on 3 May 2026.

GDELT's native format, such as `20260216T080000Z`, is converted during
normalisation into an ISO-style UTC datetime string.

## Platform Notes

**BlueSky**
- Raw records are post-level records.
- `source` = author handle, e.g. `wyndhamvic.bsky.social`.
- `title` = empty string.
- `text` = `post.text`.
- `created_at` = `post.created_at`.
- `url` = empty in the current dataset because the collected record does not provide a direct public URL.
- `australia_connection` = `query_group` from the raw record.
- `content_type` = `bluesky_post`.
- `like_count` = `post.like_count`.
- One BlueSky raw record is converted into one normalised document.

**Mastodon**
- Raw records are status-level records.
- `source` = Mastodon instance, e.g. `aus.social`.
- `query_keyword` = `search_hashtag`.
- `title` = empty string.
- `text` = HTML-stripped and whitespace-normalised `status.content`.
- `created_at` = `status.created_at`.
- `url` = `status.url`.
- `city_context` = `filter_region` if available, otherwise `"australia"`.
- `australia_connection` = `query_kind` from the raw record.
- `content_type` = `mastodon_post`.
- `like_count` = `status.favourites_count`.
- One Mastodon raw record is converted into one normalised document.

**GDELT**
- Raw records are article-level records.
- `source` = news domain, e.g. `smh.com.au`.
- `title` = article headline.
- `text` = full article body text from `article_text`.
- `created_at` = converted from GDELT `article.seendate`.
- `url` = `article.url`.
- `city_context` = `"australia"`.
- `australia_connection` = `article.sourcecountry`.
- `content_type` = `gdelt_article`.
- `like_count` = `0`.
- One GDELT raw record is converted into one normalised document.

**YouTube**
- Raw records are video-level records.
- A single YouTube raw record contains one `video` object and may contain multiple `comments`.
- The normalisation process outputs one `youtube_video` document for the video title and description.
- If comments are available, each comment is also output as a separate `youtube_comment` document.
- `source` = YouTube channel title.
- `query_keyword` = combined search queries from `search_queries`.
- `channel_title` = YouTube channel title.
- `video_id` = YouTube video ID.
- `parent_id` = empty for `youtube_video`; for `youtube_comment`, it stores the source video ID.
- `content_type` = `youtube_video` or `youtube_comment`.
- `like_count` = video like count for video documents, or comment like count for comment documents.
- YouTube comments are linked back to their source video using `video_id` and `parent_id`.

For YouTube video documents:
- `title` = `video.title`.
- `text` = `video.title` + `video.description`.
- `created_at` = `video.publishedAt`.
- `url` = `https://www.youtube.com/watch?v={video_id}`.
- `australia_connection` = `youtube_housing_video`.

For YouTube comment documents:
- `title` = source video title.
- `text` = `comment.textOriginal` or `comment.textDisplay`.
- `created_at` = `comment.publishedAt`.
- `url` = `https://www.youtube.com/watch?v={video_id}&lc={comment_id}`.
- `australia_connection` = `youtube_housing_comment`.

## ElasticSearch Mapping Notes

The current ElasticSearch mapping draft should include the following field types:

| Field | Recommended ES Type |
|---|---|
| `doc_id` | keyword |
| `platform` | keyword |
| `source` | keyword |
| `query_keyword` | keyword |
| `title` | text |
| `text` | text |
| `created_at` | date |
| `collected_at` | date |
| `url` | keyword |
| `city_context` | keyword |
| `topic` | keyword |
| `australia_connection` | keyword |
| `content_type` | keyword |
| `parent_id` | keyword |
| `video_id` | keyword |
| `channel_title` | keyword |
| `like_count` | integer |
| `raw_metadata` | object with indexing disabled |

`raw_metadata` should not be fully indexed because the original data structures
differ across platforms and may contain nested or inconsistent fields.

## Known Limitations

- BlueSky records currently do not include direct public URLs.
- Some Mastodon records contain non-Australian content despite being collected from Australia-related instances, hashtags, or filtering rules. Relevance filtering may still be needed at the analytics layer.
- GDELT articles can be very long. Consider truncating `text` before ingestion if ElasticSearch storage becomes an issue.
- YouTube data may include videos without comments because comments are disabled, the comment count is zero, or API quota was exhausted before fetching comments.
- YouTube video records and YouTube comment records have different meanings, so downstream analysis should use `content_type` to distinguish them.
| - Official datasets are structurally different from online text data and should not be forced into this schema unless a separate official-data ingestion design is created.| `housing_relevant` | boolean | No | Whether text + query_keyword matches housing keywords |
