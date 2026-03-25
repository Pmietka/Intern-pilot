"""
URL and job deduplication utilities.
"""
import hashlib
import re
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs


# ──────────────────────────────────────────────────────────────
# URL-based deduplication
# ──────────────────────────────────────────────────────────────

_STRIP_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
    "ref", "referrer", "source", "trackingId", "trk", "trkCampaign",
}


def normalize_url(url: str) -> str:
    """
    Normalize a URL for consistent deduplication:
    - Lowercase scheme and host
    - Remove common tracking parameters
    - Remove trailing slashes
    """
    if not url:
        return url
    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in qs.items() if k not in _STRIP_PARAMS}
        new_query = urlencode(sorted(filtered.items()), doseq=True)
        return urlunparse((scheme, netloc, path, "", new_query, ""))
    except Exception:
        return url


def url_hash(url: str) -> str:
    normalized = normalize_url(url)
    return hashlib.sha256(normalized.encode()).hexdigest()


def is_duplicate(url: str, seen_hashes: set[str]) -> bool:
    h = url_hash(url)
    if h in seen_hashes:
        return True
    seen_hashes.add(h)
    return False


# ──────────────────────────────────────────────────────────────
# Company + title fuzzy deduplication
# Catches the same job posted twice with different URLs
# ──────────────────────────────────────────────────────────────

_COMPANY_NOISE = re.compile(
    r"\b(llc|inc|corp|ltd|co\.?|plc|na|n\.a\.|group|holdings|services|bank|financial)\b",
    re.IGNORECASE,
)
_TITLE_YEAR = re.compile(r"\b20\d{2}\b")
_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^\w\s]")


def _normalize(text: str) -> str:
    """Lowercase, strip noise words and punctuation for fuzzy comparison."""
    text = text.lower().strip()
    text = _NON_ALNUM.sub(" ", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text


def normalize_company(company: str) -> str:
    cleaned = _COMPANY_NOISE.sub("", company)
    return _normalize(cleaned)


def normalize_title(title: str) -> str:
    # Remove year references (2025 Summer Analyst → Summer Analyst)
    cleaned = _TITLE_YEAR.sub("", title)
    return _normalize(cleaned)


def company_title_key(company: str, title: str) -> str:
    """Create a normalized composite key for company+title dedup."""
    return f"{normalize_company(company)}::{normalize_title(title)}"


def is_company_title_duplicate(company: str, title: str, seen_keys: set[str]) -> bool:
    """
    Return True if this company+title combo has been seen before.
    Adds to seen_keys if new.
    """
    key = company_title_key(company, title)
    if key in seen_keys:
        return True
    seen_keys.add(key)
    return False
