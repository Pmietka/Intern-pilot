"""
Multi-board job scraper using python-jobspy.
"""
import logging
import random
import time
from typing import Optional

from ..tracker.database import Database
from .dedup import is_duplicate, is_company_title_duplicate

logger = logging.getLogger(__name__)

JOBSPY_SITES = ["linkedin", "indeed", "glassdoor", "zip_recruiter", "google"]

SOURCE_MAP = {
    "linkedin": ["linkedin"],
    "indeed": ["indeed"],
    "glassdoor": ["glassdoor"],
    "ziprecruiter": ["zip_recruiter"],
    "google": ["google"],
    "all": JOBSPY_SITES,
}

# Retry settings
_MAX_RETRIES = 3
_RETRY_BASE_WAIT = 5  # seconds


def _scrape_with_retry(jobspy_scrape, **kwargs):
    """Call jobspy with exponential-backoff retry on failure."""
    for attempt in range(_MAX_RETRIES):
        try:
            return jobspy_scrape(**kwargs)
        except Exception as exc:
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BASE_WAIT * (2 ** attempt) + random.uniform(0, 2)
                logger.warning(
                    "Scraping attempt %d/%d failed (%s). Retrying in %.1fs...",
                    attempt + 1, _MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
            else:
                raise


def scrape_jobs(
    searches: list[dict],
    db: Database,
    source: str = "all",
    dry_run: bool = False,
) -> int:
    """
    Run all configured searches against the specified job boards.

    Args:
        searches: List of search config dicts from searches.yaml.
        db: Database instance for storage.
        source: Which board(s) to use (matches SOURCE_MAP keys).
        dry_run: If True, print what would be done without saving.

    Returns:
        Number of new jobs discovered.
    """
    try:
        from jobspy import scrape_jobs as jobspy_scrape
    except ImportError:
        logger.error("python-jobspy is not installed. Run: pip install python-jobspy")
        raise

    sites = SOURCE_MAP.get(source.lower(), JOBSPY_SITES)
    seen_url_hashes: set[str] = set()
    seen_company_titles: set[str] = set()
    total_new = 0

    for search_config in searches:
        keywords_list = search_config.get("keywords", [])
        location = search_config.get("location", "Chicago, IL")
        distance = search_config.get("distance_miles", 50)
        job_type = search_config.get("job_type", "internship")

        for keyword in keywords_list:
            logger.info("Searching: '%s' in '%s' on [%s]", keyword, location, ", ".join(sites))
            try:
                results_df = _scrape_with_retry(
                    jobspy_scrape,
                    site_name=sites,
                    search_term=keyword,
                    location=location,
                    distance=distance,
                    job_type=job_type,
                    results_wanted=25,
                    hours_old=168,  # 7 days
                    country_indeed="USA",
                    linkedin_fetch_description=True,
                )

                if results_df is None or results_df.empty:
                    logger.info("No results for '%s'", keyword)
                    _polite_delay()
                    continue

                new_count = 0
                for _, row in results_df.iterrows():
                    job_url = str(row.get("job_url", "")).strip()
                    if not job_url or job_url == "nan":
                        continue

                    # URL-based dedup (primary)
                    if is_duplicate(job_url, seen_url_hashes):
                        continue

                    job_title = str(row.get("title", "Unknown Title")).strip()
                    company = str(row.get("company", "Unknown Company")).strip()

                    # Company+title dedup (catches same job, different URL)
                    if is_company_title_duplicate(company, job_title, seen_company_titles):
                        logger.debug(
                            "Skipping likely duplicate: %s @ %s", job_title, company
                        )
                        continue

                    location_str = str(row.get("location", "")).strip()
                    description = str(row.get("description", "")).strip()
                    site_source = str(row.get("site", source)).strip()

                    if dry_run:
                        logger.info(
                            "[DRY RUN] Would save: %s at %s (%s)", job_title, company, job_url
                        )
                        new_count += 1
                        continue

                    new_id = db.insert_job(
                        url=job_url,
                        title=job_title,
                        company=company,
                        location=location_str,
                        description=description if description != "nan" else None,
                        source=site_source,
                    )
                    if new_id is not None:
                        new_count += 1

                logger.info("Search '%s': %d new jobs", keyword, new_count)
                total_new += new_count

            except Exception as exc:
                logger.error("Error scraping '%s' on %s: %s", keyword, sites, exc)

            _polite_delay()

    logger.info("Discovery complete. Total new jobs: %d", total_new)
    return total_new


def _polite_delay() -> None:
    """Random delay between requests to avoid triggering rate limits."""
    delay = random.uniform(2.5, 6.0)
    logger.debug("Polite delay: %.1fs", delay)
    time.sleep(delay)


def scrape_single_source(
    searches: list[dict],
    db: Database,
    source: str,
    dry_run: bool = False,
) -> int:
    """Scrape a single job board source."""
    return scrape_jobs(searches, db, source=source, dry_run=dry_run)
