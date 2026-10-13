"""
Central configuration for the IT Deal Intelligence platform.

API keys are NOT stored here. They are typed into the Streamlit sidebar at
run time and carried around in a small `Credentials` object, so one visitor's
keys can never leak into another visitor's session. For local/headless runs
(run_pipeline.py) keys can also come from environment variables or a .env file.
"""

import os
from dataclasses import dataclass

try:
    # Optional convenience: load a local .env file if python-dotenv exists.
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def clean_key(value):
    """Tolerate the usual copy/paste damage (stray whitespace or wrapping
    quotes), which otherwise shows up as a baffling 401 from the API."""
    return str(value or "").strip().strip("\"'").strip()


def _env(name, default=""):
    return clean_key(os.environ.get(name, default))


DB_PATH = _env("IT_DEALS_DB_PATH", "it_deals.db")

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
SERPER_SEARCH_URL = "https://google.serper.dev/search"
SERPER_NEWS_URL = "https://google.serper.dev/news"
SERPER_SCRAPE_URL = "https://scrape.serper.dev"
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# ---------------------------------------------------------------------------
# AI providers (they read the search results / articles and structure them)
# ---------------------------------------------------------------------------
LLM_PROVIDERS = {
    "Claude (Anthropic)": {
        "id": "anthropic",
        "short": "Anthropic",
        "default_model": "claude-sonnet-4-6",
        "key_env": "ANTHROPIC_API_KEY",
        "placeholder": "sk-ant-...",
        "help": "Create one at console.anthropic.com -> API Keys.",
    },
    "OpenAI (GPT)": {
        "id": "openai",
        "short": "OpenAI",
        "default_model": "gpt-4.1-mini",
        "key_env": "OPENAI_API_KEY",
        "placeholder": "sk-...",
        "help": "Create one at platform.openai.com -> API keys.",
    },
}
PROVIDER_BY_ID = {p["id"]: p for p in LLM_PROVIDERS.values()}


def _looks_invalid(key):
    return (not key.isascii()) or any(ch.isspace() for ch in key)


@dataclass(frozen=True)
class Credentials:
    """Everything needed to call the outside services for one session.

    Only the Serper key is required. An LLM key is optional: when present the
    AI structures results; when absent a built-in heuristic extractor is used
    so the whole app runs on a single API key.
    """

    serper_key: str = ""
    llm_provider: str = "anthropic"      # "anthropic" or "openai"
    llm_key: str = ""
    llm_model: str = ""                   # blank -> provider default

    @property
    def model(self):
        return self.llm_model or PROVIDER_BY_ID[self.llm_provider]["default_model"]

    @property
    def llm_label(self):
        return PROVIDER_BY_ID[self.llm_provider]["short"]

    @property
    def has_llm(self) -> bool:
        """True when a usable LLM key was supplied."""
        return bool(self.llm_key) and not _looks_invalid(self.llm_key)

    def problems(self):
        """Human-readable list of what is missing / malformed (empty = OK).

        Only Serper is mandatory. A missing/invalid LLM key is not an error –
        the app falls back to heuristic extraction.
        """
        issues = []
        if not self.serper_key:
            issues.append("Serper API key is missing")
        elif _looks_invalid(self.serper_key):
            issues.append("Serper API key contains spaces or odd characters - re-copy it")
        return issues

    def llm_problems(self):
        """Issues specific to the optional LLM key (empty = OK or unused)."""
        issues = []
        if self.llm_key and _looks_invalid(self.llm_key):
            issues.append(
                f"{self.llm_label} API key contains spaces or odd characters - re-copy it"
            )
        return issues


def credentials_from_env():
    """Build Credentials from environment variables / .env (headless runs)."""
    provider = _env("LLM_PROVIDER").lower()
    if provider not in PROVIDER_BY_ID:
        provider = "anthropic" if _env("ANTHROPIC_API_KEY") or not _env("OPENAI_API_KEY") else "openai"
    return Credentials(
        serper_key=_env("SERPER_API_KEY"),
        llm_provider=provider,
        llm_key=_env(PROVIDER_BY_ID[provider]["key_env"]),
        llm_model=_env("LLM_MODEL"),
    )


# ---------------------------------------------------------------------------
# RSS ingestion
# ---------------------------------------------------------------------------
RSS_FEEDS = [
    "https://www.digitalhealth.net/feed/",
    "https://www.contractsfinder.service.gov.uk/Notice/rss",
    "https://www.gov.uk/contracts-finder/feeds/all.rss",
]

# A strict per-feed timeout so one slow feed can't stall the whole run.
FEED_FETCH_TIMEOUT_SECONDS = 15
MAX_FEED_WORKERS = 5

# ---------------------------------------------------------------------------
# HTTP behaviour
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT_SECONDS = 90
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 3
RATE_LIMIT_SLEEP_SECONDS = 1
ARTICLE_TEXT_MAX_CHARS = 12000

# Cost guard: the most Pending URLs one "Refresh" run will extract. Each one
# costs a Serper scrape plus an AI call. Anything beyond the cap stays Pending
# and is picked up by the next run. Set to 0 for "no limit".
MAX_PENDING_PER_RUN = 50

# ---------------------------------------------------------------------------
# WEB DISCOVERY (Serper Google search, with a real date filter)
# ---------------------------------------------------------------------------

# Same "tenure" choices as the IT Deal Finder app.
TENURE_OPTIONS = {
    "Past week": 7,
    "Past month": 30,
    "Past 3 months": 90,
    "Past 6 months": 182,
    "Past year": 365,
    "Past 2 years": 730,
}
CUSTOM_RANGE_LABEL = "Custom range"
DEFAULT_TENURE = "Past month"

