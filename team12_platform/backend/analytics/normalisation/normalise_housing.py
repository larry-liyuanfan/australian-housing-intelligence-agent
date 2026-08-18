# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""Normalise source records into the shared housing analytics schema."""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Optional

from backend.analytics.sentiment.sentiment import analyse_sentiment


REQUIRED_FIELDS = {
    'doc_id',
    'platform',
    'source',
    'query_keyword',
    'title',
    'text',
    'created_at',
    'collected_at',
    'url',
    'city_context',
    'topic',
    'australia_connection',
    'raw_metadata',
}

EXTENDED_FIELDS = {
    'content_type',
    'parent_id',
    'video_id',
    'channel_title',
    'like_count',
    'subtopic',
    'language',
    'keywords',
}

# GDELT theme codes are stored as compact machine labels. Translate common
# housing-related codes so the notebook and report show readable categories.
GDELT_THEME_TO_LABEL: Dict[str, str] = {
    'econ_housing_prices':                 'housing prices',
    'crisislex_c05_need_of_shelters':       'need for shelter',
    'wb_612_housing_finance':              'housing finance',
    'emerg_emergshelter':                  'emergency shelter',
    'wb_2186_social_housing':              'social housing',
    'wb_817_land_and_housing':             'land and housing',
    'tax_fncact_tenants':                  'tenant issues',
    'tax_fncact_tenant':                   'tenant issues',
    'crisislex_crisislexrec':              'housing crisis',
    'ungp_land_property_rights':           'property rights',
    'econ_housing':                        'housing (economic)',
    'wb_1331_housing':                     'housing (world bank)',
    'rental_housing':                      'rental housing',
    'econ_housing_rental':                 'rental market',
    'econ_housing_affordability':          'housing affordability',
    'econ_housing_homelessness':           'homelessness',
    'soc_housing':                         'social housing',
    'housing_australia_future_fund':       'housing australia future fund',
}

_GDELT_CODE_RE = re.compile(
    r'^[a-z]{2,6}_[a-z0-9_]+$',
    re.IGNORECASE,
)


def translate_gdelt_code(code: str) -> str:
    """Return a human-readable label for a GDELT theme code, or the original."""
    key = code.strip().lower()
    if key in GDELT_THEME_TO_LABEL:
        return GDELT_THEME_TO_LABEL[key]
    # If it looks like a code (underscores, no spaces) try to humanise it
    if _GDELT_CODE_RE.match(key):
        parts = key.split('_')
        # Drop leading category prefixes that are numeric or very short
        readable = [p for p in parts if len(p) > 2 and not p.isdigit()]
        if readable:
            return ' '.join(readable)
    return code


def strip_html(raw_html: Optional[str]) -> str:
    """Remove HTML tags and decode entities from source text."""
    if not raw_html:
        return ''

    text = re.sub('<[^>]+>', ' ', str(raw_html))
    text = html_lib.unescape(text)
    text = re.sub('\\s+', ' ', text)

    return text.strip()


