# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

# Mastodon harvester. Fission Timer @every 30m.
# Queries AU + global Mastodon instances for housing hashtags,
# pushes raw docs to Redis MQ (primary) or writes ES direct (fallback).
from __future__ import annotations
import json, os, sys, base64, urllib.request, urllib.error, ssl, re, html as html_lib
from datetime import datetime, timezone
if os.path.isdir("/userfunc/deployarchive"):
    sys.path.insert(0, "/userfunc/deployarchive")
try:
    from textblob import TextBlob
except ImportError:
    TextBlob = None

# ES connection
ES_HOST = os.getenv("ES_HOST", "https://elasticsearch-es-http.elastic.svc.cluster.local:9200")
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")
ES_VERIFY = os.getenv("ES_VERIFY_CERTS", "0").lower() not in ("0", "false", "no")

# Read secret from K8s mounted volume, fallback to env var
def _read_secret(sname, key):
    for ns in ["default", ""]:
        try:
            path = f"/secrets/{ns}/{sname}/{key}" if ns else f"/secrets/{sname}/{key}"
            return open(path).read().strip()
        except Exception:
            continue
    return os.getenv(key.upper(), "")

MASTODON_TOKENS = _read_secret("mastodon-tokens", "MASTODON_TOKENS")
MAX_PAGES = int(os.getenv("MASTODON_MAX_PAGES", "5"))

# 38 housing-related hashtags
HOUSING_TAGS = [
    "rentalcrisis", "rentcrisis", "rentincrease", "rentfreeze", "rentalbidding",
    "tenantrights", "rentersrights", "rentalstress", "eviction", "evicted",
    "nogroundseviction", "renoviction", "housingcrisis", "housingaffordability",
    "affordablehousing", "socialhousing", "publichousing", "communityhousing",
    "housingshortage", "housingsupply", "housinginsecurity", "homelessness",
    "sleepingrough", "negativegearing", "capitalgainstax", "interestrates",
    "mortgagestress", "firsthomebuyer", "stampduty", "costofliving",
    "costoflivingcrisis", "sharehouse", "flatmate", "boardinghouse",
    "nimby", "yimby", "urbansprawl", "zoning",
]

# AU instances: posts are implicitly AU-relevant
AU_INSTANCES = ["aus.social", "mastodon.au", "melb.social"]
# Global instances: posts need AU region filter
GLOBAL_INSTANCES = ["mastodon.social", "mastodon.online"]
AU_REGION_TOKENS = ["australia", "auspol", "aushousing", "melbourne", "sydney",
    "brisbane", "adelaide", "perth", "hobart", "darwin", "canberra",
    "victoria", "nsw", "queensland"]

AUTH = base64.b64encode(f"{ES_USERNAME}:{ES_PASSWORD}".encode()).decode()
_CTX = ssl.create_default_context()
if not ES_VERIFY:
    _CTX.check_hostname = False
    _CTX.verify_mode = ssl.CERT_NONE

# ES helpers (stdlib only, no external deps)
def _es(method, path, body=None):
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

def _es_index(index, doc_id, doc):
    return _es("PUT", f"{index}/_doc/{doc_id}", doc)

# Harvester state: cursor position for crash-safe incremental harvest
def _read_state(harvester_name):
    r = _es("GET", f"harvester_state/_doc/{harvester_name}")
    if "error" in r: return {}
    return r.get("_source", {})

def _write_state(harvester_name, state):
    doc = {**state, "harvester": harvester_name, "last_run": datetime.now(timezone.utc).isoformat()}
    _es_index("harvester_state", harvester_name, doc)

# Error logging to ES for monitoring
def _log_error(harvester, error_type, msg, raw=""):
    _es("POST", "harvester_errors/_doc", {
        "harvester": harvester, "time": datetime.now(timezone.utc).isoformat(),
        "error_type": error_type, "message": msg, "raw_error": str(raw)[:2000],
    })

