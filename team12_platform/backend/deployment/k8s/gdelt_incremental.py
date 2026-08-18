# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

"""GDELT GKG incremental harvester — backfill gap then loop every 15 min."""
from __future__ import annotations
import gc, json, os, base64, urllib.request, urllib.error, ssl, re, zipfile, io, csv, time, math
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
try: from textblob import TextBlob
except ImportError: TextBlob = None

# === Unified sentiment lexicon (aligned with BlueSky/Mastodon/YouTube) ===
_SENT_NEG_PHR = {
    "rental crisis": -0.80, "housing crisis": -0.80, "rent increase": -0.55,
    "rental stress": -0.75, "housing stress": -0.75, "mortgage stress": -0.65,
    "homelessness": -0.80, "eviction": -0.70, "evicted": -0.70, "housing shortage": -0.65,
    "unaffordable housing": -0.80, "unaffordable rent": -0.80, "housing insecurity": -0.75,
    "no grounds eviction": -0.80, "sleeping rough": -0.80, "tent city": -0.85,
    "forced out": -0.70, "can't afford": -0.70, "rent burden": -0.65,
    "skyrocketing rent": -0.80, "soaring rent": -0.75, "rental squeeze": -0.70,
    "couch surfing": -0.60, "rent bidding": -0.65, "overcrowded housing": -0.70,
    "slum landlord": -0.80, "dodgy landlord": -0.70, "at all time low": -0.70,
    "record low": -0.60, "forced to move": -0.70, "kicked out": -0.70,
    "nowhere to live": -0.85, "rent gouging": -0.75, "mortgage cliff": -0.70,
}
_SENT_POS_PHR = {
    "rent relief": 0.60, "affordable housing": 0.45, "housing support": 0.45,
    "new housing supply": 0.40, "tenant support": 0.45, "rent freeze": 0.50,
    "rent cap": 0.50, "first home buyer": 0.50, "first home owners": 0.55,
    "build to rent": 0.45, "cooperative housing": 0.50, "renters rights": 0.50,
    "tenant rights": 0.50, "housing guarantee": 0.55, "better renting": 0.45,
    "fair renting": 0.50, "housing justice": 0.45,
}
_SENT_NEG_W = {
    "crisis": -0.65, "eviction": -0.70, "evicted": -0.70, "homeless": -0.75,
    "homelessness": -0.80, "shortage": -0.55, "unaffordable": -0.75, "stress": -0.55,
    "struggling": -0.55, "insecure": -0.55, "arrears": -0.50, "hike": -0.45,
    "burden": -0.45, "vulnerable": -0.45, "desperate": -0.60,
    "hopeless": -0.65, "traumatic": -0.65, "devastating": -0.65,
    "exploitation": -0.65, "unlivable": -0.75, "squeeze": -0.50,
    "skyrocketing": -0.70, "soaring": -0.55, "spiralling": -0.60,
    "collapsing": -0.70, "unsustainable": -0.60, "dire": -0.70,
    "broken": -0.50, "failing": -0.55, "worsening": -0.60,
    "plight": -0.55, "distress": -0.60, "dispossessed": -0.70,
    "gentrification": -0.45, "greed": -0.55, "foreclosure": -0.70,
    "abandoned": -0.55, "low": -0.40, "increase": -0.30,
    "squeezing": -0.55, "precarious": -0.60, "unfair": -0.50,
    "discrimination": -0.55, "excluded": -0.55,
}
_SENT_POS_W = {
    "relief": 0.55, "support": 0.35, "affordable": 0.35, "secure": 0.35,
    "stable": 0.35, "improved": 0.50, "safe": 0.30, "stability": 0.35,
    "recovery": 0.35, "ownership": 0.30, "buyers": 0.25, "homeowners": 0.25,
    "thriving": 0.45, "hopeful": 0.40, "progress": 0.25, "improvements": 0.30,
    "fairer": 0.25, "sustainable": 0.30, "assistance": 0.25,
    "cooperative": 0.30, "inclusive": 0.30, "accessible": 0.30,
    "revitalised": 0.45, "transforming": 0.35, "empowering": 0.35,
    "welcomed": 0.25, "initiative": 0.25,
}
_SENT_HOUSING_CTX = {
    "rent", "rental", "renter", "renters", "renting", "tenant", "tenants",
    "landlord", "landlords", "housing", "apartment", "apartments", "flat", "flats",
    "mortgage", "mortgages", "property", "eviction", "evictions",
    "homeless", "homelessness", "shelter", "shelters", "lease", "leasing",
    "bond", "bonds", "accommodation", "dwelling", "foreclosure",
}

