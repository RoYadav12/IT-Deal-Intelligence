"""
Heuristic (no-LLM) deal extraction from search titles/snippets and page text.

Used when only a Serper API key is provided. Quality is lower than Claude/OpenAI
but the whole pipeline runs with a single key.

Patterns cover common M&A / outsourcing / managed-services / cloud deal phrasing.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Shared token helpers
# ---------------------------------------------------------------------------

_UNKNOWN = {"", "unknown", "n/a", "na", "none", "null", "not available",
            "not specified", "not mentioned", "not disclosed"}

_VALUE_RE = re.compile(
    r"(?:US\s*)?\$\s*([\d,.]+)\s*(billion|bn|million|mn|m|b|k)?|"
    r"([\d,.]+)\s*(billion|bn|million|mn)\s*(?:dollars|usd)?|"
    r"€\s*([\d,.]+)\s*(billion|bn|million|mn|m|b)?|"
    r"£\s*([\d,.]+)\s*(billion|bn|million|mn|m|b)?",
    re.I,
)

_DATE_ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_DATE_MDY = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b",
    re.I,
)
_DATE_DMY = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+(20\d{2})\b",
    re.I,
)

_MONTH = {
    "jan": "01", "january": "01", "feb": "02", "february": "02",
    "mar": "03", "march": "03", "apr": "04", "april": "04", "may": "05",
    "jun": "06", "june": "06", "jul": "07", "july": "07", "aug": "08",
    "august": "08", "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10", "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}

# Company-name fragment: starts with a capital letter (case-sensitive).
# No period inside tokens so we don't spill across sentence boundaries.
_CO = r"[A-Z][\w&'\-]{1,30}(?:\s+[A-Z][\w&'\-]{1,30}){0,4}"

# Acquisition / merger patterns: Group1 = buyer/acquirer, Group2 = target
_ACQUIRE_PATTERNS = [
    re.compile(
        rf"({_CO})\s+"
        r"(?:to\s+)?(?:acquire|acquires|acquiring|buy|buys|buying|purchase|purchases|"
        r"take\s+over|takes\s+over)\s+"
        rf"({_CO})",
    ),
    re.compile(
        rf"({_CO})\s+"
        r"(?:to\s+)?(?:merge\s+with|merges\s+with|merging\s+with)\s+"
        rf"({_CO})",
    ),
    re.compile(
        rf"({_CO})\s+"
        r"(?:completes?\s+)?(?:acquisition|purchase)\s+of\s+"
        rf"({_CO})",
    ),
]

# Contract / services: Group1 = customer, Group2 = vendor (or reverse)
_CONTRACT_PATTERNS = [
    re.compile(
        rf"({_CO})\s+"
        r"(?:awards?|selects?|chooses?|picks?|signs?|awarded|signed)\s+"
        r"(?:a\s+|an\s+|the\s+)?"
        r"(?:(?:multi[\-\s]?year|major|new|strategic|landmark)\s+)?"
        r"(?:IT\s+|cloud\s+|managed\s+services?\s+|outsourcing\s+)?"
        r"(?:contract|deal|agreement)?\s*"
        r"(?:to|with|for|from)?\s*"
        rf"({_CO})",
    ),
    re.compile(
        rf"({_CO})\s+"
        r"(?:wins?|lands?|secures?|bags?)\s+"
        r"(?:(?:a|an|the)\s+)?"
        r"(?:[\w\-]+\s+){0,4}?"
        r"(?:contract|deal|agreement|mandate)\s+"
        r"(?:from|with|for)\s+"
        r"(?:the\s+)?"
        rf"({_CO})",
    ),
    re.compile(
        rf"({_CO})\s+"
        r"(?:partners?\s+with|teams?\s+up\s+with|collaborates?\s+with)\s+"
        rf"({_CO})",
    ),
    re.compile(
        rf"({_CO})\s+"
        r"(?:to\s+)?(?:provide|deliver|supply|offer|implement)\s+"
        r".{0,50}?\s+(?:to|for)\s+"
        r"(?:the\s+)?"
        rf"({_CO})",
    ),
]

_DEAL_TYPE_KEYWORDS = [
    (r"\bacqui(?:re[ds]?|ring|sition)\b|\bbuyout\b|\btakeover\b|\bpurchase[sd]?\b", "acquisition"),
    (r"\bmergers?\b|\bmerge[sd]?\b", "merger"),
    (r"\boutsourc", "outsourcing contract"),
    (r"\bmanaged\s+services?\b|\bmsp\b", "managed services"),
    (r"\bcloud\b|\bmigration\b|\bsaas\b|\biaas\b|\bpaas\b", "cloud deal"),
    (r"\bpartner(?:ship|s)?\b|\balliance\b|\bcollaborat", "partnership"),
]

_TECH_KEYWORDS = [
    (r"\bcyber\s*secur|\bsecurity\b|\bthreat\b|\bsoc\b", "Cybersecurity"),
    (r"\bcloud\b|\bazure\b|\baws\b|\bgcp\b|\bsaas\b", "Cloud"),
    (r"\bai\b|\bmachine\s+learning\b|\bml\b|\bgenai\b|\bgenerative\s+ai\b", "AI / Machine Learning"),
    (r"\berp\b|\bsap\b|\boracle\b", "ERP"),
    (r"\bdata\s+analy|\banalytics\b|\bbi\b|\bbig\s+data\b", "Data Analytics"),
    (r"\bmanaged\s+service|\bmsp\b|\bitsm\b", "Managed Services"),
    (r"\bdigital\s+transform", "Digital Transformation"),
    (r"\bnetwork|\bsdn\b|\b5g\b", "Networking"),
    (r"\biot\b|\binternet\s+of\s+things\b", "IoT"),
]

_COUNTRY_KEYWORDS = [
    (r"\bunited\s+states\b|\bU\.?S\.?A?\.?\b|\bamerica\b", "United States"),
    (r"\bunited\s+kingdom\b|\bU\.?K\.?\b|\bbritain\b|\bengland\b", "United Kingdom"),
    (r"\bindia\b", "India"),
    (r"\bcanada\b", "Canada"),
    (r"\baustralia\b", "Australia"),
    (r"\bgermany\b|\bdeutschland\b", "Germany"),
    (r"\bfrance\b", "France"),
    (r"\bsingapore\b", "Singapore"),
    (r"\bu\.?a\.?e\.?\b|\bdubai\b|\bemirates\b", "UAE"),
    (r"\bjapan\b", "Japan"),
    (r"\bchina\b", "China"),
    (r"\bnetherlands\b|\bdutch\b", "Netherlands"),
    (r"\bireland\b", "Ireland"),
    (r"\bbrazil\b", "Brazil"),
]

_STOP_COMPANY = {
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "at", "by",
    "with", "from", "its", "their", "new", "latest", "major", "global",
    "announces", "announced", "reports", "report", "says", "said",
    "company", "companies", "group", "inc", "ltd", "llc", "plc", "corp",
    "corporation", "limited", "technologies", "technology", "services",
    "solutions", "systems", "software", "digital", "data", "cloud",
    "it", "tech", "deal", "contract", "agreement", "partnership",
}


def _clean(value: Any) -> str:
    if value is None:
        return "Unknown"
    text = str(value).strip()
    if text.lower() in _UNKNOWN:
        return "Unknown"
    text = re.sub(r"[\s,;:.\-–—]+$", "", text).strip()
    return text or "Unknown"


def _looks_like_company(name: str) -> bool:
    name = name.strip()
    if len(name) < 2 or len(name) > 60:
        return False
    words = name.split()
    if not words:
        return False
    if not words[0][0].isupper():
        return False
    if re.search(r"[.!?]", name):
        return False
    if len(words) == 1 and words[0].lower() in _STOP_COMPANY:
        return False
    function_words = {
        "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "at",
        "by", "with", "from", "its", "their", "new", "latest", "major", "global",
    }
    if all(w.lower() in function_words for w in words):
        return False
    return True


def _detect_deal_type(text: str) -> str:
    low = text.lower()
    for pattern, label in _DEAL_TYPE_KEYWORDS:
        if re.search(pattern, low):
            return label
    return "other"


def _detect_technology(text: str) -> str:
    low = text.lower()
    for pattern, label in _TECH_KEYWORDS:
        if re.search(pattern, low):
            return label
    return "Unknown"


def _detect_country(text: str) -> str:
    for pattern, label in _COUNTRY_KEYWORDS:
        if re.search(pattern, text, re.I):
            return label
    return "Unknown"


def _extract_value(text: str) -> str:
    m = _VALUE_RE.search(text)
    if not m:
        return "Unknown"
    raw = m.group(0).strip()
    raw = re.sub(r"\s+", " ", raw)
    return raw


def _extract_date(text: str, fallback: str = "") -> str:
    m = _DATE_ISO.search(text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = _DATE_MDY.search(text)
    if m:
        month = _MONTH.get(m.group(1).lower()[:3], "01")
        day = int(m.group(2))
        year = m.group(3)
        return f"{year}-{month}-{day:02d}"
    m = _DATE_DMY.search(text)
    if m:
        day = int(m.group(1))
        month = _MONTH.get(m.group(2).lower()[:3], "01")
        year = m.group(3)
        return f"{year}-{month}-{day:02d}"
    return _clean(fallback) if fallback else "Unknown"


def _pick_parties(text: str, deal_type: str) -> tuple[str, str]:
    """Return (customer/buyer, vendor/target)."""
    for pat in _ACQUIRE_PATTERNS:
        m = pat.search(text)
        if m:
            buyer, target = _clean(m.group(1)), _clean(m.group(2))
            if _looks_like_company(buyer) and _looks_like_company(target):
                return buyer, target

    for pat in _CONTRACT_PATTERNS:
        m = pat.search(text)
        if m:
            a, b = _clean(m.group(1)), _clean(m.group(2))
            if not (_looks_like_company(a) and _looks_like_company(b)):
                continue
            low = m.group(0).lower()
            if any(w in low for w in ("wins", "lands", "secures", "bags")):
                return b, a  # customer, vendor
            if any(w in low for w in ("provide", "deliver", "supply", "offer", "implement")):
                return b, a
            return a, b

    return "Unknown", "Unknown"


def _summary_from(title: str, snippet: str, max_len: int = 220) -> str:
    parts = [p for p in (title.strip(), snippet.strip()) if p]
    text = " — ".join(parts) if parts else "Unknown"
    if len(text) > max_len:
        text = text[: max_len - 1].rsplit(" ", 1)[0] + "…"
    return text or "Unknown"


def _confidence(customer: str, vendor: str, deal_type: str, value: str) -> str:
    known = sum(1 for v in (customer, vendor) if v != "Unknown")
    if known == 2 and deal_type not in ("other", "Unknown"):
        return "Medium" if value == "Unknown" else "High"
    if known >= 1:
        return "Low"
    return "Low"


def structure_search_result(item: dict) -> dict:
    """Turn one Serper organic/news result into a raw deal dict (LLM-shaped)."""
    title = item.get("title") or ""
    snippet = item.get("snippet") or ""
    link = item.get("link") or ""
    serper_date = item.get("date") or ""
    combined = f"{title}. {snippet}"

    low = combined.lower()
    if any(skip in low for skip in (
        "job opening", "we are hiring", "career", "salary", "internship",
        "how to", "what is", "top 10", "best of", "list of",
    )):
        return {}

    deal_type = _detect_deal_type(combined)
    customer, vendor = _pick_parties(combined, deal_type)
    value = _extract_value(combined)
    date = _extract_date(combined, fallback=serper_date)
    tech = _detect_technology(combined)
    country = _detect_country(combined)
    summary = _summary_from(title, snippet)
    conf = _confidence(customer, vendor, deal_type, value)

    if customer == "Unknown" and vendor == "Unknown" and deal_type == "other":
        if not re.search(
            r"\b(deal|contract|acquisition|merger|outsourc|managed\s+service|"
            r"partnership|agreement|awarded|signed)\b",
            low,
        ):
            return {}

    return {
        "customer": customer,
        "customer_website": "Unknown",
        "vendor": vendor,
        "vendor_website": "Unknown",
        "deal_type": deal_type,
        "deal_value": value,
        "country": country,
        "technology": tech,
        "date": date,
        "summary": summary,
        "confidence": conf,
        "customer_industry": "Unknown",
        "vendor_industry": "Unknown",
        "secondary_market": "Unknown",
        "source_url": link,
    }


def structure_results(results: list[dict]) -> list[dict]:
    """Heuristic equivalent of AI structure_results for a list of search hits."""
    deals = []
    seen_urls = set()
    for item in results:
        link = (item.get("link") or "").strip().rstrip("/").lower()
        if not link or link in seen_urls:
            continue
        deal = structure_search_result(item)
        if deal:
            deals.append(deal)
            seen_urls.add(link)
    return deals


def extract_from_article(article_text: str, url: str = "", title_hint: str = "") -> dict:
    """Heuristic extraction from full page text (RSS / manual URL path)."""
    head = (title_hint + "\n" + (article_text or ""))[:6000]
    deal_type = _detect_deal_type(head)
    customer, vendor = _pick_parties(head, deal_type)
    value = _extract_value(head)
    date = _extract_date(head)
    tech = _detect_technology(head)
    country = _detect_country(head)
    summary_src = head.replace("\n", " ").strip()
    summary = summary_src[:220].rsplit(" ", 1)[0] + ("…" if len(summary_src) > 220 else "")
    conf = _confidence(customer, vendor, deal_type, value)

    return {
        "customer": customer,
        "customer_website": "Unknown",
        "vendor": vendor,
        "vendor_website": "Unknown",
        "deal_type": deal_type,
        "deal_value": value,
        "country": country,
        "technology": tech,
        "date": date,
        "summary": summary or "Unknown",
        "confidence": conf,
        "customer_industry": "Unknown",
        "vendor_industry": "Unknown",
        "secondary_market": "Unknown",
    }