# --- Unified sentiment lexicon ---
_NEG_PHR = {
    "rental crisis": -0.80, "housing crisis": -0.80, "rent increase": -0.55,
    "rental stress": -0.75, "housing stress": -0.75, "mortgage stress": -0.65,
    "homelessness": -0.80, "eviction": -0.70, "evicted": -0.70, "housing shortage": -0.65,
    "unaffordable housing": -0.80, "unaffordable rent": -0.80, "housing insecurity": -0.75,
    "rent arrears": -0.65, "priced out": -0.75, "cost of living": -0.45,
    "no grounds eviction": -0.80, "sleeping rough": -0.80, "tent city": -0.85,
    "mould rental": -0.55, "unsafe housing": -0.75, "forced out": -0.70,
    "can't afford": -0.70, "rent burden": -0.65, "skyrocketing rent": -0.80,
    "soaring rent": -0.75, "rent gouging": -0.75,
    "rental squeeze": -0.70, "housing squeeze": -0.70,
    "couch surfing": -0.60, "rent bidding": -0.65,
    "overcrowded housing": -0.70, "slum landlord": -0.80,
    "rental scam": -0.75, "housing waitlist": -0.60, "dodgy landlord": -0.70,
    "mortgage cliff": -0.70, "at all time low": -0.70, "record low": -0.60,
    "living in a car": -0.80, "without a home": -0.80,
    "losing their home": -0.85, "forced to move": -0.70,
    "kicked out": -0.70, "nowhere to live": -0.85,
}
_POS_PHR = {
    "rent relief": 0.60, "affordable housing": 0.45, "housing support": 0.45,
    "new housing supply": 0.40, "social housing investment": 0.45, "tenant support": 0.45,
    "better protection": 0.45, "more secure": 0.45, "rent freeze": 0.50,
    "rent cap": 0.50, "first home buyer": 0.50, "first home owners": 0.55,
    "build to rent": 0.45, "key worker housing": 0.50,
    "cooperative housing": 0.50, "renters rights": 0.50, "tenant rights": 0.50,
    "housing guarantee": 0.55, "shared equity": 0.40,
    "better renting": 0.45, "fair renting": 0.50, "housing justice": 0.45,
}
_NEG_W = {
    "crisis": -0.65, "worse": -0.65, "worst": -0.75, "stress": -0.55,
    "unaffordable": -0.75, "eviction": -0.70, "evicted": -0.70, "homeless": -0.75,
    "homelessness": -0.80, "shortage": -0.55, "insecure": -0.55, "mould": -0.40,
    "unsafe": -0.65, "arrears": -0.50, "struggling": -0.55, "hike": -0.45,
    "burden": -0.45, "vulnerable": -0.45, "uninhabitable": -0.80,
    "dilapidated": -0.65, "overcrowded": -0.65, "desperate": -0.60,
    "hopeless": -0.65, "traumatic": -0.65, "devastating": -0.65,
    "exploitation": -0.65, "unlivable": -0.75, "squeeze": -0.50,
    "skyrocketing": -0.70, "soaring": -0.55, "spiralling": -0.60,
    "crunch": -0.50, "collapsing": -0.70, "unsustainable": -0.60,
    "dire": -0.70, "broken": -0.50, "failing": -0.55, "worsening": -0.60,
    "plight": -0.55, "distress": -0.60, "dispossessed": -0.70, "displaced": -0.55,
    "gentrification": -0.45, "greed": -0.55, "profiteering": -0.60,
    "foreclosure": -0.70, "foreclosed": -0.70, "abandoned": -0.55,
    "low": -0.40, "increase": -0.30, "increasing": -0.35,
    "squeezing": -0.55, "deteriorating": -0.55, "precarious": -0.60,
    "unfair": -0.50, "discrimination": -0.55, "excluded": -0.55,
}
_POS_W = {
    "relief": 0.55, "support": 0.35, "affordable": 0.35, "secure": 0.35,
    "stable": 0.35, "improved": 0.50, "safe": 0.30, "stability": 0.35,
    "recovery": 0.35, "ownership": 0.30, "buyers": 0.25, "homeowners": 0.25,
    "thriving": 0.45, "hopeful": 0.40, "progress": 0.25, "improvements": 0.30,
    "fairer": 0.25, "sustainable": 0.30, "assistance": 0.25,
    "cooperative": 0.30, "inclusive": 0.30, "accessible": 0.30,
    "revitalised": 0.45, "transforming": 0.35, "celebrating": 0.35,
    "empowering": 0.35, "welcomed": 0.25, "initiative": 0.25,
}
_HOUSING_CTX = {
    "rent", "rental", "renter", "renters", "renting", "tenant", "tenants",
    "landlord", "landlords", "housing", "apartment", "apartments", "flat", "flats",
    "mortgage", "mortgages", "property", "eviction", "evictions",
    "homeless", "homelessness", "shelter", "shelters", "lease", "leasing",
    "bond", "bonds", "accommodation", "dwelling", "foreclosure",
}

