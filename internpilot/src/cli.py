"""
InternPilot CLI entry point using Click.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

import click

from .utils.config_loader import (
    load_env,
    load_employers,
    load_profile,
    load_searches,
    validate_configs,
)
from .tracker.database import Database

# Load .env on import
load_env()

# Logging setup
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(LOG_DIR / "internpilot.log")),
    ],
)
logger = logging.getLogger(__name__)

# Default DB path
DB_PATH = Path(__file__).resolve().parents[1] / "internpilot.db"


def get_db() -> Database:
    return Database(DB_PATH)


# ============================================================
# Root group
# ============================================================

@click.group()
@click.version_option("1.0.0", prog_name="InternPilot")
def cli():
    """InternPilot: Automate your finance internship applications."""
    pass


# ============================================================
# PIPELINE HELPER (shared by `run` and `schedule`)
# ============================================================

def _run_pipeline_once(
    source: str = "all",
    skip_apply: bool = False,
    skip_outreach: bool = False,
    supervised: bool = False,
    dry_run: bool = False,
) -> None:
    """Execute one full pipeline: discover → score → generate → apply → outreach."""
    import datetime

    db = get_db()
    profile = load_profile()
    searches_config = load_searches()
    filters = searches_config.get("filters", {})
    min_score = filters.get("min_match_score", 7)
    max_per_day = filters.get("max_applications_per_day", 10)
    cooldown_days = filters.get("cooldown_days_per_company", 90)

    start = datetime.datetime.now()
    click.echo(f"\n{'='*60}")
    click.echo(f"  InternPilot Pipeline  |  {start:%Y-%m-%d %H:%M:%S}")
    if dry_run:
        click.echo("  [DRY RUN - no changes will be saved]")
    click.echo(f"{'='*60}")

    # ── Step 1: Discover ───────────────────────────────────────
    click.echo("\n[1/5] Discovering jobs...")
    searches = searches_config.get("searches", [])
    if searches:
        try:
            from .discovery.scraper import scrape_jobs
            total = scrape_jobs(searches, db, source=source, dry_run=dry_run)
            click.echo(f"  New jobs found: {total}")
        except Exception as exc:
            click.echo(f"  Discovery error: {exc}", err=True)
            logger.error("Discovery error: %s", exc)
    else:
        click.echo("  No searches configured, skipping.")

    # ── Step 2: Score ──────────────────────────────────────────
    click.echo("\n[2/5] Scoring unscored jobs...")
    try:
        from .scoring.matcher import score_all_unscored
        scored = score_all_unscored(db, profile, dry_run=dry_run)
        click.echo(f"  Jobs scored: {scored}")
    except Exception as exc:
        click.echo(f"  Scoring error: {exc}", err=True)
        logger.error("Scoring error: %s", exc)

    # ── Step 3: Generate content ───────────────────────────────
    click.echo("\n[3/5] Generating application content...")
    try:
        from .content.resume_tailor import generate_resume_for_job
        from .content.cover_letter import generate_cover_letter_for_job
        from .content.email_drafter import generate_email_for_job

        all_scored = db.get_jobs_by_min_score(min_score)
        pending_gen = [j for j in all_scored if j.status == "scored"]
        click.echo(f"  Jobs needing content: {len(pending_gen)}")
        gen_ok = 0
        for job in pending_gen:
            jid = job.id
            try:
                generate_resume_for_job(jid, db, profile, dry_run=dry_run)
                generate_cover_letter_for_job(jid, db, profile, dry_run=dry_run)
                generate_email_for_job(jid, db, dry_run=dry_run)
                if not dry_run:
                    db.update_job_status(jid, "content_generated")
                gen_ok += 1
            except Exception as exc:
                click.echo(f"  [Job {jid}] Generate error: {exc}", err=True)
                logger.error("Generate error for job %d: %s", jid, exc)
        click.echo(f"  Content generated: {gen_ok}/{len(pending_gen)}")
    except Exception as exc:
        click.echo(f"  Content generation error: {exc}", err=True)
        logger.error("Content generation error: %s", exc)

    # ── Step 4: Apply ──────────────────────────────────────────
    if not skip_apply:
        click.echo("\n[4/5] Applying to jobs...")
        try:
            from .applicant.workday_agent import apply_to_job

            jobs_to_apply = db.get_all_jobs(status="content_generated")
            applied_today = db.count_applications_today()
            recent_companies = db.get_companies_applied_recently(cooldown_days)
            applied_count = 0

            for job in jobs_to_apply:
                if applied_today + applied_count >= max_per_day:
                    click.echo(f"  Daily limit ({max_per_day}) reached.")
                    break
                if job.company in recent_companies:
                    click.echo(f"  Skipping {job.company} (cooldown active).")
                    continue
                try:
                    success = asyncio.run(
                        apply_to_job(job.id, db, profile, supervised=supervised, dry_run=dry_run)
                    )
                    if success:
                        applied_count += 1
                        click.echo(f"  Applied: {job.title} @ {job.company}")
                except Exception as exc:
                    click.echo(f"  [Job {job.id}] Apply error: {exc}", err=True)
                    logger.error("Apply error for job %d: %s", job.id, exc)

            click.echo(f"  Applications submitted: {applied_count}")
        except Exception as exc:
            click.echo(f"  Apply step error: {exc}", err=True)
            logger.error("Apply step error: %s", exc)
    else:
        click.echo("\n[4/5] Apply step skipped.")

    # ── Step 5: Outreach follow-ups ────────────────────────────
    if not skip_outreach:
        click.echo("\n[5/5] Sending due follow-up emails...")
        try:
            from .outreach.scheduler import send_due_followups
            fu_count = send_due_followups(db, profile, dry_run=dry_run)
            click.echo(f"  Follow-ups sent: {fu_count}")
        except Exception as exc:
            click.echo(f"  Outreach error: {exc}", err=True)
            logger.error("Outreach error: %s", exc)
    else:
        click.echo("\n[5/5] Outreach step skipped.")

    elapsed = (datetime.datetime.now() - start).seconds
    click.echo(f"\n{'='*60}")
    click.echo(f"  Pipeline complete in {elapsed}s.")
    click.echo(f"{'='*60}\n")


# ============================================================
# RUN  (one-shot full pipeline)
# ============================================================

@cli.command("run")
@click.option(
    "--source",
    default="all",
    type=click.Choice(["all", "linkedin", "indeed", "glassdoor", "ziprecruiter", "google"], case_sensitive=False),
    help="Job board to scrape during discovery.",
)
@click.option("--skip-apply", is_flag=True, help="Skip the Workday application step.")
@click.option("--skip-outreach", is_flag=True, help="Skip the follow-up email step.")
@click.option(
    "--supervised/--no-supervised",
    default=False,
    help="Pause browser automation for human confirmation (default: off for automation).",
)
@click.option("--dry-run", is_flag=True, help="Simulate all steps without saving or submitting.")
def run_pipeline(source: str, skip_apply: bool, skip_outreach: bool, supervised: bool, dry_run: bool):
    """Run the full pipeline in one command: discover → score → generate → apply → outreach."""
    _run_pipeline_once(
        source=source,
        skip_apply=skip_apply,
        skip_outreach=skip_outreach,
        supervised=supervised,
        dry_run=dry_run,
    )


# ============================================================
# SCHEDULE  (recurring automated pipeline)
# ============================================================

@cli.command("schedule")
@click.option(
    "--time",
    "run_time",
    default="08:00",
    help="Daily run time in HH:MM (24-hour). Default: 08:00.",
    show_default=True,
)
@click.option(
    "--interval",
    type=int,
    default=None,
    metavar="HOURS",
    help="Run every N hours instead of once per day at a fixed time.",
)
@click.option(
    "--source",
    default="all",
    type=click.Choice(["all", "linkedin", "indeed", "glassdoor", "ziprecruiter", "google"], case_sensitive=False),
    help="Job board to scrape during each discovery run.",
)
@click.option("--skip-apply", is_flag=True, help="Skip the Workday application step.")
@click.option("--skip-outreach", is_flag=True, help="Skip the follow-up email step.")
@click.option(
    "--supervised/--no-supervised",
    default=False,
    help="Pause browser automation for human confirmation.",
)
@click.option("--dry-run", is_flag=True, help="Simulate all steps without saving or submitting.")
@click.option("--run-now", is_flag=True, help="Run the pipeline immediately on start, then follow the schedule.")
def schedule(
    run_time: str,
    interval: int,
    source: str,
    skip_apply: bool,
    skip_outreach: bool,
    supervised: bool,
    dry_run: bool,
    run_now: bool,
):
    """Run the full pipeline automatically on a schedule (runs until Ctrl+C)."""
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
    except ImportError:
        click.echo("APScheduler is required: pip install apscheduler", err=True)
        sys.exit(1)

    def _job():
        _run_pipeline_once(
            source=source,
            skip_apply=skip_apply,
            skip_outreach=skip_outreach,
            supervised=supervised,
            dry_run=dry_run,
        )

    scheduler = BlockingScheduler(timezone="America/Chicago")

    if interval:
        scheduler.add_job(_job, "interval", hours=interval)
        click.echo(f"Scheduler started: pipeline runs every {interval} hour(s).")
    else:
        try:
            hour, minute = map(int, run_time.split(":"))
        except ValueError:
            click.echo(f"Invalid --time value '{run_time}'. Use HH:MM format.", err=True)
            sys.exit(1)
        scheduler.add_job(_job, "cron", hour=hour, minute=minute)
        click.echo(f"Scheduler started: pipeline runs daily at {run_time}.")

    click.echo("Press Ctrl+C to stop.\n")

    if run_now:
        click.echo("Running pipeline now before entering schedule loop...")
        _job()

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        click.echo("\nScheduler stopped.")


# ============================================================
# DISCOVER
# ============================================================

@cli.command()
@click.option(
    "--source",
    default="all",
    type=click.Choice(["all", "linkedin", "indeed", "glassdoor", "ziprecruiter", "google"], case_sensitive=False),
    help="Which job board to scrape.",
)
@click.option("--workday", is_flag=True, help="Scrape configured Workday portals only.")
@click.option("--dry-run", is_flag=True, help="Show what would be discovered without saving.")
def discover(source: str, workday: bool, dry_run: bool):
    """Discover new job listings from job boards and Workday portals."""
    db = get_db()

    if workday:
        click.echo("Scraping Workday portals...")
        employers = load_employers()
        employer_list = employers.get("employers", [])

        async def run_workday():
            from .discovery.workday_scraper import scrape_all_workday_portals
            total = await scrape_all_workday_portals(employer_list, db, dry_run=dry_run)
            click.echo(f"Workday scrape complete. New jobs: {total}")

        asyncio.run(run_workday())
        return

    click.echo(f"Discovering jobs (source={source})...")
    searches_config = load_searches()
    searches = searches_config.get("searches", [])

    if not searches:
        click.echo("No searches configured in searches.yaml.", err=True)
        sys.exit(1)

    try:
        from .discovery.scraper import scrape_jobs
        total = scrape_jobs(searches, db, source=source, dry_run=dry_run)
        if dry_run:
            click.echo(f"[DRY RUN] Would have discovered {total} new jobs.")
        else:
            click.echo(f"Discovery complete. {total} new jobs added to database.")
    except ImportError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ============================================================
# SCORE
# ============================================================

@cli.command()
@click.option("--job-id", type=int, default=None, help="Score a specific job by ID.")
@click.option("--dry-run", is_flag=True, help="Show scores without saving.")
def score(job_id: int, dry_run: bool):
    """Score unscored jobs against your profile using Claude AI."""
    db = get_db()
    profile = load_profile()

    try:
        from .scoring.matcher import score_all_unscored, score_single_job

        if job_id:
            click.echo(f"Scoring job {job_id}...")
            s, rationale = score_single_job(job_id, db, profile, dry_run=dry_run)
            click.echo(f"Score: {s}/10")
            click.echo(f"Rationale: {rationale}")
        else:
            click.echo("Scoring all unscored jobs...")
            count = score_all_unscored(db, profile, dry_run=dry_run)
            click.echo(f"Scored {count} jobs.")
    except Exception as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)


# ============================================================
# GENERATE
# ============================================================

@cli.command()
@click.option("--job-id", type=int, default=None, help="Generate content for a specific job.")
@click.option("--all", "generate_all", is_flag=True, help="Generate for all jobs scoring 7+.")
@click.option("--resume-only", type=int, default=None, metavar="JOB_ID", help="Generate resume only for job ID.")
@click.option("--email-only", type=int, default=None, metavar="JOB_ID", help="Generate recruiter email only for job ID.")
@click.option("--dry-run", is_flag=True, help="Preview output without saving files.")
def generate(job_id: int, generate_all: bool, resume_only: int, email_only: int, dry_run: bool):
    """Generate tailored resume, cover letter, and recruiter email."""
    db = get_db()
    profile = load_profile()
    searches_config = load_searches()
    min_score = searches_config.get("filters", {}).get("min_match_score", 7)

    from .content.resume_tailor import generate_resume_for_job
    from .content.cover_letter import generate_cover_letter_for_job
    from .content.email_drafter import generate_email_for_job

    if resume_only:
        click.echo(f"Generating resume for job {resume_only}...")
        path = generate_resume_for_job(resume_only, db, profile, dry_run=dry_run)
        if path:
            click.echo(f"Resume saved: {path}")
        return

    if email_only:
        click.echo(f"Generating recruiter email for job {email_only}...")
        path = generate_email_for_job(email_only, db, dry_run=dry_run)
        if path:
            click.echo(f"Email saved: {path}")
        return

    target_ids = []
    if job_id:
        target_ids = [job_id]
    elif generate_all:
        jobs = db.get_jobs_by_min_score(min_score)
        target_ids = [j.id for j in jobs]
        click.echo(f"Generating content for {len(target_ids)} jobs scoring {min_score}+...")
    else:
        click.echo("Specify --job-id, --all, --resume-only, or --email-only.", err=True)
        sys.exit(1)

    for jid in target_ids:
        click.echo(f"\n[Job {jid}] Generating resume...")
        try:
            resume_path = generate_resume_for_job(jid, db, profile, dry_run=dry_run)
            if resume_path:
                click.echo(f"  Resume: {resume_path}")
        except Exception as exc:
            click.echo(f"  Resume error: {exc}", err=True)

        click.echo(f"[Job {jid}] Generating cover letter...")
        try:
            cl_path = generate_cover_letter_for_job(jid, db, profile, dry_run=dry_run)
            if cl_path:
                click.echo(f"  Cover letter: {cl_path}")
        except Exception as exc:
            click.echo(f"  Cover letter error: {exc}", err=True)

        click.echo(f"[Job {jid}] Generating recruiter email...")
        try:
            email_path = generate_email_for_job(jid, db, dry_run=dry_run)
            if email_path:
                click.echo(f"  Email: {email_path}")
        except Exception as exc:
            click.echo(f"  Email error: {exc}", err=True)

        if not dry_run:
            db.update_job_status(jid, "content_generated")

    click.echo("\nContent generation complete.")


# ============================================================
# APPLY
# ============================================================

@cli.command()
@click.option("--job-id", type=int, default=None, help="Apply to a specific job.")
@click.option("--supervised", is_flag=True, default=True, help="Pause after every field for confirmation.")
@click.option("--batch", is_flag=True, help="Apply to all jobs with content ready.")
@click.option("--dry-run", is_flag=True, help="Simulate application without submitting.")
def apply(job_id: int, supervised: bool, batch: bool, dry_run: bool):
    """Submit job applications via Browser Use Workday automation."""
    db = get_db()
    profile = load_profile()
    searches_config = load_searches()
    filters = searches_config.get("filters", {})
    max_per_day = filters.get("max_applications_per_day", 10)
    cooldown_days = filters.get("cooldown_days_per_company", 90)

    from .applicant.workday_agent import apply_to_job

    target_ids = []
    if job_id:
        target_ids = [job_id]
    elif batch:
        jobs = db.get_all_jobs(status="content_generated")
        target_ids = [j.id for j in jobs]
        click.echo(f"Batch apply: {len(target_ids)} jobs with content ready.")
    else:
        click.echo("Specify --job-id or --batch.", err=True)
        sys.exit(1)

    applied_today = db.count_applications_today()
    recent_companies = db.get_companies_applied_recently(cooldown_days)

    applied_count = 0
    for jid in target_ids:
        if applied_today + applied_count >= max_per_day:
            click.echo(f"Daily application limit ({max_per_day}) reached. Stopping.")
            break

        job = db.get_job(jid)
        if not job:
            click.echo(f"Job {jid} not found, skipping.", err=True)
            continue

        if job.company in recent_companies:
            click.echo(
                f"Skipping {job.company} (applied within last {cooldown_days} days)."
            )
            continue

        click.echo(f"\nApplying to: {job.title} at {job.company} (job_id={jid})")

        try:
            success = asyncio.run(
                apply_to_job(jid, db, profile, supervised=supervised, dry_run=dry_run)
            )
            if success:
                applied_count += 1
                click.echo(f"  Applied successfully.")
            else:
                click.echo(f"  Application not completed (see above).")
        except Exception as exc:
            click.echo(f"  Error: {exc}", err=True)
            logger.error("Apply error for job %d: %s", jid, exc)

    click.echo(f"\nApply session complete. Applications submitted: {applied_count}")


# ============================================================
# OUTREACH
# ============================================================

@cli.command()
@click.option("--job-id", type=int, default=None, help="Send recruiter email for a specific job.")
@click.option("--followups", is_flag=True, help="Send all due follow-up emails.")
@click.option("--contact-name", default=None, help="Recruiter name.")
@click.option("--contact-email", default=None, help="Recruiter email address.")
@click.option("--contact-title", default=None, help="Recruiter job title.")
@click.option("--dry-run", is_flag=True, help="Preview emails without sending.")
def outreach(
    job_id: int,
    followups: bool,
    contact_name: str,
    contact_email: str,
    contact_title: str,
    dry_run: bool,
):
    """Send recruiter outreach emails and follow-ups."""
    db = get_db()
    profile = load_profile()

    if followups:
        click.echo("Checking for due follow-ups...")
        from .outreach.scheduler import send_due_followups
        count = send_due_followups(db, profile, dry_run=dry_run)
        click.echo(f"Follow-ups sent: {count}")
        return

    if job_id:
        click.echo(f"Sending outreach for job {job_id}...")
        from .content.email_drafter import generate_email_for_job
        from .outreach.email_sender import send_outreach_email

        # Generate draft if not already done
        path = generate_email_for_job(
            job_id,
            db,
            contact_name=contact_name,
            contact_email=contact_email,
            contact_title=contact_title,
            dry_run=dry_run,
        )
        if path:
            click.echo(f"Email draft saved: {path}")

        if contact_email and not dry_run:
            # Find the outreach record just created
            outreaches = db.get_outreach_for_job(job_id)
            if outreaches:
                latest = outreaches[0]
                success = send_outreach_email(latest.id, db, profile, dry_run=dry_run)
                click.echo("Email sent." if success else "Email send failed.")
        elif dry_run:
            click.echo("[DRY RUN] Email not sent.")
        else:
            click.echo("No --contact-email provided. Email draft saved but not sent.")
        return

    click.echo("Specify --job-id or --followups.", err=True)
    sys.exit(1)


# ============================================================
# STATUS
# ============================================================

@cli.command()
@click.option("--job-id", type=int, default=None, help="Show details for one job.")
@click.option("--applied", is_flag=True, help="List all applied jobs.")
@click.option("--pending", is_flag=True, help="List jobs with content ready but not applied.")
def status(job_id: int, applied: bool, pending: bool):
    """Show application tracker dashboard."""
    db = get_db()

    if job_id:
        _show_job_details(db, job_id)
        return

    if applied:
        jobs = db.get_all_jobs(status="applied")
        _print_job_table(jobs, "Applied Jobs")
        return

    if pending:
        jobs = db.get_all_jobs(status="content_generated")
        _print_job_table(jobs, "Content Ready (Pending Application)")
        return

    # Default: full dashboard
    stats = db.get_summary_stats()
    click.echo("\n" + "=" * 60)
    click.echo("  InternPilot Dashboard")
    click.echo("=" * 60)
    click.echo(f"  Total jobs tracked:    {stats['total']}")
    click.echo(f"  Discovered:            {stats['discovered']}")
    click.echo(f"  Scored:                {stats['scored']}")
    click.echo(f"  Content generated:     {stats['content_generated']}")
    click.echo(f"  Applied:               {stats['applied']}")
    click.echo(f"  Interview:             {stats['interview']}")
    click.echo(f"  Offer:                 {stats['offer']}")
    click.echo(f"  Rejected:              {stats['rejected']}")
    click.echo("-" * 60)
    click.echo(f"  Outreach emails sent:  {stats['outreach_sent']}")
    click.echo(f"  Responses received:    {stats['responses']}")
    click.echo("=" * 60 + "\n")

    # Show top scored jobs
    top_jobs = db.get_jobs_by_min_score(7)[:10]
    if top_jobs:
        click.echo("Top Scored Jobs (7+):")
        _print_job_table(top_jobs[:10])


def _show_job_details(db: Database, job_id: int) -> None:
    job = db.get_job(job_id)
    if not job:
        click.echo(f"Job {job_id} not found.", err=True)
        return

    application = db.get_application(job_id)
    outreaches = db.get_outreach_for_job(job_id)

    click.echo("\n" + "=" * 60)
    click.echo(f"  Job {job_id}: {job.title}")
    click.echo("=" * 60)
    click.echo(f"  Company:       {job.company}")
    click.echo(f"  Location:      {job.location or 'N/A'}")
    click.echo(f"  Source:        {job.source or 'N/A'}")
    click.echo(f"  Status:        {job.status}")
    click.echo(f"  Match Score:   {job.match_score or 'Unscored'}/10")
    click.echo(f"  URL:           {job.url}")
    if job.match_rationale:
        click.echo(f"\n  Rationale: {job.match_rationale}")
    if application:
        click.echo(f"\n  Application:")
        click.echo(f"    Applied at:   {application.applied_at or 'Not yet applied'}")
        click.echo(f"    Method:       {application.method or 'N/A'}")
        click.echo(f"    Resume:       {application.resume_path or 'Not generated'}")
        click.echo(f"    Cover Letter: {application.cover_letter_path or 'Not generated'}")
    if outreaches:
        click.echo(f"\n  Outreach ({len(outreaches)} record(s)):")
        for o in outreaches:
            click.echo(f"    Contact: {o.contact_name or 'Unknown'} ({o.contact_email or 'no email'})")
            click.echo(f"    Sent: {o.sent_at or 'Not sent'}")
            click.echo(f"    Follow-up: {o.followup_scheduled_at or 'N/A'}")
    click.echo("=" * 60 + "\n")


def _print_job_table(jobs: list, title: str = "") -> None:
    if title:
        click.echo(f"\n{title} ({len(jobs)} jobs):")
    click.echo(f"{'ID':<6} {'Score':<7} {'Status':<20} {'Company':<25} {'Title'}")
    click.echo("-" * 90)
    for job in jobs:
        score_str = f"{job.match_score}/10" if job.match_score else "N/A"
        title_str = job.title[:45] if len(job.title) > 45 else job.title
        company_str = job.company[:23] if len(job.company) > 23 else job.company
        click.echo(
            f"{job.id:<6} {score_str:<7} {job.status:<20} {company_str:<25} {title_str}"
        )


# ============================================================
# EXPORT
# ============================================================

@cli.command()
@click.option("--csv", "to_csv", is_flag=True, help="Export tracker to CSV.")
@click.option("--output", default="internpilot_export.csv", help="Output file path.")
def export(to_csv: bool, output: str):
    """Export job tracker data."""
    if not to_csv:
        click.echo("Specify --csv.", err=True)
        sys.exit(1)

    db = get_db()
    output_path = Path(output)
    db.export_to_csv(output_path)
    click.echo(f"Exported to {output_path}")


# ============================================================
# CONFIG
# ============================================================

@cli.command("config")
@click.option("--validate", is_flag=True, help="Validate all YAML configs and env vars.")
@click.option("--add-employer", is_flag=True, help="Interactive prompt to add a new employer.")
def config_cmd(validate: bool, add_employer: bool):
    """Manage InternPilot configuration."""
    if validate:
        click.echo("Validating configuration...")
        issues = validate_configs()
        if issues:
            click.echo(f"Found {len(issues)} issue(s):")
            for issue in issues:
                click.echo(f"  [!] {issue}")
        else:
            click.echo("All configurations are valid.")
        return

    if add_employer:
        _interactive_add_employer()
        return

    click.echo("Specify --validate or --add-employer.", err=True)


def _interactive_add_employer() -> None:
    """Interactively add a new employer to employers.yaml."""
    import yaml

    click.echo("\nAdd New Employer")
    click.echo("-" * 40)
    name = click.prompt("Company name")
    workday_url = click.prompt("Workday portal URL (or press Enter to skip)", default="")
    keywords_input = click.prompt("Keywords (comma-separated)")
    priority = click.prompt("Priority (1=highest)", type=int, default=2)

    keywords = [k.strip() for k in keywords_input.split(",") if k.strip()]

    employer_entry = {
        "name": name,
        "workday_url": workday_url or "[FILL IN WORKDAY URL]",
        "keywords": keywords,
        "priority": priority,
        "contacts": [],
    }

    config_path = Path(__file__).resolve().parents[1] / "config" / "employers.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        data.setdefault("employers", []).append(employer_entry)

        with open(config_path, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)

        click.echo(f"\nAdded {name} to employers.yaml.")
    except Exception as exc:
        click.echo(f"Error updating employers.yaml: {exc}", err=True)
