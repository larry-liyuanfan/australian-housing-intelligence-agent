# COMP90024 Team 12
# Public attribution: COMP90024 Team 12; member identities removed from this portfolio copy.

# Housing sentiment analysis — domain lexicon (65%) + TextBlob (35%) hybrid.
# Used by GDELT harvester, YouTube ingest, and bulk sentiment recompute.
from __future__ import annotations
import math, re
from typing import Any, Dict

try:
    from textblob import TextBlob
except Exception:
    TextBlob = None

# --- Housing-specific sentiment lexicon ---

NEGATIVE_PHRASES = {
    "rental crisis": -0.80, "housing crisis": -0.80, "cost of living": -0.45,
    "rent increase": -0.55, "rent hikes": -0.60, "rising rents": -0.55,
    "rental stress": -0.75, "housing stress": -0.75, "mortgage stress": -0.65,
    "under pressure": -0.55, "priced out": -0.75, "housing shortage": -0.65,
    "rental shortage": -0.65, "homelessness": -0.80, "eviction": -0.70,
    "evicted": -0.70, "rent arrears": -0.65, "unaffordable housing": -0.80,
    "unaffordable rent": -0.80, "housing insecurity": -0.75,
    "mould rental": -0.55, "unsafe housing": -0.75, "social housing waitlist": -0.55,
    "can't afford": -0.70, "cannot afford": -0.70, "rent burden": -0.65,
    "rental affordability": -0.55, "skyrocketing rent": -0.80, "soaring rent": -0.75,
    "rent gouging": -0.75, "no grounds eviction": -0.80, "forced out": -0.70,
    "rental squeeze": -0.70, "housing squeeze": -0.70,
    "tent city": -0.85, "sleeping rough": -0.80, "couch surfing": -0.60,
    "rent bidding": -0.65, "overcrowded housing": -0.70, "slum landlord": -0.80,
    "rental scam": -0.75, "housing waitlist": -0.60, "dodgy landlord": -0.70,
    "mortgage cliff": -0.70, "rate rise pain": -0.60,
    "at all time low": -0.70, "all time low": -0.65, "record low": -0.60,
    "not enough": -0.45, "can not afford": -0.70, "could not afford": -0.65,
    "struggling to pay": -0.75, "struggling to afford": -0.70,
    "rent burdened": -0.70, "rent stressed": -0.70,
    "living in a car": -0.80, "living on the street": -0.85,
    "no home": -0.80, "without a home": -0.80,
    "losing their home": -0.85, "lose their home": -0.80,
    "nowhere to live": -0.85, "nowhere to go": -0.75,
    "forced to move": -0.70, "kicked out": -0.70,
}

POSITIVE_PHRASES = {
    "housing support": 0.45, "rent relief": 0.60, "rental relief": 0.60,
    "affordable housing": 0.45, "more secure": 0.45, "feel more secure": 0.55,
    "new housing supply": 0.40, "increase housing supply": 0.45,
    "social housing investment": 0.45, "tenant support": 0.45,
    "government support": 0.35, "better protection": 0.45,
    "first home buyer": 0.50, "first home owners": 0.55, "home ownership": 0.45,
    "build to rent": 0.45, "key worker housing": 0.50, "community land trust": 0.55,
    "cooperative housing": 0.50, "renters rights": 0.50, "tenant rights": 0.50,
    "housing guarantee": 0.55, "shared equity": 0.40, "stamp duty relief": 0.45,
    "housing solution": 0.40, "rental reform": 0.40,
    "better renting": 0.45, "fair renting": 0.50, "housing justice": 0.45,
}

NEGATIVE_WORDS = {
    "crisis": -0.65, "worse": -0.65, "worst": -0.75, "pressure": -0.35,
    "stress": -0.55, "stressed": -0.55, "unaffordable": -0.75, "eviction": -0.70,
    "evicted": -0.70, "homeless": -0.75, "homelessness": -0.80, "shortage": -0.55,
    "insecure": -0.55, "insecurity": -0.55, "mould": -0.40, "unsafe": -0.65,
    "arrears": -0.50, "surge": -0.35, "hike": -0.45, "hikes": -0.45,
    "burden": -0.45, "struggling": -0.55, "struggle": -0.50, "vulnerable": -0.45,
    "uninhabitable": -0.80, "dilapidated": -0.65, "derelict": -0.60,
    "overcrowded": -0.65, "substandard": -0.60, "infestation": -0.55,
    "desperate": -0.60, "hopeless": -0.65, "traumatic": -0.65,
    "devastating": -0.65, "exploitation": -0.65, "exploited": -0.60,
    "unlivable": -0.75, "condemned": -0.60, "squeeze": -0.50, "squeezed": -0.55,
    "skyrocketing": -0.70, "skyrocket": -0.65, "soaring": -0.55,
    "spiralling": -0.60, "crunch": -0.50, "plummeting": -0.55,
    "collapsing": -0.70, "unsustainable": -0.60, "dire": -0.70,
    "catastrophic": -0.75, "broken": -0.50, "failing": -0.55,
    "worsening": -0.60, "plight": -0.55, "distress": -0.60,
    "dispossessed": -0.70, "displaced": -0.55, "gentrification": -0.45,
    "greed": -0.55, "profiteering": -0.60, "hoarding": -0.50,
    "abandoned": -0.55, "foreclosure": -0.70, "foreclosed": -0.70,
    "delinquent": -0.50, "overvalued": -0.45,
    "low": -0.40, "lows": -0.40, "increase": -0.30, "increases": -0.30,
    "increasing": -0.35, "hiked": -0.50, "hiking": -0.45,
    "worsen": -0.55, "tight": -0.40, "tightening": -0.45,
    "shortfall": -0.55, "insufficient": -0.55,
    "unmet": -0.50, "backlog": -0.45, "waitlist": -0.55, "waitlists": -0.55,
    "deterioration": -0.55, "deteriorating": -0.55,
    "deprivation": -0.60, "precarious": -0.60,
    "exclusion": -0.50, "excluded": -0.55,
    "unfair": -0.50, "discrimination": -0.55,
    "bidding": -0.45, "overbidding": -0.55,
    "exodus": -0.50, "fleeing": -0.50,
    "squeezing": -0.55,
}