# Domain lexicon (65%) + TextBlob (35%) hybrid sentiment
def _analyse_sentiment(text: str):
    import math
    if not text: return 0.0, "neutral", 0.0, 0
    c = re.sub(r"https?://\S+|www\.\S+|@\w+", " ", str(text))
    c = re.sub(r"[^0-9A-Za-z\s.,!?\$%'-]", " ", c)
    c = re.sub(r"\s+", " ", c).strip().lower()
    if not c: return 0.0, "neutral", 0.0, 0
    score = 0.0
    for p, w in _NEG_PHR.items():
        if p in c: score += w
    for p, w in _POS_PHR.items():
        if p in c: score += w
    words = re.findall(r"[a-zA-Z']+", c)
    for w in words:
        if w in _NEG_W: score += _NEG_W[w]
        elif w in _POS_W: score += _POS_W[w]
    ws = set(words)
    hits = len(ws & _HOUSING_CTX)
    if hits >= 5: score -= 0.15
    elif hits >= 3: score -= 0.10
    elif hits >= 1: score -= 0.06
    dn = score / max(1.0, math.log(len(words) + 1)) if words else 0.0
    dn = max(-1.0, min(1.0, dn))
    try:
        if TextBlob is not None:
            tbp = float(TextBlob(c).sentiment.polarity)
        else:
            tbp = 0.0
    except Exception:
        tbp = 0.0
    n = (0.35 * tbp + 0.65 * dn) if abs(dn) > 0 else (0.65 * tbp + 0.35 * dn)
    n = max(-1.0, min(1.0, n))
    label = "positive" if n >= 0.04 else "negative" if n <= -0.04 else "neutral"
    return round(n, 4), label, round(min(1.0, abs(n) + 0.15), 4), len(c)

# Strip HTML tags from Mastodon post content
def _strip_html(text):
    if not text: return ""
    text = re.sub('<[^>]+>', ' ', str(text))
    text = html_lib.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()

# Build unique doc_id from post URI or ID
def _safe_id(raw):
    raw = str(raw or '').strip()
    if not raw: raw = 'missing'
    return f"mastodon_{re.sub(r'[^A-Za-z0-9._-]', '_', raw.replace('/','_').replace(':','_'))[:160]}"

# Build ES document from Mastodon status (no sentiment — added by processor or fallback)
def _normalise(instance, tag, status, region=None):
    text = _strip_html(status.get("content"))
    if not text: return None
    raw_id = status.get("uri") or status.get("id") or ""
    uri = status.get("uri", "")
    return {
        "doc_id": _safe_id(raw_id),
        "platform": "mastodon",
        "source": instance,
        "query_keyword": tag,
        "title": "",
        "text": text,
        "created_at": status.get("created_at"),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "url": status.get("url") or uri,
        "city_context": region or "australia",
        "topic": "housing",
        "australia_connection": "global_filtered" if region else "au_housing",
        "housing_relevant": True,
        "raw_metadata": {"instance": instance, "tag": tag, "status_id": status.get("id")},
    }

# Parse instance=token pairs from K8s Secret
def _parse_tokens(token_str):
    tokens = {}
    for pair in token_str.split(","):
        if "=" in pair:
            domain, token = pair.split("=", 1)
            tokens[domain.strip()] = token.strip()
    return tokens

# Check if text contains AU region substring
def _contains_au_region(text, region):
    return region.lower() in text.lower()

