# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

# Bluesky harvester. Fission Timer @every 30m.
# Searches housing keywords via AT Protocol, filters AU-relevant posts,
# publishes raw docs to Redis MQ (primary) or writes ES direct (fallback).
from __future__ import annotations
import json, os, sys, base64, urllib.request, urllib.error, urllib.parse, ssl, re
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

BSKY_ACCOUNTS = _read_secret("bluesky-accounts", "BSKY_ACCOUNTS")
MAX_QUERIES = int(os.getenv("BSKY_MAX_QUERIES", "30"))
MAX_PAGES = int(os.getenv("BSKY_MAX_PAGES", "3"))

# AU-specific queries — no additional filter needed
AU_ONLY = [
    "negative gearing", "VCAT rental", "NCAT rental", "QCAT rental",
    "Centrelink rent", "Commonwealth Rent Assistance", "NRAS",
    "first home owner grant", "FHOG", "stamp duty Australia",
    "no grounds eviction", "median rent Sydney",
    "median rent Melbourne", "median rent Brisbane",
    "CoreLogic Australia", "realestate.com.au",
]

# General queries — requires AU post-filter
GENERAL = [
    "rental crisis", "rent increase", "rent freeze", "rent cap",
    "tenant rights", "eviction notice", "housing crisis",
    "housing affordability", "homelessness", "housing shortage",
    "mortgage stress", "first home buyer", "build to rent",
    "rental stress", "social housing", "public housing",
]

ALL_QUERIES = list(dict.fromkeys(AU_ONLY + GENERAL))

# AU detection regex: cities, states, jargon, country refs, emoji flags
_AU_CITIES = r"\b(melbourne|sydney|brisbane|adelaide|perth|hobart|darwin|canberra|geelong|newcastle|wollongong|gold\s*coast|sunshine\s*coast|cairns|townsville|ballarat|bendigo|toowoomba|launceston)\b"
_AU_STATES = r"\b(new\s*south\s*wales|nsw|victoria|vic|queensland|qld|western\s*australia|south\s*australia|tasmania|tas|act|northern\s*territory)\b"
_AU_JARGON = r"\b(negative\s*gearing|centrelink|medicare|vcat|ncat|qcat|sacat|acat|nras|fhogg|auspol|rba|corelogic|proptrack|realestate\.com\.au|albanese|dutton|greens\s*housing|afl|nrl)\b"
_AU_COUNTRY = r"\b(australia|aussie)\b"
_AU_EMOJI = "[\U0001F1E6\U0001F1FA\U0001F998\U0001F428]"

_AU_RE = re.compile(f"({_AU_CITIES}|{_AU_STATES}|{_AU_JARGON}|{_AU_COUNTRY}|{_AU_EMOJI})", re.IGNORECASE)

AUTH = base64.b64encode(f"{ES_USERNAME}:{ES_PASSWORD}".encode()).decode()
_CTX = ssl.create_default_context()
if not ES_VERIFY:
    _CTX.check_hostname = False
    _CTX.verify_mode = ssl.CERT_NONE

# ES request helper (stdlib only, no elasticsearch-py)
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
def _read_state(name):
    r = _es("GET", f"harvester_state/_doc/{name}")
    return r.get("_source", {}) if "error" not in r else {}

def _write_state(name, state):
    doc = {**state, "harvester": name, "last_run": datetime.now(timezone.utc).isoformat()}
    _es_index("harvester_state", name, doc)

# Error logging to ES for monitoring
def _log_error(harv, etype, msg, raw=""):
    _es("POST", "harvester_errors/_doc", {
        "harvester": harv, "time": datetime.now(timezone.utc).isoformat(),
        "error_type": etype, "message": msg, "raw_error": str(raw)[:2000],
    })

# Build unique doc_id from post URI
def _safe_id(raw):
    raw = str(raw or '').strip()
    if not raw: raw = 'missing'
    return f"bluesky_{re.sub(r'[^A-Za-z0-9._-]', '_', raw.replace('/','_').replace(':','_'))[:160]}"

