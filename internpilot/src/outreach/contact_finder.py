"""
Recruiter contact discovery using Hunter.io API.
Requires HUNTER_API_KEY set in config/.env.
Free tier: 25 searches/month. https://hunter.io/api-documentation
"""
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

HUNTER_BASE_URL = "https://api.hunter.io/v2"


def get_hunter_api_key() -> Optional[str]:
    return os.getenv("HUNTER_API_KEY", "").strip() or None


def find_company_domain(company_name: str) -> Optional[str]:
    """Resolve a company name to its primary email domain via Hunter.io."""
    api_key = get_hunter_api_key()
    if not api_key:
        return None
    try:
        import requests
        resp = requests.get(
            f"{HUNTER_BASE_URL}/domain-search",
            params={"company": company_name, "limit": 1, "api_key": api_key},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("data", {}).get("domain")
        logger.warning("Hunter.io domain lookup returned %d for %s", resp.status_code, company_name)
    except Exception as exc:
        logger.debug("Domain lookup failed for %s: %s", company_name, exc)
    return None


def find_recruiter_contacts(
    company: str,
    domain: Optional[str] = None,
    limit: int = 5,
) -> list[dict]:
    """
    Find HR/recruiting contacts at a company using Hunter.io.

    Args:
        company: Company name.
        domain: Known email domain (e.g. "jpmorgan.com"). Auto-resolved if None.
        limit: Max contacts to return.

    Returns:
        List of dicts with keys: name, email, title, confidence, company.
    """
    api_key = get_hunter_api_key()
    if not api_key:
        logger.info("HUNTER_API_KEY not set — skipping contact discovery.")
        return []

    if not domain:
        domain = find_company_domain(company)
    if not domain:
        logger.info("Could not resolve domain for '%s'", company)
        return []

    try:
        import requests
        resp = requests.get(
            f"{HUNTER_BASE_URL}/domain-search",
            params={
                "domain": domain,
                "department": "human_resources",
                "limit": limit,
                "api_key": api_key,
            },
            timeout=10,
        )
        resp.raise_for_status()
        emails = resp.json().get("data", {}).get("emails", [])

        contacts = []
        for e in emails:
            first = e.get("first_name", "")
            last = e.get("last_name", "")
            contacts.append({
                "name": f"{first} {last}".strip() or "Unknown",
                "email": e.get("value", ""),
                "title": e.get("position", ""),
                "confidence": e.get("confidence", 0),
                "company": company,
                "domain": domain,
            })

        logger.info("Found %d contacts at %s (%s)", len(contacts), company, domain)
        time.sleep(1)  # Polite rate limiting
        return contacts

    except Exception as exc:
        logger.error("Hunter.io lookup failed for %s: %s", company, exc)
        return []