# Mastodon API helper
def _mastodon_get(instance, path, token, params=None):
    url = f"https://{instance}/api/v1/{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items() if v)
        url += f"?{qs}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", "CCC-housing-mastodon/1.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()), r.headers.get("Link", "")
    except urllib.error.HTTPError as e:
        return {"error": str(e)}, ""
    except Exception as e:
        return {"error": str(e)}, ""

# Extract max_id from Link header for pagination
def _extract_max_id(link_header):
    m = re.search(r'[?&]max_id=(\d+)', link_header)
    return m.group(1) if m else None

# Harvest one instance+tag combination, with optional AU region filter
def _harvest_instance_tag(instance, tag, token, filter_region=None):
    state_key = f"mastodon_{instance}_{tag}"
    if filter_region:
        state_key += f"_{filter_region}"
    state = _read_state(state_key)
    since_id = state.get("last_cursor")

    collected = 0
    page_docs = []
    params = {"limit": "40"}
    if since_id:
        params["since_id"] = since_id

    for page in range(MAX_PAGES):
        posts, link = _mastodon_get(instance, f"timelines/tag/{tag}", token, params)
        if isinstance(posts, dict) and "error" in posts:
            if "429" in posts.get("error", ""):
                _log_error("mastodon", "rate_limit", f"{instance}/{tag}", posts["error"])
            return collected

        if not isinstance(posts, list):
            break

        for post in posts:
            if filter_region:
                content = post.get("content", "")
                tag_names = " ".join(t.get("name", "") for t in (post.get("tags") or []))
                blob = f"{content} {tag_names}"
                if not _contains_au_region(blob, filter_region):
                    continue

            doc = _normalise(instance, tag, post, filter_region)
            if doc:
                page_docs.append(doc)
                collected += 1

        # Push batch to Redis MQ; fallback to ES direct if Redis down
        if page_docs:
            mq_ok = _publish_mq(page_docs)
            if not mq_ok:
                for d in page_docs:
                    s_score, s_label, s_subj, s_chars = _analyse_sentiment(d["text"])
                    d["sentiment"] = s_score
                    d["sentiment_label"] = s_label
                    d["subjectivity"] = s_subj
                    d["sentiment_text_chars"] = s_chars
                    _es_index("housing_posts", d["doc_id"], d)
            page_docs.clear()

        new_max = _extract_max_id(link)
        if new_max:
            params["max_id"] = new_max
            _write_state(state_key, {"last_cursor": new_max, "posts_last_run": collected})
        else:
            break

    return collected

# Push docs to Redis MQ via raw RESP protocol. Returns False if Redis unreachable.
def _publish_mq(docs):
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(("redis.redis.svc.cluster.local", 6379))
        for doc in docs:
            msg = json.dumps(doc)
            cmd = f"*3\r\n$5\r\nLPUSH\r\n$13\r\nhousing-posts\r\n${len(msg)}\r\n{msg}\r\n"
            sock.sendall(cmd.encode())
        sock.close()
        return True
    except Exception:
        return False

# Main: iterate AU instances (all tags) + global instances (top tags x top regions)
def main():
    tokens = _parse_tokens(MASTODON_TOKENS)
    if not tokens:
        return json.dumps({"status": "error", "message": "No MASTODON_TOKENS configured"})

    total = 0
    errors = 0

    for instance in AU_INSTANCES:
        token = tokens.get(instance)
        if not token: continue
        for tag in HOUSING_TAGS:
            try:
                n = _harvest_instance_tag(instance, tag, token)
                total += n
            except Exception as e:
                _log_error("mastodon", "exception", f"{instance}/{tag}", str(e))
                errors += 1

    for instance in GLOBAL_INSTANCES:
        token = tokens.get(instance)
        if not token: continue
        for tag in HOUSING_TAGS[:10]:
            for region in AU_REGION_TOKENS[:5]:
                try:
                    n = _harvest_instance_tag(instance, tag, token, region)
                    total += n
                except Exception as e:
                    _log_error("mastodon", "exception", f"{instance}/{tag}/{region}", str(e))
                    errors += 1

    return json.dumps({
        "status": "ok",
        "posts_collected": total,
        "errors": errors,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

if __name__ == "__main__":
    print(main())
