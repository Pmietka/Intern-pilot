"""
URL deduplication utilities.
"""
import hashlib
import re
from urllib.parse import urlparse, urlunparse, urlencode, parse_qs


def normalize_url(url: str) -> str:
    """
    Normalize a URL for consistent deduplication:
    - Lowercase scheme and host
    - Remove common tracking parameters
    - Remove trailing slashes
    """
    if not url:
        return url

    # Tracking params to strip
    _STRIP_PARAMS = {
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term",
        "ref", "referrer", "source", "trackingId", "trk", "trkCampaign",
    }

    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")

        # Filter query params
        qs = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in qs.items() if k not in _STRIP_PARAMS}
        new_query = urlencode(sorted(filtered.items()), doseq=True)

        normalized = urlunparse((scheme, netloc, path, "", new_query, ""))
        return normalized
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
