"""Find the official website of a company via one Serper search.

The AI is (deliberately) not allowed to guess websites from memory, and news
articles rarely state them, so the website columns used to stay "Unknown".
This module fills them in by searching "<company> official website" and
accepting a result only when its domain actually matches the company name
(so a wrong site is never saved - "Unknown" is better than a wrong link).
"""

import re
from urllib.parse import urlparse

import config
import extraction

# Domains that are about a company, never the company's own site.
_BLOCKED = (
    "linkedin.", "facebook.", "twitter.", "x.com", "instagram.", "youtube.",
    "wikipedia.", "crunchbase.", "bloomberg.", "reuters.", "forbes.",
    "zoominfo.", "glassdoor.", "indeed.", "naukri.", "pitchbook.",
    "dnb.com", "owler.", "craft.co", "tracxn.", "yahoo.", "marketwatch.",
    "businesswire.", "prnewswire.", "globenewswire.", "medium.", "reddit.",
    "wsj.", "ft.com", "cnbc.", "techcrunch.", "gartner.", "g2.com",
    "trustpilot.", "mapquest.", "yelp.", "sec.gov", "bing.", "google.",
)
_SUFFIXES = {
    "inc", "incorporated", "ltd", "limited", "llc", "llp", "plc", "corp",
    "corporation", "co", "company", "group", "holdings", "holding", "gmbh",
    "ag", "sa", "se", "nv", "bv", "pvt", "pty", "the", "and", "of",
    "technologies", "technology", "tech", "systems", "solutions", "services",
    "global", "international", "limited.", "us", "usa", "uk", "india",
}
_UNKNOWN = {"", "unknown", "n/a", "none", "null"}
_cache = {}   # company name -> website (or "Unknown"), per process


def _tokens(name):
    words = re.findall(r"[a-z0-9]+", str(name).lower())
    core = [w for w in words if w not in _SUFFIXES]
    return core or words


def _host(url):
    host = urlparse(str(url or "")).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _matches(host, tokens):
    """The domain must contain the company's full squashed name, or (for
    multi-word names) its first word when that word is distinctive."""
    label = re.sub(r"[^a-z0-9]", "", host.split(":")[0])
    squashed = "".join(tokens)
    if squashed and squashed in label:
        return True
    return len(tokens[0]) >= 4 and tokens[0] in label


def normalize_website(value):
    """'www.acme.com/about' / 'https://Acme.com' -> 'https://acme.com'."""
    text = str(value or "").strip()
    if text.lower() in _UNKNOWN:
        return "Unknown"
    if not re.match(r"^https?://", text, re.I):
        text = "https://" + text
    host = _host(text)
    if "." not in host or " " in host:
        return "Unknown"
    return f"https://{host}"


def find_website(company, creds):
    """Return 'https://domain' for a company, or 'Unknown'."""
    company = str(company or "").strip()
    if company.lower() in _UNKNOWN:
        return "Unknown"
    key = company.lower()
    if key in _cache:
        return _cache[key]
    tokens = _tokens(company)
    result = "Unknown"
    if tokens:
        response = extraction.request_with_retries(
            "POST", config.SERPER_SEARCH_URL, service="Serper",
            headers=extraction.serper_headers(creds),
            json={"q": f"{company} official website", "num": 8},
        )
        data = response.json() if response is not None else {}
        candidates = []
        kg = (data.get("knowledgeGraph") or {}).get("website")
        if kg:
            candidates.append(kg)
        candidates += [r.get("link") for r in data.get("organic", [])]
        for link in candidates:
            host = _host(link)
            if not host or any(b in host for b in _BLOCKED):
                continue
            if _matches(host, tokens):
                result = f"https://{host}"
                break
    _cache[key] = result
    return result


def fill_websites(fields, creds):
    """Fill CustomerWebsite / VendorWebsite in a normalized deal dict.

    Never raises for ordinary failures; a bad key / no credits (FatalAPIError)
    is re-raised so the caller can stop the run.
    """
    for name_key, site_key in (("Customer", "CustomerWebsite"),
                               ("Vendor", "VendorWebsite")):
        current = normalize_website(fields.get(site_key))
        if current == "Unknown":
            try:
                current = find_website(fields.get(name_key), creds)
            except extraction.FatalAPIError:
                raise
            except Exception:
                current = "Unknown"
        fields[site_key] = current
    return fields