# BlueSky AT Protocol session
def _bsky_login(handle, password):
    body = json.dumps({"identifier": handle, "password": password}).encode()
    req = urllib.request.Request("https://bsky.social/xrpc/com.atproto.server.createSession", data=body)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

# BlueSky searchPosts API with cursor pagination
def _bsky_search(jwt, query, cursor=None):
    params = f"?q={urllib.parse.quote(query)}&sort=latest&limit=25"
    if cursor:
        params += f"&cursor={urllib.parse.quote(cursor)}"
    url = f"https://bsky.social/xrpc/app.bsky.feed.searchPosts{params}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {jwt}")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": str(e), "code": e.code}
    except Exception as e:
        return {"error": str(e)}

# Check if post text, bio or handle references Australia
def _is_au_relevant(text, bio="", handle=""):
    blob = f"{text} {bio} {handle}"
    return bool(_AU_RE.search(blob))

# --- Unified sentiment lexicon ---
_NEG_PHRASES = {
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
_POS_PHRASES = {
    "rent relief": 0.60, "affordable housing": 0.45, "housing support": 0.45,
    "new housing supply": 0.40, "social housing investment": 0.45, "tenant support": 0.45,
    "better protection": 0.45, "more secure": 0.45, "rent freeze": 0.50,
    "rent cap": 0.50, "first home buyer": 0.50, "first home owners": 0.55,
    "build to rent": 0.45, "key worker housing": 0.50,
    "cooperative housing": 0.50, "renters rights": 0.50, "tenant rights": 0.50,
    "housing guarantee": 0.55, "shared equity": 0.40,
    "better renting": 0.45, "fair renting": 0.50, "housing justice": 0.45,
}
_NEG_WORDS = {
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
_POS_WORDS = {
    "improved": 0.50, "relief": 0.55, "support": 0.35, "affordable": 0.35,
    "secure": 0.35, "stable": 0.35, "safe": 0.30, "stability": 0.35, "recovery": 0.35,
    "ownership": 0.30, "buyers": 0.25, "homeowners": 0.25, "thriving": 0.45,
    "hopeful": 0.40, "progress": 0.25, "improvements": 0.30,
    "fairer": 0.25, "sustainable": 0.30, "assistance": 0.25,
    "cooperative": 0.30, "inclusive": 0.30, "accessible": 0.30,
    "revitalised": 0.45, "transforming": 0.35, "celebrating": 0.35,
    "empowering": 0.35, "welcomed": 0.25, "initiative": 0.25,
}
_HOUSING_CONTEXT = {
    "rent", "rental", "renter", "renters", "renting", "tenant", "tenants",
    "landlord", "landlords", "housing", "apartment", "apartments", "flat", "flats",
    "mortgage", "mortgages", "property", "eviction", "evictions",
    "homeless", "homelessness", "shelter", "shelters", "lease", "leasing",
    "bond", "bonds", "accommodation", "dwelling", "foreclosure",
}

# Domain lexicon (65%) + TextBlob (35%) hybrid sentiment
def _analyse_sentiment(text: str):
    import math
    if not text:
        return 0.0, "neutral", 0.0, 0
    cleaned = re.sub(r"https?://\S+|www\.\S+", " ", str(text))
    cleaned = re.sub(r"@\w+", " ", cleaned)
    cleaned = re.sub(r"[^0-9A-Za-z\s.,!?\$%'-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    if not cleaned:
        return 0.0, "neutral", 0.0, 0

    score = 0.0
    for phrase, weight in _NEG_PHRASES.items():
        if phrase in cleaned: score += weight
    for phrase, weight in _POS_PHRASES.items():
        if phrase in cleaned: score += weight

    words = re.findall(r"[a-zA-Z']+", cleaned)
    for word in words:
        if word in _NEG_WORDS: score += _NEG_WORDS[word]
        elif word in _POS_WORDS: score += _POS_WORDS[word]

    # Housing context bias: more housing terms = leans negative
    word_set = set(words)
    housing_hits = len(word_set & _HOUSING_CONTEXT)
    if housing_hits >= 5: score -= 0.15
    elif housing_hits >= 3: score -= 0.10
    elif housing_hits >= 1: score -= 0.06

    domain_normalised = score / max(1.0, math.log(len(words) + 1)) if words else 0.0
    domain_normalised = max(-1.0, min(1.0, domain_normalised))

    try:
        if TextBlob is not None:
            tb_polarity = float(TextBlob(cleaned).sentiment.polarity)
        else:
            tb_polarity = 0.0
    except Exception:
        tb_polarity = 0.0

    if abs(domain_normalised) > 0:
        normalised = (0.35 * tb_polarity) + (0.65 * domain_normalised)
    else:
        normalised = (0.65 * tb_polarity) + (0.35 * domain_normalised)

    normalised = max(-1.0, min(1.0, normalised))

    if normalised >= 0.04:
        label = "positive"
    elif normalised <= -0.04:
        label = "negative"
    else:
        label = "neutral"

    return round(normalised, 4), label, round(min(1.0, abs(normalised) + 0.15), 4), len(cleaned)

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

# Main: login, search all queries, push to MQ (fallback to ES direct if Redis down)
def main():
    accounts = []
    for pair in BSKY_ACCOUNTS.split(","):
        if ":" in pair:
            h, p = pair.split(":", 1)
            accounts.append((h.strip(), p.strip()))

    if not accounts:
        return json.dumps({"status": "error", "message": "No BSKY_ACCOUNTS configured"})

    # Hash-based account rotation per hour
    import hashlib
    idx = int(hashlib.md5(datetime.now(timezone.utc).strftime("%Y%m%d%H").encode()).hexdigest(), 16) % len(accounts)
    handle, password = accounts[idx]
    session = _bsky_login(handle, password)
    if "error" in session:
        _log_error("bluesky", "auth_failed", handle, session["error"])
        return json.dumps({"status": "error", "message": f"Login failed: {session['error']}"})

    jwt = session["accessJwt"]
    total = 0
    errors = 0

    for query in ALL_QUERIES[:MAX_QUERIES]:
        state_key = f"bluesky_{re.sub(r'[^a-z0-9]', '_', query.lower())[:80]}"
        state = _read_state(state_key)
        cursor = state.get("last_cursor")

        query_total = 0
        query_docs = []
        for page in range(MAX_PAGES):
            result = _bsky_search(jwt, query, cursor)
            if "error" in result:
                if result.get("code") == 429:
                    _log_error("bluesky", "rate_limit", query, result["error"])
                break

            posts = result.get("posts") or []
            for post in posts:
                text = (post.get("record") or {}).get("text", "")
                author = post.get("author") or {}
                bio = author.get("description", "")
                handle_b = author.get("handle", "")

                if query not in AU_ONLY and not _is_au_relevant(text, bio, handle_b):
                    continue

                uri = post.get("uri", "")
                doc = {
                    "doc_id": _safe_id(uri),
                    "platform": "bluesky",
                    "source": handle_b,
                    "query_keyword": query,
                    "title": "",
                    "text": text,
                    "created_at": (post.get("record") or {}).get("createdAt"),
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "url": uri,
                    "city_context": "australia",
                    "topic": "housing",
                    "australia_connection": "au_only" if query in AU_ONLY else "general_filtered",
                    "housing_relevant": True,
                    "raw_metadata": {"query": query, "post_uri": uri},
                }
                query_docs.append(doc)
                query_total += 1

            # Push batch to Redis MQ; fallback to ES direct if Redis down
            if query_docs:
                mq_ok = _publish_mq(query_docs)
                if not mq_ok:
                    for d in query_docs:
                        s_score, s_label, s_subj, s_chars = _analyse_sentiment(d["text"])
                        d["sentiment"] = s_score
                        d["sentiment_label"] = s_label
                        d["subjectivity"] = s_subj
                        d["sentiment_text_chars"] = s_chars
                        _es_index("housing_posts", d["doc_id"], d)
                query_docs.clear()

            new_cursor = result.get("cursor")
            if new_cursor:
                cursor = new_cursor
                _write_state(state_key, {"last_cursor": cursor, "posts_last_run": query_total})
            else:
                break

        total += query_total

    return json.dumps({
        "status": "ok",
        "posts_collected": total,
        "errors": errors,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

if __name__ == "__main__":
    print(main())