def _analyse_sentiment(text: str):
    """Domain-lexicon sentiment — same algorithm across all 4 platforms."""
    if not text: return 0.0, "neutral", 0.0
    t = re.sub(r"[^0-9A-Za-z\s.,!?'-]", " ", str(text).lower())
    t = re.sub(r"\s+", " ", t).strip()
    if not t: return 0.0, "neutral", 0.0
    score = 0.0
    for p, w in _SENT_NEG_PHR.items():
        if p in t: score += w
    for p, w in _SENT_POS_PHR.items():
        if p in t: score += w
    words = re.findall(r"[a-zA-Z']+", t)
    for w in words:
        if w in _SENT_NEG_W: score += _SENT_NEG_W[w]
        elif w in _SENT_POS_W: score += _SENT_POS_W[w]
    ws = set(words)
    hits = len(ws & _SENT_HOUSING_CTX)
    if hits >= 5: score -= 0.15
    elif hits >= 3: score -= 0.10
    elif hits >= 1: score -= 0.06
    dn = score / max(1.0, math.log(len(words) + 1)) if words else 0.0
    dn = max(-1.0, min(1.0, dn))
    tbp = 0.0
    if TextBlob is not None:
        try:
            tbp = float(TextBlob(t).sentiment.polarity)
        except Exception:
            pass
    n = (0.35 * tbp + 0.65 * dn) if abs(dn) > 0 else (0.65 * tbp + 0.35 * dn)
    n = max(-1.0, min(1.0, n))
    label = "positive" if n >= 0.04 else "negative" if n <= -0.04 else "neutral"
    return round(n, 4), label, round(min(1.0, abs(n) + 0.15), 4)

# Config
ES_HOST = os.getenv("ES_HOST", "https://elasticsearch-es-http.elastic.svc.cluster.local:9200")
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")
ES_VERIFY = os.getenv("ES_VERIFY_CERTS", "0") not in ("0", "false", "no")
GKG_MASTER_URL = "http://data.gdeltproject.org/gdeltv2/masterfilelist.txt"
LAST_DATE_FILE = "/tmp/gdelt_last_processed.txt"

# AU housing themes to match
AU_THEMES = re.compile(
    r"(?<![A-Za-z])(HOUSING|HOUSING_PRICES|HOUSING_AFFORDABILITY|EVICTION|HOMELESSNESS|"
    r"RENTAL|WB_2671_HOUSING_AND_CONSTRUCTION|ENV_NATURALRESOURCES_HOUSING)(?![A-Za-z])",
    re.IGNORECASE,
)

AUTH = base64.b64encode(f"{ES_USERNAME}:{ES_PASSWORD}".encode()).decode()
_CTX = ssl.create_default_context()
if not ES_VERIFY:
    _CTX.check_hostname = False
    _CTX.verify_mode = ssl.CERT_NONE


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True, file=__import__('sys').stderr)


