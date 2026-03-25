"""
AI-powered cover letter generation using Claude API.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from ..tracker.database import Database
from ..tracker.models import Job
from ..utils.llm import call_claude

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path(__file__).resolve().parents[2] / "outputs" / "cover_letters"
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "config" / "templates"

COVER_LETTER_PROMPT = """\
Write a cover letter for a DePaul University Keeley Scholar applying to a finance internship.

RULES:
- Apply Dale Carnegie principles: show genuine interest in the company, make the reader feel important, frame everything in terms of what you can contribute to THEM
- Never use em dashes, en dashes, or hyphens as punctuation
- Keep it to 3 to 4 paragraphs, under 350 words
- Reference something specific about the company (use the job description context)
- Connect the candidate's entrepreneurial experience (Appointly Solutions) to the skills needed in banking/consulting (client management, analytical thinking, building systems)
- Mention the Keeley Scholars program and JPMorgan project MVP recognition
- Close with a specific, confident call to action
- Sound like a real 20 year old finance student wrote it, not an AI. No flowery language. No "I am writing to express my interest." Direct and substantive.

CANDIDATE PROFILE:
{profile_content}

TARGET JOB:
Title: {job_title}
Company: {company}
Description: {job_description}

Return only the cover letter body text (no salutation, no signature), no JSON wrapping.
"""


def generate_cover_letter_text(
    job: Job,
    profile: dict,
    delay: float = 2.0,
) -> str:
    """
    Use Claude to generate cover letter body text for a specific job.

    Returns:
        Cover letter body as a string.
    """
    import yaml

    profile_content = yaml.dump(profile, default_flow_style=False, allow_unicode=True)
    description = job.description or "No description available."
    if len(description) > 4000:
        description = description[:4000] + "...[truncated]"

    prompt = COVER_LETTER_PROMPT.format(
        profile_content=profile_content,
        job_title=job.title,
        company=job.company,
        job_description=description,
    )

    text = call_claude(prompt, delay=delay)
    logger.info(
        "Cover letter generated for job %d (%s at %s)",
        job.id, job.title, job.company,
    )
    return text.strip()


def render_cover_letter(
    body_text: str,
    job: Job,
    profile: dict,
    hiring_manager_name: Optional[str] = None,
) -> str:
    """
    Render the full cover letter using the Jinja2 template.

    Returns:
        Full formatted cover letter string.
    """
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("cover_letter.j2")

    # Split body into paragraphs
    paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
    while len(paragraphs) < 4:
        paragraphs.append("")

    rendered = template.render(
        date=datetime.now().strftime("%B %d, %Y"),
        hiring_manager_name=hiring_manager_name,
        company=job.company,
        company_address=None,
        paragraph_1=paragraphs[0] if len(paragraphs) > 0 else "",
        paragraph_2=paragraphs[1] if len(paragraphs) > 1 else "",
        paragraph_3=paragraphs[2] if len(paragraphs) > 2 else "",
        closing_paragraph=paragraphs[3] if len(paragraphs) > 3 else "",
        profile=profile,
    )
    return rendered


def save_cover_letter(
    content: str,
    job: Job,
) -> Path:
    """Save cover letter as a .txt file and return its path."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    safe_company = "".join(
        c if c.isalnum() or c in " _" else "" for c in job.company
    ).strip().replace(" ", "_")
    safe_title = "".join(
        c if c.isalnum() or c in " _" else "" for c in job.title
    ).strip().replace(" ", "_")[:40]
    filename = f"cover_letter_{safe_company}_{safe_title}_{job.id}.txt"
    output_path = OUTPUTS_DIR / filename

    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    logger.info("Cover letter saved to %s", output_path)
    return output_path


def generate_cover_letter_for_job(
    job_id: int,
    db: Database,
    profile: dict,
    delay: float = 2.0,
    dry_run: bool = False,
) -> Optional[Path]:
    """Generate and save a cover letter for a specific job ID."""
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found.")

    body_text = generate_cover_letter_text(job, profile, delay=delay)
    full_letter = render_cover_letter(body_text, job, profile)

    if dry_run:
        logger.info("[DRY RUN] Would generate cover letter for job %d", job_id)
        print(full_letter)
        return None

    path = save_cover_letter(full_letter, job)
    db.update_application_paths(job_id, cover_letter_path=str(path))
    return path
