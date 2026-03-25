"""
Workday portal job scraper.
Uses Browser Use to navigate Workday career portals and extract job listings.
"""
import logging
import time
from pathlib import Path
from typing import Optional

from ..tracker.database import Database

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path(__file__).resolve().parents[2] / "outputs" / "screenshots"


async def scrape_workday_portal(
    employer: dict,
    db: Database,
    dry_run: bool = False,
) -> int:
    """
    Scrape a single Workday portal for matching job listings.

    Args:
        employer: Dict from employers.yaml (name, workday_url, keywords).
        db: Database instance.
        dry_run: If True, do not save to DB.

    Returns:
        Number of new jobs found.
    """
    try:
        from browser_use import Agent
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        logger.error(
            "browser-use or langchain-anthropic is not installed. "
            "Run: pip install browser-use langchain-anthropic"
        )
        raise

    from ..utils.config_loader import get_anthropic_api_key

    name = employer.get("name", "Unknown")
    workday_url = employer.get("workday_url", "")
    keywords = employer.get("keywords", [])

    if not workday_url or "[FILL IN]" in workday_url:
        logger.warning("Skipping %s: workday_url not configured", name)
        return 0

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        api_key=get_anthropic_api_key(),
        timeout=120,
    )

    keyword_str = ", ".join(keywords)
    task = (
        f"Go to the Workday careers portal at {workday_url}. "
        f"Search for internship positions matching these keywords: {keyword_str}. "
        f"For each matching job listing, extract: job title, job URL, location, and a brief description. "
        f"Return results as a JSON array of objects with keys: title, url, location, description."
    )

    try:
        agent = Agent(task=task, llm=llm)
        result = await agent.run()

        # Parse result
        import json
        result_text = str(result)

        # Try to extract JSON from the result
        start = result_text.find("[")
        end = result_text.rfind("]") + 1
        if start >= 0 and end > start:
            jobs_data = json.loads(result_text[start:end])
        else:
            logger.warning("Could not parse job listings from Workday result for %s", name)
            return 0

        new_count = 0
        for job in jobs_data:
            job_url = job.get("url", "").strip()
            job_title = job.get("title", "Unknown").strip()
            location = job.get("location", "").strip()
            description = job.get("description", "").strip()

            if not job_url:
                continue

            if not dry_run:
                new_id = db.insert_job(
                    url=job_url,
                    title=job_title,
                    company=name,
                    location=location,
                    description=description,
                    source="workday",
                    workday_portal=workday_url,
                )
                if new_id is not None:
                    new_count += 1
            else:
                logger.info("[DRY RUN] Would save: %s at %s", job_title, name)
                new_count += 1

        logger.info("Workday scrape for %s: %d new jobs", name, new_count)
        return new_count

    except Exception as exc:
        logger.error("Workday scrape failed for %s: %s", name, exc)
        return 0


async def scrape_all_workday_portals(
    employers: list[dict],
    db: Database,
    dry_run: bool = False,
) -> int:
    """Scrape all configured Workday portals."""
    total = 0
    for employer in employers:
        count = await scrape_workday_portal(employer, db, dry_run=dry_run)
        total += count
        time.sleep(3)  # Polite delay between portals
    return total
