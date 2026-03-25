"""
Job scoring using Claude API.
Evaluates each job against the candidate's profile and assigns a 1-10 match score.
"""
import logging
import time
from typing import Optional

import yaml

from ..tracker.database import Database
from ..tracker.models import Job
from ..utils.llm import call_claude_json

logger = logging.getLogger(__name__)

SCORING_PROMPT = """\
You are evaluating whether a job posting is a strong match for a finance undergraduate seeking internships.

CANDIDATE PROFILE:
{profile_yaml_content}

JOB POSTING:
Title: {job_title}
Company: {company}
Location: {location}
Description: {job_description}

Score this job 1 to 10 based on these weighted criteria:
- Year level match (is this for sophomores/rising juniors? or does it accept all years?): 30% weight
- Role alignment (commercial banking, corporate banking, consulting, or adjacent finance roles): 25% weight
- Location fit (Chicago area, or remote, or willing to relocate): 15% weight
- Skills match (does the candidate's experience align with requirements?): 20% weight
- Prestige and career development value: 10% weight

Respond in this exact JSON format and nothing else:
{{
  "score": <integer 1 to 10>,
  "rationale": "<2 to 3 sentences explaining the score>",
  "year_level_match": <true/false>,
  "is_internship": <true/false>,
  "role_type": "<commercial_banking|corporate_banking|investment_banking|consulting|other_finance|not_finance>"
}}
"""


def score_job(
    job: Job,
    profile: dict,
    delay: float = 2.0,
) -> tuple[int, str]:
    """
    Score a single job against the candidate profile.

    Returns:
        (score, rationale) tuple.
    """
    profile_yaml = yaml.dump(profile, default_flow_style=False, allow_unicode=True)

    description = job.description or "No description available."
    # Truncate very long descriptions to stay within token limits
    if len(description) > 4000:
        description = description[:4000] + "...[truncated]"

    prompt = SCORING_PROMPT.format(
        profile_yaml_content=profile_yaml,
        job_title=job.title,
        company=job.company,
        location=job.location or "Unknown",
        job_description=description,
    )

    try:
        result = call_claude_json(prompt, delay=delay)
        score = int(result.get("score", 5))
        rationale = result.get("rationale", "No rationale provided.")
        score = max(1, min(10, score))  # Clamp to 1-10

        logger.info(
            "Scored '%s' at %s: %d/10 [%s]",
            job.title, job.company, score,
            result.get("role_type", "unknown"),
        )
        return score, rationale
    except Exception as exc:
        logger.error("Failed to score job %d (%s): %s", job.id, job.title, exc)
        raise


def score_all_unscored(
    db: Database,
    profile: dict,
    delay: float = 2.0,
    dry_run: bool = False,
) -> int:
    """
    Score all jobs that have not yet been scored.

    Returns:
        Number of jobs scored.
    """
    jobs = db.get_unscored_jobs()
    if not jobs:
        logger.info("No unscored jobs found.")
        return 0

    logger.info("Scoring %d unscored jobs...", len(jobs))
    scored = 0

    for job in jobs:
        try:
            score, rationale = score_job(job, profile, delay=delay)
            if not dry_run:
                db.update_job_score(job.id, score, rationale)
            else:
                logger.info(
                    "[DRY RUN] Would score job %d '%s': %d/10",
                    job.id, job.title, score,
                )
            scored += 1
        except Exception as exc:
            logger.error("Skipping job %d due to error: %s", job.id, exc)
            continue

    logger.info("Scoring complete. %d/%d jobs scored.", scored, len(jobs))
    return scored


def score_single_job(
    job_id: int,
    db: Database,
    profile: dict,
    delay: float = 2.0,
    dry_run: bool = False,
) -> tuple[int, str]:
    """
    Score a single job by ID.
    """
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found in database.")

    score, rationale = score_job(job, profile, delay=delay)

    if not dry_run:
        db.update_job_score(job_id, score, rationale)

    return score, rationale