POSITIVE_WORDS = {
    "improved": 0.50, "improve": 0.45, "secure": 0.35, "relief": 0.55,
    "support": 0.35, "affordable": 0.35, "stability": 0.35, "protected": 0.40,
    "protection": 0.35, "investment": 0.25, "supply": 0.20, "recovery": 0.35,
    "safe": 0.30, "stable": 0.35,
    "ownership": 0.30, "buyers": 0.25, "homeowners": 0.25,
    "initiative": 0.25, "funding": 0.20, "commitment": 0.25,
    "opportunity": 0.20, "thriving": 0.45, "prosperity": 0.35,
    "hopeful": 0.40, "welcomed": 0.25, "progress": 0.25,
    "improvement": 0.30, "improvements": 0.30,
    "fairer": 0.25, "sustainable": 0.30, "assistance": 0.25,
    "cooperative": 0.30, "inclusive": 0.30, "accessible": 0.30,
    "revitalised": 0.45, "regenerated": 0.40, "transforming": 0.35,
    "empowering": 0.35, "celebrating": 0.35,
}

# Words indicating housing context — used for bias
HOUSING_CONTEXT = {
    "rent", "rental", "renter", "renters", "renting", "rented",
    "tenant", "tenants", "tenancy", "landlord", "landlords",
    "housing", "apartment", "apartments", "flat", "flats",
    "mortgage", "mortgages", "property", "properties",
    "eviction", "evictions", "evict", "evicted",
    "homeless", "homelessness", "shelter", "shelters",
    "lease", "leasing", "bond", "bonds", "accommodation",
    "homeownership", "homebuyer", "homebuyers",
    "lodging", "boarding", "sublet", "roommate", "flatmate",
    "dwelling", "dwellings", "realestate", "foreclosure", "foreclosed",
}

# Clean text: strip URLs, mentions, special chars
def clean_text(text: str) -> str:
    if not text: return ""
    text = str(text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"@\w+", " ", text)
    text = re.sub(r"#", "", text)
    text = re.sub(r"[^0-9A-Za-z\s.,!?$%'-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))

def label_sentiment(score: float) -> str:
    if score >= 0.04: return "positive"
    if score <= -0.04: return "negative"
    return "neutral"

# TextBlob NLP polarity
def textblob_score(text: str) -> tuple[float, float]:
    if TextBlob is None: return 0.0, 0.0
    try:
        result = TextBlob(text).sentiment
        return float(result.polarity), float(result.subjectivity)
    except Exception:
        return 0.0, 0.0

# Domain lexicon: match phrases then words, log-normalise
def domain_lexicon_score(text: str) -> float:
    lower_text = text.lower()
    score = 0.0
    for phrase, weight in NEGATIVE_PHRASES.items():
        if phrase in lower_text: score += weight
    for phrase, weight in POSITIVE_PHRASES.items():
        if phrase in lower_text: score += weight
    words = re.findall(r"[a-zA-Z']+", lower_text)
    for word in words:
        if word in NEGATIVE_WORDS: score += NEGATIVE_WORDS[word]
        elif word in POSITIVE_WORDS: score += POSITIVE_WORDS[word]
    if not words: return 0.0
    # Apply housing context bias before normalization
    hits = len(set(words) & HOUSING_CONTEXT)
    if hits >= 5: score -= 0.15
    elif hits >= 3: score -= 0.10
    elif hits >= 1: score -= 0.06
    normalised = score / max(1.0, math.log(len(words) + 1))
    return clamp(normalised)

# Main: combined sentiment (domain 65% + TextBlob 35%)
def analyse_sentiment(text: str) -> Dict[str, Any]:
    cleaned = clean_text(text)
    if not cleaned:
        return {"sentiment": 0.0, "sentiment_label": "neutral", "subjectivity": 0.0,
                "sentiment_text_chars": 0}

    tb_polarity, tb_subjectivity = textblob_score(cleaned)
    domain_score = domain_lexicon_score(cleaned)

    if abs(domain_score) > 0:
        final_score = (0.35 * tb_polarity) + (0.65 * domain_score)
    else:
        final_score = (0.65 * tb_polarity) + (0.35 * domain_score)

    final_score = clamp(final_score)
    subjectivity = max(tb_subjectivity,
                       min(1.0, abs(domain_score) + 0.15 if abs(domain_score) > 0 else 0.0))

    return {
        "sentiment": round(final_score, 4),
        "sentiment_label": label_sentiment(final_score),
        "subjectivity": round(subjectivity, 4),
        "sentiment_text_chars": len(cleaned),
    }