def iso_now() -> str:
    """Return the current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def stable_hash(value: Any) -> str:
    """Create a stable hash for repeatable document identifiers."""
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hashlib.sha1(encoded).hexdigest()[:16]


SUBTOPIC_RULES = [
    (
        'rental_crisis',
        [
            r'\brental crisis\b',
            r'\brental stress\b',
            r'\brental pressure\b',
            r'\bcant find rental\b',
            r"\bcan't find rental\b",
            r'\brent too high\b',
            r'\brental insecurity\b',
            r'\bhousing insecurity\b',
        ],
    ),
    (
        'rent_increase',
        [
            r'\brent increase\b',
            r'\brent increases\b',
            r'\brising rent\b',
            r'\brising rents\b',
            r'\brent hike\b',
            r'\brent hikes\b',
            r'\brent arrears\b',
        ],
    ),
    (
        'tenant_rights',
        [
            r'\btenant rights\b',
            r'\btenants?\b',
            r'\blandlord\b',
            r'\blease break\b',
            r'\bqcat\b',
            r'\bncat\b',
            r'\bvcat\b',
            r'\bbond not returned\b',
            r'\brental inspection\b',
            r'\brental bidding\b',
            r'\btax_fncact_tenants\b',
            r'\btax_fncact_tenant\b',
        ],
    ),
    (
        'rental_bond',
        [
            r'\brental bond\b',
            r'\bbond rental\b',
            r'\bbond\b',
        ],
    ),
    (
        'homelessness_and_shelter_need',
        [
            r'\bhomeless\b',
            r'\bhomelessness\b',
            r'\bsleeping in car\b',
            r'\bshelter\b',
            r'\bemerg_emergshelter\b',
            r'\bcrisislex_c05_need_of_shelters\b',
        ],
    ),
    (
        'social_and_public_housing',
        [
            r'\bsocial housing\b',
            r'\bpublic housing\b',
            r'\bpublic housing waiting list\b',
            r'\bhousing waiting list\b',
            r'\bwb_2186_social_housing\b',
        ],
    ),
    (
        'housing_affordability',
        [
            r'\bhousing affordability\b',
            r'\brental affordability\b',
            r'\baffordable housing\b',
            r'\baustralia housing cost of living\b',
            r'\bcost of living\b',
        ],
    ),
    (
        'housing_prices',
        [
            r'\bhousing prices\b',
            r'\bhouse prices\b',
            r'\becon_housing_prices\b',
            r'\bproperty prices\b',
        ],
    ),
    (
        'housing_finance',
        [
            r'\bhousing finance\b',
            r'\bfirst home buyer\b',
            r'\brba interest rate housing\b',
            r'\bmortgage\b',
            r'\binterest rate\b',
            r'\bwb_612_housing_finance\b',
        ],
    ),
    (
        'negative_gearing',
        [
            r'\bnegative gearing\b',
        ],
    ),
    (
        'share_house_and_flatmates',
        [
            r'\bshare house\b',
            r'\bflatmate\b',
            r'\bmoving out\b',
        ],
    ),
    (
        'housing_policy_and_supply',
        [
            r'\bhousing australia future fund\b',
            r'\bhousing policy\b',
            r'\bhousing supply\b',
            r'\bland and housing\b',
            r'\bwb_817_land_and_housing\b',
            r'\bnew construction\b',
        ],
    ),
    (
        'rental_conditions',
        [
            r'\bmould rental\b',
            r'\bunsafe housing\b',
            r'\bpoor housing\b',
            r'\blandlord from hell\b',
        ],
    ),
]


def match_subtopic(text: str) -> Optional[str]:
    """Match housing-related keywords to the closest project subtopic."""
    if not text:
        return None

    text = text.lower()

    for subtopic, patterns in SUBTOPIC_RULES:
        for pattern in patterns:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return subtopic

    return None


def infer_subtopic(
    query_keyword: Optional[str] = '',
    title: Optional[str] = '',
    text: Optional[str] = '',
) -> str:
    """Infer the best housing subtopic from source metadata and text."""
    query_text = str(query_keyword or '').lower()
    content_text = ' '.join(
        str(part)
        for part in [title or '', text or '']
        if part
    ).lower()

    query_match = match_subtopic(query_text)

    if query_match:
        return query_match

    content_match = match_subtopic(content_text)

    if content_match:
        return content_match

    return 'general_housing'


def safe_doc_id(platform: str, raw_id: Optional[str]) -> str:
    """Build a stable document id while avoiding unsafe characters."""
    raw_id = str(raw_id or '').strip()

    if not raw_id:
        raw_id = 'missing_id'

    raw_hash = hashlib.sha1(raw_id.encode('utf-8')).hexdigest()[:16]
    cleaned = re.sub('\\s+', '_', raw_id)
    cleaned = cleaned.replace('/', '_').replace(':', '_')
    cleaned = re.sub('[^A-Za-z0-9._-]', '_', cleaned)

    if len(cleaned) > 160:
        cleaned = f'{cleaned[:120]}_{raw_hash}'

    return f'{platform}_{cleaned}'


def normalise_date(value: Optional[str]) -> Optional[str]:
    """Convert source date values into a consistent ISO-style date."""
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    known_formats = [
        '%Y%m%dT%H%M%SZ',
        '%Y%m%d%H%M%S',
        '%Y%m%d',
    ]

    for fmt in known_formats:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue

    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
        return value
    except ValueError:
        return None


def gdelt_date_to_iso(value: Optional[str]) -> Optional[str]:
    """Convert a GDELT date value into ISO date format where possible."""
    return normalise_date(value)


def read_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    """Yield decoded JSON records from a JSONL file."""
    with path.open('r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue

            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f'Invalid JSON on {path}:{line_no}: {exc}') from exc


def is_base_schema_record(record: Dict[str, Any]) -> bool:
    """Detect records that already use the project housing schema."""
    return REQUIRED_FIELDS.issubset(set(record.keys()))


# GDELT records often have article metadata but short or missing body text.
# Use the title for those records and use title + text for social sources.
_GDELT_PLATFORMS = {'gdelt_doc', 'gdelt', 'gdelt_gkg_article'}


def _sentiment_text_for(doc: Dict[str, Any]) -> str:
    """Return the text string that should be used for sentiment scoring."""
    platform = doc.get('platform', '')

    if platform in _GDELT_PLATFORMS:
        # GDELT article_text is often GDELT metadata codes, not real prose.
        # The article title is short, in plain English, and far more reliable
        # for sentiment scoring.
        title = doc.get('title', '').strip()
        if title:
            return title
        # Fall back to first 500 chars of text only if title is absent
        return doc.get('text', '')[:500]

    # BlueSky, Mastodon, YouTube: concatenate title + text
    return ' '.join(
        str(part)
        for part in [doc.get('title', ''), doc.get('text', '')]
        if part
    )


def attach_sentiment(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Attach sentiment score and label fields to a normalised document."""
    sentiment_text = _sentiment_text_for(doc)

    if not doc.get('subtopic'):
        doc['subtopic'] = infer_subtopic(
            query_keyword=doc.get('query_keyword', ''),
            title=doc.get('title', ''),
            text=doc.get('text', ''),
        )

    doc.update(analyse_sentiment(sentiment_text))

    return doc


