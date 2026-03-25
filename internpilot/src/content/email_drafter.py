"""
Recruiter outreach and follow-up email drafting using Claude API.
"""
import logging
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from ..tracker.database import Database
from ..tracker.models import Job
from ..utils.llm import call_claude_json

logger = logging.getLogger(__name__)

OUTPUTS_DIR = Path(__file__).resolve().parents[2] / "outputs" / "emails"
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "config" / "templates"

RECRUITER_EMAIL_PROMPT = """\
Draft a networking email from a DePaul University Keeley Scholar to a recruiter or professional at the target company.

RULES:
- Subject line format: "DePaul Keeley Sophomore, Quick Question"
- Apply Dale Carnegie principles throughout
- Never use em dashes, en dashes, or hyphens as punctuation
- Keep it under 150 words total
- Open with one specific thing about the company or the recipient that shows research (not generic flattery)
- Briefly mention your background: Keeley Scholars, finance major, Appointly (entrepreneurial experience)
- Ask ONE clear, easy to answer question (not "can I pick your brain" but something specific like "would you recommend any particular preparation for the summer analyst program?")
- Close warmly but professionally
- Should read like a real college student wrote it, conversational but polished

CANDIDATE: Patrick, Sophomore, DePaul University Keeley Scholars Program, Finance Major
COMPANY: {company}
ROLE: {job_title}
CONTACT NAME: {contact_name}
CONTACT TITLE: {contact_title}

Return as JSON:
{{
  "subject": "...",
  "body": "..."
}}
"""

FOLLOWUP_EMAIL_PROMPT = """\
Write a brief follow-up email to a recruiter who has not responded to an initial networking outreach.

RULES:
- Never use em dashes, en dashes, or hyphens as punctuation
- Keep it under 100 words total
- Acknowledge that they are busy
- Reiterate genuine interest in the company (not the job listing)
- Same polite, direct tone as the original email
- Do not beg or over-apologize

CANDIDATE: Patrick, Sophomore, DePaul University Keeley Scholars Program, Finance Major
COMPANY: {company}
ROLE: {job_title}
CONTACT NAME: {contact_name}
ORIGINAL SUBJECT: {original_subject}
DAYS SINCE FIRST EMAIL: {days_since}

Return as JSON:
{{
  "subject": "Re: {original_subject}",
  "body": "..."
}}
"""


def draft_recruiter_email(
    job: Job,
    contact_name: Optional[str] = None,
    contact_title: Optional[str] = None,
    delay: float = 2.0,
) -> dict:
    """
    Draft a recruiter outreach email for a job.

    Returns:
        Dict with keys: subject, body.
    """
    prompt = RECRUITER_EMAIL_PROMPT.format(
        company=job.company,
        job_title=job.title,
        contact_name=contact_name or "not provided",
        contact_title=contact_title or "not provided",
    )

    result = call_claude_json(prompt, delay=delay)
    logger.info(
        "Recruiter email drafted for job %d (%s at %s)",
        job.id, job.title, job.company,
    )
    return result


def draft_followup_email(
    job: Job,
    original_subject: str,
    contact_name: Optional[str] = None,
    days_since: int = 7,
    delay: float = 2.0,
) -> dict:
    """
    Draft a follow-up email for a job.

    Returns:
        Dict with keys: subject, body.
    """
    prompt = FOLLOWUP_EMAIL_PROMPT.format(
        company=job.company,
        job_title=job.title,
        contact_name=contact_name or "not provided",
        original_subject=original_subject,
        days_since=days_since,
    )

    result = call_claude_json(prompt, delay=delay)
    logger.info("Follow-up email drafted for %s", job.company)
    return result


def save_email_draft(
    email_data: dict,
    job: Job,
    email_type: str = "outreach",
) -> Path:
    """Save a drafted email to the outputs/emails directory."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    safe_company = "".join(
        c if c.isalnum() or c in " _" else "" for c in job.company
    ).strip().replace(" ", "_")
    filename = f"{email_type}_{safe_company}_{job.id}.txt"
    output_path = OUTPUTS_DIR / filename

    content = f"Subject: {email_data.get('subject', '')}\n\n{email_data.get('body', '')}"
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(content)

    logger.info("Email draft saved to %s", output_path)
    return output_path


THANKYOU_EMAIL_PROMPT = """\
Write a brief thank-you email after a job interview for a finance internship.

RULES:
- Never use em dashes, en dashes, or hyphens as punctuation
- Keep it under 120 words total
- Reference one specific topic that was discussed in the interview
- Reiterate genuine interest in the specific role and firm
- Professional, warm, not sycophantic
- Sound like a real 20 year old, not an AI

CANDIDATE: Patrick, Sophomore, DePaul University Keeley Scholars Program, Finance Major
COMPANY: {company}
ROLE: {job_title}
INTERVIEWER NAME: {contact_name}
INTERVIEWER TITLE: {contact_title}
SPECIFIC TOPIC DISCUSSED: {topic_discussed}
INTERVIEW DATE: {interview_date}

Return as JSON:
{{
  "subject": "Thank You - {job_title} Interview",
  "body": "..."
}}
"""


def draft_thankyou_email(
    job: Job,
    contact_name: Optional[str] = None,
    contact_title: Optional[str] = None,
    topic_discussed: str = "the role and team",
    interview_date: str = "today",
    delay: float = 2.0,
) -> dict:
    """
    Draft a post-interview thank-you email.

    Returns:
        Dict with keys: subject, body.
    """
    prompt = THANKYOU_EMAIL_PROMPT.format(
        company=job.company,
        job_title=job.title,
        contact_name=contact_name or "Interviewer",
        contact_title=contact_title or "not provided",
        topic_discussed=topic_discussed,
        interview_date=interview_date,
    )
    result = call_claude_json(prompt, delay=delay)
    logger.info("Thank-you email drafted for job %d (%s)", job.id, job.company)
    return result


def generate_email_for_job(
    job_id: int,
    db: Database,
    contact_name: Optional[str] = None,
    contact_email: Optional[str] = None,
    contact_title: Optional[str] = None,
    delay: float = 2.0,
    dry_run: bool = False,
) -> Optional[Path]:
    """Generate and save a recruiter email for a specific job ID."""
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found.")

    email_data = draft_recruiter_email(
        job,
        contact_name=contact_name,
        contact_title=contact_title,
        delay=delay,
    )

    if dry_run:
        logger.info("[DRY RUN] Would save email for job %d", job_id)
        print(f"Subject: {email_data.get('subject', '')}")
        print()
        print(email_data.get("body", ""))
        return None

    path = save_email_draft(email_data, job, email_type="outreach")

    # Record in outreach table
    db.insert_outreach(
        company=job.company,
        job_id=job_id,
        contact_name=contact_name,
        contact_email=contact_email,
        contact_title=contact_title,
        email_subject=email_data.get("subject"),
        email_body=email_data.get("body"),
    )

    return path