# Search "angles" - each one is a separate Serper search per click.
# IMPORTANT: Serper FREE accounts reject search operators (OR, quotes,
# brackets, minus signs) with "Query pattern not allowed for free accounts".
# So every query below is plain words only. Each one pairs one theme from your
# keyword list with a deal-signal word (contract / agreement / awarded ...).
# Edit freely: one line = one Serper search.
DISCOVERY_QUERIES = [
    # Cloud
    "cloud migration contract awarded",
    "cloud transformation agreement signed",
    "cloud modernization multi-year contract",
    "cloud managed services agreement",
    "AWS strategic collaboration agreement enterprise",
    "Microsoft Azure multi-year agreement enterprise",
    "Google Cloud multi-year contract enterprise",
    "hybrid cloud multi-cloud contract awarded",
    "SaaS PaaS IaaS agreement signed enterprise",
    "data center modernization migration contract",
    # AI
    "generative AI implementation contract signed",
    "AI integration partnership commercial agreement",
    "large language models enterprise deployment agreement",
    "AI infrastructure GPU contract agreement",
    "AI automation enterprise contract awarded",
    # Transformation / modernization
    "digital transformation contract awarded",
    "legacy system modernization contract",
    "application modernization contract awarded",
    "IT modernization contract awarded",
    # Outsourcing / managed services
    "IT outsourcing contract signed",
    "IT outsourcing renewal multi-year",
    "managed IT services agreement signed",
    "managed infrastructure services contract awarded",
    "application development and maintenance contract awarded",
    "application management services contract signed",
    "service desk outsourcing contract",
    "IT services contract renewal extension",
    # Security
    "cybersecurity contract awarded",
    "managed security services agreement signed",
    "zero trust security implementation contract",
    # Data
    "data analytics contract awarded",
    "data modernization migration contract",
    "data warehouse lakehouse implementation contract",
    # Enterprise software
    "ERP implementation contract awarded",
    "SAP S/4HANA implementation contract signed",
    "Salesforce ServiceNow implementation contract",
    "software licensing agreement enterprise signed",
    # Engineering / automation
    "software development contract awarded",
    "DevOps platform engineering contract",
    "systems integration contract awarded",
    "robotic process automation intelligent automation contract",
    # Network / industry
    "network modernization SD-WAN contract",
    "5G implementation Industry 4.0 industrial IoT contract",
    # Contract-language catch-alls
    "master services agreement IT services signed",
    "IT contract award multi-year technology",
    "technology partnership commercial agreement signed",
    "IT vendor selected technology procurement contract",
    # Verticals
    "healthcare IT modernization contract",
    "government IT modernization contract awarded",
    "fintech banking technology implementation agreement",
    "telecom IT transformation contract",
    "retail technology transformation contract",
]

# The angles ticked by default in the app (keeps a one-click run cheap:
# 12 Serper searches). Tick more in "Search settings" for wider coverage.
DEFAULT_DISCOVERY_QUERIES = [
    "cloud migration contract awarded",
    "cloud managed services agreement",
    "generative AI implementation contract signed",
    "digital transformation contract awarded",
    "IT outsourcing contract signed",
    "managed IT services agreement signed",
    "application development and maintenance contract awarded",
    "cybersecurity contract awarded",
    "data analytics contract awarded",
    "ERP implementation contract awarded",
    "master services agreement IT services signed",
    "IT contract award multi-year technology",
]

# Search operators can't be used on free Serper accounts, so Google can't drop
# M&A noise up front. Exclusions are enforced afterwards instead: by the AI
# prompts, the heuristic extractor, and the Python safety net below.
QUERY_EXCLUSIONS = ""

# Python safety net: a deal whose type/summary matches these AND which has no
# contract-type signal is dropped before saving.
EXCLUDED_DEAL_TERMS = [
    "merger", "acquisition", "m&a", "takeover", "buyout", "divestiture",
    "equity investment", "venture capital", "private equity", "stock purchase",
    "share transfer", "corporate restructuring", "funding round", "fundraising",
    "joint venture",
]
CONTRACT_SIGNAL_TERMS = [
    "contract", "agreement", "msa", "sow", "awarded", "renewal", "extension",
    "outsourc", "managed service", "implementation", "licens", "selected",
    "selects", "signed", "deployment",
]

DISCOVERY_RESULTS_PER_QUERY = 20     # Serper "num" (10-50)
STRUCTURE_CHUNK_SIZE = 20            # search results per AI call

DISCOVERY_COUNTRY_OPTIONS = [
    "Any", "United States", "United Kingdom", "India", "Canada", "Australia",
    "Germany", "France", "Singapore", "UAE", "Japan", "Global",
]

DISCOVERY_GEOGRAPHY_OPTIONS = [
    "Any", "North America", "Europe", "Asia Pacific",
    "Middle East & Africa", "Latin America",
]

DISCOVERY_INDUSTRY_OPTIONS = [
    "Any", "Healthcare", "Banking", "Retail", "Government", "Telecom",
    "Manufacturing", "Education", "Energy", "Insurance", "Transportation",
]

DISCOVERY_TECHNOLOGY_OPTIONS = [
    "Any", "Cloud", "Cybersecurity", "AI / Machine Learning", "ERP",
    "Data Analytics", "Managed Services", "Digital Transformation",
    "Networking", "IoT",
]

DEAL_TYPES = [
    "cloud services contract", "outsourcing contract", "managed services",
    "AI / automation deal", "software / ERP implementation",
    "cybersecurity contract", "data & analytics contract",
    "digital transformation contract", "technology partnership",
    "licensing agreement", "contract renewal / extension", "other",
]