def normalise_base_schema_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Clean and enrich a record that already matches the base schema."""
    base = {
        'doc_id': record.get('doc_id', ''),
        'platform': record.get('platform', ''),
        'source': record.get('source', ''),
        'query_keyword': record.get('query_keyword', ''),
        'title': record.get('title', '') or '',
        'text': record.get('text', '') or '',
        'created_at': normalise_date(record.get('created_at')),
        'collected_at': normalise_date(record.get('collected_at')) or iso_now(),
        'url': record.get('url', '') or '',
        'city_context': record.get('city_context', 'australia') or 'australia',
        'topic': record.get('topic', 'housing') or 'housing',
        'subtopic': record.get('subtopic') or infer_subtopic(
            query_keyword=record.get('query_keyword', ''),
            title=record.get('title', ''),
            text=record.get('text', ''),
        ),
        'australia_connection': record.get('australia_connection', 'unknown') or 'unknown',
        'raw_metadata': record.get('raw_metadata', {}),
    }

    for field in EXTENDED_FIELDS:
        if field in record and field not in base:
            base[field] = record[field]

    return base


def normalise_bluesky(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a BlueSky record into the shared housing-post schema."""
    post = raw.get('post', {}) or {}
    raw_id = post.get('uri') or post.get('cid') or stable_hash(raw)

    return {
        'doc_id': safe_doc_id('bluesky', raw_id),
        'platform': 'bluesky',
        'source': post.get('author_handle', '') or '',
        'query_keyword': raw.get('search_query', '') or raw.get('query_keyword', '') or '',
        'title': '',
        'text': post.get('text', '') or '',
        'created_at': normalise_date(post.get('created_at')),
        'collected_at': normalise_date(raw.get('harvested_at')) or iso_now(),
        'url': post.get('uri', '') or '',
        'city_context': 'australia',
        'topic': 'housing',
        'australia_connection': raw.get('query_group', 'unknown') or 'unknown',
        'raw_metadata': raw,
    }


