# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

# MQ consumer for Redis housing-posts queue.
# Reads raw posts, computes sentiment (domain lexicon + TextBlob),
# bulk-indexes to Elasticsearch. Supports both Fission MQ trigger (env var)
# and KEDA HTTP connector (Flask request body).
import json, os, sys, ssl, base64, urllib.request, re, math
from datetime import datetime, timezone
if os.path.isdir("/userfunc/deployarchive"):
    sys.path.insert(0, "/userfunc/deployarchive")
try:
    from textblob import TextBlob
except ImportError:
    TextBlob = None

ES_HOST = os.getenv("ES_HOST", "https://elasticsearch-es-http.elastic.svc.cluster.local:9200")
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")
ES_VERIFY = os.getenv("ES_VERIFY_CERTS", "0").lower() not in ("0", "false", "no")
AUTH = base64.b64encode(f"{ES_USERNAME}:{ES_PASSWORD}".encode()).decode()
CTX = ssl.create_default_context()
if not ES_VERIFY:
    CTX.check_hostname = False
    CTX.verify_mode = ssl.CERT_NONE

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

    word_set = set(words)
    housing_hits = len(word_set & _HOUSING_CONTEXT)
    if housing_hits >= 5: score -= 0.15
    elif housing_hits >= 3: score -= 0.10
    elif housing_hits >= 1: score -= 0.06

    domain_normalised = score / max(1.0, math.log(len(words) + 1)) if words else 0.0
    domain_normalised = max(-1.0, min(1.0, domain_normalised))

    try:
        tb_polarity = float(TextBlob(cleaned).sentiment.polarity)
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

# Bulk index to ES with upsert by doc_id
def es_bulk(docs):
    lines = []
    for doc in docs:
        lines.append(json.dumps({"index": {"_index": "housing_posts", "_id": doc["doc_id"]}}))
        lines.append(json.dumps(doc))
    body = "\n".join(lines) + "\n"
    r = urllib.request.Request(f"{ES_HOST}/_bulk", data=body.encode(), method="POST")
    r.add_header("Authorization", f"Basic {AUTH}")
    r.add_header("Content-Type", "application/x-ndjson")
    try:
        with urllib.request.urlopen(r, timeout=60, context=CTX) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}

# Entry point: read messages from MQ trigger (env var) or KEDA HTTP connector (Flask body)
def main():
    raw = os.environ.get("MESSAGE", "")
    if not raw:
        try:
            from flask import request
            raw = request.get_data(as_text=True) or "[]"
        except Exception:
            raw = "[]"
    try:
        messages = json.loads(raw)
    except Exception:
        return json.dumps({"status": "error", "message": f"Invalid input: {raw[:200]}"})

    if not messages:
        return json.dumps({"status": "ok", "count": 0})

    # Normalise: single dict or list of strings/dicts
    if isinstance(messages, dict):
        messages = [messages]
    elif not isinstance(messages, list):
        return json.dumps({"status": "error", "message": f"Unexpected type: {type(messages).__name__}"})

    docs = []
    parse_errors = 0
    for msg in messages:
        if isinstance(msg, str):
            try:
                doc = json.loads(msg)
            except Exception:
                parse_errors += 1
                continue
        elif isinstance(msg, dict):
            doc = msg
        else:
            parse_errors += 1
            continue

        # Compute sentiment and write to ES
        text = doc.get("text", "")
        sent_score, sent_label, sent_subj, sent_chars = _analyse_sentiment(text)
        doc["sentiment"] = sent_score
        doc["sentiment_label"] = sent_label
        doc["subjectivity"] = sent_subj
        doc["sentiment_text_chars"] = sent_chars
        doc["processed_at"] = datetime.now(timezone.utc).isoformat()
        docs.append(doc)

    if docs:
        result = es_bulk(docs)
        if "error" in result:
            return json.dumps({"status": "error", "message": str(result["error"])[:500]})
        errors = sum(1 for i in result.get("items", []) if "error" in i.get("index", {}))
        return json.dumps({"status": "ok", "count": len(docs), "errors": errors, "parse_errors": parse_errors})

    return json.dumps({"status": "ok", "count": 0, "parse_errors": parse_errors})
