"""
Follow-up email scheduling and sending.
"""
import logging
from datetime import datetime
from typing import Optional

from ..tracker.database import Database
from ..tracker.models import Job, Outreach

logger = logging.getLogger(__name__)


def send_due_followups(
    db: Database,
    profile: dict,
    dry_run: bool = False,
) -> int:
    """
    Find all outreach records where a follow-up is due and send them.

    Returns:
        Number of follow-ups sent.
    """
    from ..content.email_drafter import draft_followup_email
    from .email_sender import send_email

    due = db.get_due_followups()
    if not due:
        logger.info("No follow-ups due.")
        return 0

    logger.info("%d follow-up(s) due.", len(due))
    sent_count = 0

    personal = profile.get("personal", {})
    signature = (
        f"\n\n--\n"
        f"{personal.get('first_name', '')} {personal.get('last_name', '')}\n"
        f"DePaul University, Finance, Class of 2027\n"
        f"Keeley Scholars Program\n"
        f"{personal.get('email', '')}\n"
        f"{personal.get('phone', '')}"
    )

    for outreach in due:
        if not outreach.contact_email:
            logger.warning(
                "Outreach %d for %s has no contact email, skipping.", outreach.id, outreach.company
            )
            continue

        # Calculate days since original email
        days_since = 7
        if outreach.sent_at:
            try:
                sent_dt = datetime.fromisoformat(str(outreach.sent_at))
                days_since = (datetime.utcnow() - sent_dt).days
            except Exception:
                pass

        # Get the associated job (if any) for context
        job = db.get_job(outreach.job_id) if outreach.job_id else None
        job_title = job.title if job else "the internship position"

        # Draft follow-up
        try:
            followup_data = draft_followup_email(
                job=job,
                original_subject=outreach.email_subject or "DePaul Keeley Sophomore, Quick Question",
                contact_name=outreach.contact_name,
                days_since=days_since,
            )
        except Exception as exc:
            logger.error("Failed to draft follow-up for outreach %d: %s", outreach.id, exc)
            continue

        full_body = followup_data.get("body", "") + signature

        success = send_email(
            to=outreach.contact_email,
            subject=followup_data.get("subject", f"Re: {outreach.email_subject}"),
            body=full_body,
            dry_run=dry_run,
        )

        if success and not dry_run:
            db.mark_followup_sent(outreach.id)
            sent_count += 1
        elif dry_run:
            sent_count += 1

    logger.info("Follow-ups sent: %d/%d", sent_count, len(due))
    return sent_count


def schedule_job_with_apscheduler(
    db: Database,
    profile: dict,
    interval_hours: int = 24,
) -> None:
    """
    Use APScheduler to periodically send follow-up emails.
    This is optional; use `internpilot outreach --followups` for manual runs.
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        logger.error("APScheduler not installed. Run: pip install apscheduler")
        raise

    scheduler = BlockingScheduler()

    @scheduler.scheduled_job("interval", hours=interval_hours, id="followups")
    def followup_job():
        logger.info("Running scheduled follow-up check...")
        count = send_due_followups(db, profile)
        logger.info("Scheduled follow-up run complete. Sent: %d", count)

    logger.info("Starting scheduler (follow-up check every %d hours)...", interval_hours)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