def normalise_mastodon(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a Mastodon record into the shared housing-post schema."""
    status = raw.get('status', {}) or {}
    raw_id = status.get('uri') or status.get('id') or stable_hash(raw)

    return {
        'doc_id': safe_doc_id('mastodon', raw_id),
        'platform': 'mastodon',
        'source': raw.get('instance', '') or '',
        'query_keyword': raw.get('search_hashtag', '') or raw.get('query_keyword', '') or '',
        'title': '',
        'text': strip_html(status.get('content')),
        'created_at': normalise_date(status.get('created_at')),
        'collected_at': normalise_date(raw.get('harvested_at')) or iso_now(),
        'url': status.get('url', '') or status.get('uri', '') or '',
        'city_context': raw.get('filter_region') or 'australia',
        'topic': 'housing',
        'australia_connection': raw.get('query_kind', 'unknown') or 'unknown',
        'raw_metadata': raw,
    }


def infer_query_keyword_from_youtube(raw: Dict[str, Any]) -> str:
    """Handle infer query keyword from youtube logic for the housing analytics pipeline."""
    search_queries = raw.get('search_queries') or []

    if isinstance(search_queries, list) and search_queries:
        first = search_queries[0]

        if isinstance(first, dict) and first.get('query'):
            return str(first['query'])

    return raw.get('query_keyword') or raw.get('query') or 'youtube'


def build_youtube_text(raw: Dict[str, Any]) -> str:
    """Handle build youtube text logic for the housing analytics pipeline."""
    video = raw.get('video', {}) or {}

    title = video.get('title', '') or ''
    description = video.get('description', '') or ''
    tags = video.get('tags') or []

    if isinstance(tags, list):
        tag_text = ' '.join(str(tag) for tag in tags)
    else:
        tag_text = str(tags)

    comment_texts = []
    comments = raw.get('comments') or []

    if isinstance(comments, list):
        for comment in comments:
            if not isinstance(comment, dict):
                continue

            text = (
                comment.get('text')
                or comment.get('textDisplay')
                or comment.get('textOriginal')
                or comment.get('comment_text')
                or ''
            )

            if text:
                comment_texts.append(str(text))

    parts = [
        title,
        description,
        f'Tags: {tag_text}' if tag_text else '',
        'Comments: ' + ' '.join(comment_texts[:20]) if comment_texts else '',
    ]

    return '\n'.join(part for part in parts if part).strip()


def normalise_youtube(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a YouTube source record into the shared housing-post schema."""
    video = raw.get('video', {}) or {}
    video_id = video.get('id') or stable_hash(raw)

    title = video.get('title', '') or ''
    text = build_youtube_text(raw)
    url = f'https://www.youtube.com/watch?v={video_id}' if video_id else ''

    search_queries = raw.get('search_queries') or []
    region_code = ''

    if isinstance(search_queries, list) and search_queries:
        first = search_queries[0]

        if isinstance(first, dict):
            region_code = first.get('region_code', '') or ''

    return {
        'doc_id': safe_doc_id('youtube', video_id),
        'platform': 'youtube',
        'source': video.get('channelTitle', '') or video.get('channelId', '') or '',
        'query_keyword': infer_query_keyword_from_youtube(raw),
        'title': title,
        'text': text,
        'created_at': normalise_date(video.get('publishedAt')),
        'collected_at': (
            normalise_date(raw.get('last_updated_at'))
            or normalise_date(raw.get('first_seen_at'))
            or iso_now()
        ),
        'url': url,
        'city_context': 'australia' if region_code in {'AU', ''} else region_code,
        'topic': 'housing',
        'australia_connection': (
            'youtube_search_region_AU'
            if region_code == 'AU'
            else 'youtube_housing_search'
        ),
        'raw_metadata': raw,
    }


def extract_location_names(raw: Dict[str, Any]) -> list[str]:
    """Handle extract location names logic for the housing analytics pipeline."""
    locations = raw.get('locations') or []
    names: list[str] = []

    if isinstance(locations, list):
        for loc in locations:
            if not isinstance(loc, dict):
                continue

            name = loc.get('full_name')

            if name:
                names.append(str(name))

    return names


def build_gdelt_fallback_text(raw: Dict[str, Any], source: str, url: str) -> str:
    """Handle build gdelt fallback text logic for the housing analytics pipeline."""
    themes = raw.get('themes') or []
    all_themes = raw.get('all_themes') or ''
    location_names = extract_location_names(raw)

    if isinstance(themes, list):
        theme_text = ', '.join(str(t) for t in themes)
    else:
        theme_text = str(themes)

    tone = raw.get('tone') or {}
    tone_text = ''

    if isinstance(tone, dict):
        tone_parts = []

        for key in ['tone', 'positive', 'negative', 'polarity', 'word_count']:
            if key in tone and tone.get(key) is not None:
                tone_parts.append(f'{key}: {tone.get(key)}')

        tone_text = ', '.join(tone_parts)

    parts = [
        'GDELT housing article metadata.',
        f'Source: {source}.' if source else '',
        f'Themes: {theme_text}.' if theme_text else '',
        f'All themes: {all_themes}.' if all_themes else '',
        f"Locations: {', '.join(location_names)}." if location_names else '',
        f'Tone: {tone_text}.' if tone_text else '',
        f'URL: {url}.' if url else '',
    ]

    return ' '.join(part for part in parts if part).strip()


# Prefer explicit query metadata, then fall back to readable GDELT theme labels.
def infer_query_keyword_from_gdelt(raw: Dict[str, Any]) -> str:
    """Handle infer query keyword from gdelt logic for the housing analytics pipeline."""
    explicit_query = (
        raw.get('search_query')
        or raw.get('query_keyword')
        or raw.get('query')
    )

    if explicit_query:
        label = translate_gdelt_code(str(explicit_query))
        return label

    themes = raw.get('themes') or []

    if isinstance(themes, list) and themes:
        return translate_gdelt_code(str(themes[0]).lower())

    all_themes = raw.get('all_themes') or ''

    if isinstance(all_themes, str) and all_themes:
        first_theme = all_themes.split(';')[0].strip()

        if first_theme:
            return translate_gdelt_code(first_theme.lower())

    return 'gdelt'


def infer_australia_connection(raw: Dict[str, Any]) -> str:
    """Handle infer australia connection logic for the housing analytics pipeline."""
    locations = extract_location_names(raw)

    if locations:
        for name in locations:
            if 'Australia' in name:
                return 'location_mentions_australia'

    country = raw.get('sourcecountry') or raw.get('source_country') or raw.get('country')

    if country:
        return str(country)

    return 'Australia'


def normalise_gdelt(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a GDELT/news record into the shared housing-post schema."""
    article = raw.get('article', {}) or {}

    url = (
        article.get('url')
        or raw.get('source_url')
        or raw.get('url')
        or raw.get('documentidentifier')
        or raw.get('DocumentIdentifier')
        or raw.get('document_identifier')
        or ''
    )

    title = (
        article.get('title')
        or raw.get('title')
        or raw.get('headline')
        or raw.get('name')
        or ''
    )

    source = (
        article.get('domain')
        or raw.get('source_name')
        or raw.get('domain')
        or raw.get('source')
        or raw.get('source_domain')
        or raw.get('sourceCommonName')
        or raw.get('SourceCommonName')
        or ''
    )

    text = (
        raw.get('article_text')
        or raw.get('text')
        or raw.get('content')
        or raw.get('body')
        or raw.get('description')
        or title
        or ''
    )

    if not text:
        text = build_gdelt_fallback_text(raw, source=source, url=url)

    seendate = (
        article.get('seendate')
        or raw.get('seendate')
        or raw.get('date')
        or raw.get('publish_date')
        or raw.get('published_at')
        or raw.get('created_at')
        or raw.get('DATE')
        or ''
    )

    location_names = extract_location_names(raw)
    raw_id = (
        url
        or raw.get('gkg_record_id')
        or raw.get('record_id')
        or title
        or stable_hash(raw)
    )

    return {
        'doc_id': safe_doc_id('gdelt_doc', raw_id),
        'platform': 'gdelt_doc',
        'source': source,
        'query_keyword': infer_query_keyword_from_gdelt(raw),
        'title': title,
        'text': text,
        'created_at': gdelt_date_to_iso(seendate),
        'collected_at': normalise_date(raw.get('harvested_at')) or iso_now(),
        'url': url,
        'city_context': ', '.join(location_names[:5]) if location_names else 'australia',
        'topic': 'housing',
        'australia_connection': infer_australia_connection(raw),
        'raw_metadata': raw,
    }


def normalise_record(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Dispatch one raw record to the correct source-specific normaliser."""
    if is_base_schema_record(raw):
        return attach_sentiment(normalise_base_schema_record(raw))

    platform = raw.get('platform')

    if platform == 'bluesky':
        return attach_sentiment(normalise_bluesky(raw))

    if platform == 'mastodon':
        return attach_sentiment(normalise_mastodon(raw))

    if platform in {'gdelt_doc', 'gdelt', 'gdelt_gkg_article'}:
        return attach_sentiment(normalise_gdelt(raw))

    if platform == 'youtube':
        return attach_sentiment(normalise_youtube(raw))

    gdelt_indicators = {
        'article',
        'article_text',
        'seendate',
        'documentidentifier',
        'DocumentIdentifier',
        'document_identifier',
        'sourcecountry',
        'SourceCommonName',
        'sourceCommonName',
        'source_url',
        'source_name',
        'gkg_record_id',
        'all_themes',
        'themes',
        'locations',
        'tone',
        'fetch_status',
    }

    if gdelt_indicators.intersection(set(raw.keys())):
        return attach_sentiment(normalise_gdelt(raw))

    youtube_indicators = {
        'video',
        'comments',
        'comment_fetch',
        'search_queries',
        'first_seen_at',
        'last_updated_at',
    }

    if youtube_indicators.intersection(set(raw.keys())):
        return attach_sentiment(normalise_youtube(raw))

    return None


# Discover final sample files and harvested JSONL files without requiring a
# single hard-coded source folder.
def discover_input_files(
    data_dir: Path,
    samples_dir: Path,
    extra_files: Optional[list[Path]] = None,
) -> list[Path]:
    """Find source data files that should be included in normalisation."""
    paths: list[Path] = []

    if samples_dir.exists():
        paths.extend(sorted(samples_dir.glob('*.jsonl')))

    harvesting_samples = Path('backend/harvesting/samples')
    if harvesting_samples.exists() and harvesting_samples.resolve() != samples_dir.resolve():
        paths.extend(sorted(harvesting_samples.glob('*.jsonl')))

    bluesky_root = data_dir / 'bluesky_au'
    if bluesky_root.exists():
        paths.extend(sorted(bluesky_root.glob('*.jsonl')))

    mastodon_root = data_dir / 'mastodon_au'
    if mastodon_root.exists():
        paths.extend(sorted(mastodon_root.glob('*.jsonl')))

    youtube_root = data_dir / 'youtube-demo'
    if youtube_root.exists():
        paths.extend(sorted(youtube_root.glob('youtube_master_part*.jsonl')))

    gdelt_roots = [
        data_dir / 'gdelt_yearly',
        data_dir / 'gdelt_yearly_25-26_lt100mb',
    ]

    for gdelt_root in gdelt_roots:
        if not gdelt_root.exists():
            continue

        paths.extend(sorted(gdelt_root.glob('*/*/articles/*.jsonl')))
        paths.extend(sorted(gdelt_root.glob('*/*/gkg_high.jsonl')))

        paths.extend(sorted(gdelt_root.glob('*/articles/*.jsonl')))

        gkg_high = gdelt_root / 'high' / 'gkg_high.jsonl'
        if gkg_high.exists():
            paths.append(gkg_high)

    legacy_names = [
        'bluesky_housing.jsonl',
        'mastodon_housing.jsonl',
        'meeting_sample_gdelt_full_run_with_text.jsonl',
    ]

    for name in legacy_names:
        path = data_dir / name
        if path.exists():
            paths.append(path)

    if data_dir.exists():
        for path in sorted(data_dir.glob('*.jsonl')):
            name = path.name.lower()

            if name.startswith('normalised_'):
                continue

            if 'official' in name:
                continue

            paths.append(path)

    if extra_files:
        for path in extra_files:
            if path.exists():
                paths.append(path)
            else:
                print(f'WARNING: extra file not found, skipping: {path}')

    unique_paths: list[Path] = []
    seen: set[Path] = set()

    for path in paths:
        resolved = path.resolve()

        if resolved in seen:
            continue

        unique_paths.append(path)
        seen.add(resolved)

    return unique_paths


def normalise_files(paths: Iterable[Path]) -> Iterator[Dict[str, Any]]:
    """Normalise a collection of input files into project documents."""
    seen_doc_ids: set[str] = set()

    for path in paths:
        read_count = 0
        usable_count = 0
        skipped_count = 0
        duplicate_count = 0

        for raw in read_jsonl(path):
            read_count += 1
            doc = normalise_record(raw)

            if doc is None:
                skipped_count += 1
                continue

            if not doc.get('text'):
                skipped_count += 1
                continue

            doc_id = doc.get('doc_id')

            if not doc_id:
                skipped_count += 1
                continue

            if doc_id in seen_doc_ids:
                duplicate_count += 1
                skipped_count += 1
                continue

            seen_doc_ids.add(doc_id)
            usable_count += 1

            yield doc

        print(
            f'{path}: read={read_count}, usable={usable_count}, '
            f'skipped={skipped_count}, duplicates={duplicate_count}'
        )


def write_jsonl(docs: Iterable[Dict[str, Any]], output_path: Path) -> int:
    """Write normalised records to a JSONL output file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0

    with output_path.open('w', encoding='utf-8') as f:
        for doc in docs:
            f.write(json.dumps(doc, ensure_ascii=False) + '\n')
            count += 1

    return count


def main() -> None:
    """Run this module as a command-line entry point."""
    parser = argparse.ArgumentParser(
        description='Normalise available housing records for ElasticSearch.'
    )

    parser.add_argument(
        '--data-dir',
        default='data',
        help='Project data directory (default: data/).',
    )

    parser.add_argument(
        '--samples-dir',
        default='backend/harvesting/samples',
        help='Directory containing sample normalised JSONL files.',
    )

    parser.add_argument(
    '--output',
    default='data/processed/normalised_housing_posts.jsonl',
    help='Output normalised JSONL file.',
    )

    # Extra files let the team ingest late-arriving source dumps without
    # changing the project directory layout.
    parser.add_argument(
        '--extra-files',
        nargs='*',
        default=[],
        metavar='FILE',
        help=(
            'Additional raw JSONL files to include (any platform). '
            'Use this to explicitly pass bluesky_housing.jsonl or '
            'mastodon_housing.jsonl when they live outside --data-dir. '
            'Example: --extra-files /path/to/bluesky_housing.jsonl '
            '/path/to/mastodon_housing.jsonl'
        ),
    )

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    samples_dir = Path(args.samples_dir)
    extra_files = [Path(f) for f in args.extra_files] if args.extra_files else []

    paths = discover_input_files(data_dir, samples_dir, extra_files=extra_files)

    if not paths:
        raise FileNotFoundError(
            'No JSONL input files found. Checked:\n'
            f'  samples_dir : {samples_dir}\n'
            f'  data_dir    : {data_dir}\n'
            f'  gdelt root  : {data_dir / "gdelt_yearly_25-26_lt100mb"}\n'
            'Tip: use --extra-files to pass paths explicitly.'
        )

    print(f'Discovered {len(paths)} input file(s):')

    for path in paths:
        print(f'  - {path}')

    count = write_jsonl(
        normalise_files(paths),
        Path(args.output),
    )

    print(f'\nWrote {count} normalised records to {args.output}')


if __name__ == '__main__':
    main()