# ES helpers
def _es(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{ES_HOST}/{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Basic {AUTH}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30, context=_CTX) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else {"status_code": r.status}
    except urllib.error.HTTPError as e:
        return {"error": str(e), "body": e.read().decode()[:300]}
    except Exception as e:
        return {"error": str(e)}


def _es_index(index: str, doc_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    return _es("PUT", f"{index}/_doc/{doc_id}", doc)


def _read_state(name: str) -> Dict[str, Any]:
    r = _es("GET", f"harvester_state/_doc/{name}")
    return r.get("_source", {}) if "error" not in r else {}


def _write_state(name: str, state: Dict[str, Any]) -> None:
    doc = {**state, "harvester": name, "last_run": datetime.now(timezone.utc).isoformat()}
    _es_index("harvester_state", name, doc)


def _log_error(error_type: str, msg: str, raw: str = "") -> None:
    _es("POST", "harvester_errors/_doc", {
        "harvester": "gdelt_gkg", "time": datetime.now(timezone.utc).isoformat(),
        "error_type": error_type, "message": msg, "raw_error": str(raw)[:2000],
    })


def _read_last_date() -> str:
    try:
        return open(LAST_DATE_FILE).read().strip()
    except Exception:
        state = _read_state("gdelt_gkg")
        return state.get("last_date", "20260508")  # Default: day after last data


def _write_last_date(date_str: str) -> None:
    with open(LAST_DATE_FILE, "w") as f:
        f.write(date_str)
    _write_state("gdelt_gkg", {"last_date": date_str, "last_file": ""})


# GKG processing
def _http_get(url: str, timeout: int = 60) -> Optional[bytes]:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "CCC-gdelt-gkg/1.0")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception as e:
        log(f"  HTTP error: {e}")
        return None


def _safe_id(raw: str) -> str:
    raw = str(raw or "").strip()
    if not raw:
        raw = "missing"
    return f"gdelt_doc_{re.sub(r'[^A-Za-z0-9._-]', '_', raw)[:160]}"


def _is_au_location(locations: str) -> bool:
    """Check V2Locations column for Australian locations (country code AU/AUS)."""
    if not locations:
        return False
    loc_upper = locations.upper()
    return "#AU#" in loc_upper or "#AUS#" in loc_upper or "AUSTRALIA" in loc_upper


def _is_au_domain(domain: str, url: str) -> bool:
    """Check if the source domain is Australian (.au TLD)."""
    d = (domain or "").lower()
    u = (url or "").lower()
    return d.endswith(".au") or ".au/" in u or "://au." in u


def _normalise_gkg(row: dict) -> Optional[dict]:
    themes_col7 = row.get("themes") or ""
    themes_col8 = row.get("V2Themes") or ""
    all_themes = f"{themes_col7};{themes_col8}"
    themes = [t.strip() for t in all_themes.split(";") if t.strip()]

    # Three-pronged match (OR): housing themes, AU location, .au domain
    has_housing_theme = any(AU_THEMES.search(t) for t in themes)
    has_au_location = _is_au_location(row.get("locations") or "")
    has_au_domain = _is_au_domain(row.get("domain") or "", row.get("url") or "")

    if not (has_housing_theme or has_au_location or has_au_domain):
        return None

    url = row.get("url") or row.get("SOURCEURL") or row.get("DocumentIdentifier") or ""
    title = row.get("title") or row.get("Name") or ""
    source = row.get("domain") or row.get("SourceCommonName") or ""
    date_str = row.get("seendate") or row.get("DATE") or ""
    locations = row.get("locations") or ""
    text = f"GDELT GKG: {title}. Themes: {';'.join(themes[:10])}"

    sent_score, sent_label, sent_subj = _analyse_sentiment(text)
    return {
        "doc_id": _safe_id(url or title or str(hash(text))),
        "platform": "gdelt_doc",
        "source": source,
        "query_keyword": themes[0].lower() if themes else "gdelt_gkg",
        "title": title,
        "text": text,
        "created_at": _format_date(date_str),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "url": url,
        "city_context": "australia",
        "topic": "housing",
        "australia_connection": "Australia",
        "housing_relevant": True,
        "like_count": 0,
        "comment_count": 0,
        "sentiment": sent_score,
        "sentiment_label": sent_label,
        "subjectivity": sent_subj,
        "raw_metadata": {
            "themes": themes[:10],
            "source_url": url,
            "filter_reason": ", ".join([
                r for r, v in [
                    ("housing_theme", has_housing_theme),
                    ("au_location", has_au_location),
                    ("au_domain", has_au_domain),
                ] if v
            ]),
        },
    }


def _format_date(d: str) -> Optional[str]:
    d = str(d).strip()
    if not d:
        return None
    for fmt in ["%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S", "%Y%m%d"]:
        try:
            return datetime.strptime(d, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return None


def process_gkg_zip(zip_url: str) -> int:
    """Download + filter one GKG zip. Returns number of matching rows."""
    data = _http_get(zip_url)
    if not data:
        return 0

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            if not names:
                return 0
            text = zf.read(names[0]).decode("utf-8", errors="replace")
    except Exception as e:
        log(f"  Unzip error: {e}")
        return 0

    csv.field_size_limit(1000000)
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    # GKG v2 columns (27 total):
    # GKGRECORDID, DATE, SourceCollectionIdentifier, SourceCommonName, DocumentIdentifier,
    # Counts, V2Counts, Themes, V2Themes, V2Locations, V2Persons, V2Organizations,
    # V2Tone, ...
    ingested = 0
    for row in reader:
        if len(row) < 8:
            continue
        mapping = {
            "themes": row[7] if len(row) > 7 else "",
            "V2Themes": row[8] if len(row) > 8 else "",
            "locations": row[9] if len(row) > 9 else "",
            "url": row[4] if len(row) > 4 else "",
            "title": row[4] if len(row) > 4 else "",
            "domain": row[3] if len(row) > 3 else "",
            "seendate": row[1] if len(row) > 1 else "",
        }
        doc = _normalise_gkg(mapping)
        if doc:
            _es_index("housing_posts", doc["doc_id"], doc)
            ingested += 1

    return ingested


def get_files_for_range(start_date: str, end_date: str) -> list[str]:
    """Download master list, return GKG zip URLs between dates."""
    data = _http_get(GKG_MASTER_URL)
    if not data:
        log("ERROR: Cannot download master file list")
        return []

    urls = []
    start = start_date.replace("-", "")
    end = end_date.replace("-", "")
    for line in data.decode("utf-8", errors="replace").splitlines():
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        url_part = parts[2] if len(parts) > 2 else parts[-1]
        if ".gkg.csv.zip" not in url_part and ".gkg.csv" not in url_part:
            continue
        # Extract date from URL: .../20260513120000.gkg.csv.zip
        m = re.search(r"(\d{14})", url_part)
        if not m:
            continue
        file_date = m.group(1)
        if start <= file_date <= end:
            urls.append(url_part)
    return sorted(urls)


def get_latest_file_url() -> Optional[str]:
    """Get the most recent 15min GKG zip URL."""
    data = _http_get(GKG_MASTER_URL)
    if not data:
        return None
    latest = None
    latest_ts = ""
    for line in data.decode("utf-8", errors="replace").splitlines():
        parts = line.strip().split()
        if len(parts) < 3:
            continue
        url_part = parts[2] if len(parts) > 2 else parts[-1]
        if ".gkg.csv.zip" not in url_part:
            continue
        m = re.search(r"(\d{14})", url_part)
        if m and m.group(1) > latest_ts:
            latest_ts = m.group(1)
            latest = url_part
    return latest


def _get_processed_files() -> set:
    """Read set of already-processed filenames from ES state."""
    state = _read_state("gdelt_gkg")
    raw = state.get("processed_files", "")
    if isinstance(raw, list):
        return set(raw)
    return set(raw.split(",")) if raw else set()


def _mark_file_processed(fname: str) -> None:
    """Append a filename to the processed set in ES state."""
    processed = _get_processed_files()
    processed.add(fname)
    _write_state("gdelt_gkg", {
        "processed_files": ",".join(sorted(processed)[-500:]),  # Keep last 500
        "processed_count": len(processed),
    })


def _detect_previous_crash() -> Optional[str]:
    """Check if the previous run ended abnormally by examining state."""
    state = _read_state("gdelt_gkg")
    last_run = state.get("last_run", "")
    processed = state.get("processed_count", 0)
    status = state.get("status", "")
    if status == "crashed":
        return f"Previous run crashed at processed_count={processed}, last_run={last_run[:19]}"
    return None


def _mark_status(status: str) -> None:
    """Mark harvester status in ES (running/OK/crashed)."""
    _write_state("gdelt_gkg", {"status": status})


# Main
def main():
    log("GDELT GKG incremental harvester starting")

    # Detect if previous run crashed
    crash_reason = _detect_previous_crash()
    if crash_reason:
        log(f"Detected previous crash: {crash_reason}")
        _log_error("crash_recovery", "detected_previous_crash", crash_reason)

    _mark_status("running")

    # Phase 1: Backfill from last known date to now
    last_date = _read_last_date()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")

    if last_date <= today:
        log(f"Backfill: {last_date} → {today}")
        files = get_files_for_range(last_date, today)
        log(f"  Found {len(files)} GKG files to backfill")

        processed_set = _get_processed_files()
        if processed_set:
            log(f"  Resuming: {len(processed_set)} files already processed, skipping...")

        files = [f for f in files if f.split("/")[-1] not in processed_set]
        log(f"  Remaining to process: {len(files)} files")

        done = 0
        for i, url in enumerate(files):
            fname = url.split("/")[-1]
            try:
                log(f"  [{i+1}/{len(files)}] {fname}: downloading...")
                n = process_gkg_zip(url)
                if n > 0:
                    log(f"  [{i+1}/{len(files)}] {fname}: {n} rows OK")
                else:
                    log(f"  [{i+1}/{len(files)}] {fname}: 0 matching rows")
                _mark_file_processed(fname)
                done += 1
            except Exception as e:
                log(f"  [{i+1}/{len(files)}] {fname}: ERROR {type(e).__name__}: {str(e)[:200]}")
                _log_error("gdelt_backfill", fname, str(e))
                _mark_file_processed(fname)  # Mark as processed even if failed

            # Free memory after each file (prevents OOM on large zips)
            gc.collect()

            # Data anomaly: warn if >50 consecutive files all return 0 rows
            if n == 0:
                zero_streak = getattr(main, "_zero_streak", 0) + 1
                main._zero_streak = zero_streak  # type: ignore[attr-defined]
                if zero_streak == 50:
                    log(f"  WARNING: {zero_streak} consecutive files with 0 rows — possible filter issue")
                    _log_error("data_anomaly", "consecutive_zero_rows",
                               f"{zero_streak} files in a row returned 0 matching rows")
            else:
                main._zero_streak = 0  # type: ignore[attr-defined]

            if i < len(files) - 1:
                time.sleep(0.5)

        _write_last_date(today + "235959")
        _mark_status("backfill_complete")
        log(f"Backfill complete: {done} files (total {done + len(processed_set):,})")

    # Phase 2: Incremental loop
    log("Starting incremental loop (every 900s)")
    last_file = ""

    while True:
        try:
            latest_url = get_latest_file_url()
            if latest_url and latest_url != last_file:
                fname = latest_url.split("/")[-1]
                n = process_gkg_zip(latest_url)
                log(f"  Incremental: {fname} → {n} rows")
                last_file = latest_url
                _write_state("gdelt_gkg", {"last_file": last_file})
                _mark_status("incremental_OK")
                gc.collect()
            else:
                log("  No new file yet")
        except Exception as e:
            log(f"  Incremental error: {e}")
            _log_error("exception", "incremental_loop", str(e))
            _mark_status("crashed")

        time.sleep(900)


if __name__ == "__main__":
    main()
