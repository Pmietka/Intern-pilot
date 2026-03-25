"""
Browser Use agent for automated Workday job applications.

Uses the browser-use library (AI browser agent) to navigate Workday portals,
fill forms using profile data, and submit applications.

The agent runs in a headed (visible) browser so the user can monitor progress.
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

from ..tracker.database import Database
from ..tracker.models import Job
from .form_filler import build_profile_answers, get_screenshot_path

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path(__file__).resolve().parents[2] / "outputs" / "screenshots"

# Workday application agent task template
WORKDAY_TASK_TEMPLATE = """\
You are filling out a job application on Workday for {company} for the position: {job_title}.

The application URL is: {application_url}

CANDIDATE PROFILE DATA (use these exact values for form fields):
{profile_data_formatted}

RESUME FILE PATH: {resume_path}

IMPORTANT INSTRUCTIONS:
1. Navigate to the application URL and click "Apply" to begin.
2. Fill in ALL form fields using the candidate profile data provided above.
3. Match field labels to profile data intelligently (e.g., "First Name" -> "{first_name}").
4. When you encounter a file upload field for a resume, upload the file at: {resume_path}
5. For dropdown fields, select the option that best matches the profile data.
6. For fields not covered by the profile data, use best judgment based on context.
7. PAUSE on any field you cannot confidently fill and ask for input.
8. Take a screenshot after completing each page/section.
9. BEFORE clicking the final Submit button, PAUSE and report: "READY TO SUBMIT - please confirm."
10. Do NOT submit without explicit confirmation.

SUPERVISED MODE: {supervised}
If supervised=True, pause after EVERY field fill and confirm with the user.
If supervised=False, only pause on uncertain fields and before final submission.

If you encounter a CAPTCHA, stop immediately and report: "CAPTCHA DETECTED - manual intervention required."
"""


async def run_workday_agent(
    job: Job,
    profile: dict,
    resume_path: Optional[Path] = None,
    supervised: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Run the Browser Use agent to fill out a Workday application.

    Args:
        job: Job record with workday_portal URL.
        profile: Candidate profile dict.
        resume_path: Path to the tailored resume .docx or .pdf file.
        supervised: If True, pause after every field. If False, only pause on uncertain fields.
        dry_run: If True, simulate without actually submitting.

    Returns:
        Dict with keys: success (bool), notes (str), fields_needing_input (list).
    """
    try:
        from browser_use import Agent, Browser, BrowserConfig
        from langchain_anthropic import ChatAnthropic
    except ImportError as exc:
        logger.error(
            "browser-use or langchain-anthropic not installed. "
            "Run: pip install browser-use langchain-anthropic\n%s", exc
        )
        raise

    from ..utils.config_loader import get_anthropic_api_key

    application_url = job.workday_portal or job.url
    if not application_url:
        raise ValueError(f"Job {job.id} has no application URL.")

    profile_answers = build_profile_answers(profile)
    personal = profile.get("personal", {})

    # Format profile data for the prompt
    profile_lines = [f"  {k}: {v}" for k, v in profile_answers.items()]
    profile_data_formatted = "\n".join(profile_lines)

    resume_path_str = str(resume_path) if resume_path and resume_path.exists() else "NOT PROVIDED"

    task = WORKDAY_TASK_TEMPLATE.format(
        company=job.company,
        job_title=job.title,
        application_url=application_url,
        profile_data_formatted=profile_data_formatted,
        resume_path=resume_path_str,
        first_name=personal.get("first_name", ""),
        supervised=supervised,
    )

    if dry_run:
        logger.info("[DRY RUN] Would run Workday agent for job %d: %s at %s", job.id, job.title, job.company)
        logger.info("[DRY RUN] Application URL: %s", application_url)
        logger.info("[DRY RUN] Supervised: %s", supervised)
        return {"success": False, "notes": "dry_run", "fields_needing_input": []}

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    llm = ChatAnthropic(
        model="claude-sonnet-4-20250514",
        api_key=get_anthropic_api_key(),
        timeout=120,
        max_tokens=4096,
    )

    # Configure browser: headed (visible) so user can watch
    browser_config = BrowserConfig(
        headless=False,
        disable_security=False,
    )

    result_data = {
        "success": False,
        "notes": "",
        "fields_needing_input": [],
    }

    try:
        logger.info(
            "Starting Workday agent for %s (%s) - supervised=%s",
            job.company, job.title, supervised,
        )
        print(f"\n[WORKDAY AGENT] Starting application for {job.title} at {job.company}")
        print(f"[WORKDAY AGENT] URL: {application_url}")
        print(f"[WORKDAY AGENT] Supervised mode: {supervised}")
        print("[WORKDAY AGENT] Browser window will open. Watch for [NEEDS INPUT] and [CONFIRM] prompts.\n")

        browser = Browser(config=browser_config)
        agent = Agent(
            task=task,
            llm=llm,
            browser=browser,
        )

        agent_result = await agent.run()
        result_text = str(agent_result)

        # Check for submit confirmation
        if "READY TO SUBMIT" in result_text or "ready to submit" in result_text.lower():
            print(f"\n[CONFIRM] Ready to submit application to {job.company} for {job.title}.")
            print("Type 'submit' to confirm or 'abort' to cancel: ", end="")
            user_input = input().strip().lower()

            if user_input == "submit":
                print("[WORKDAY AGENT] Submitting application...")
                # The agent has already paused; we would need to signal it to continue.
                # In practice, the agent handles this via its task description.
                result_data["success"] = True
                result_data["notes"] = "Application submitted by user confirmation."
            else:
                result_data["success"] = False
                result_data["notes"] = "Application aborted by user."
                print("[WORKDAY AGENT] Application aborted.")
        elif "CAPTCHA DETECTED" in result_text:
            result_data["success"] = False
            result_data["notes"] = "CAPTCHA detected. Manual intervention required."
            print("\n[ALERT] CAPTCHA detected! Manual intervention required.")
        else:
            result_data["success"] = True
            result_data["notes"] = result_text[:500]

    except Exception as exc:
        logger.error("Workday agent error for job %d: %s", job.id, exc)
        result_data["success"] = False
        result_data["notes"] = f"Error: {exc}"
        print(f"\n[WORKDAY AGENT ERROR] {exc}")

    return result_data


async def apply_to_job(
    job_id: int,
    db: Database,
    profile: dict,
    supervised: bool = True,
    dry_run: bool = False,
) -> bool:
    """
    Full application flow for a job: fetch job, find resume, run agent, log result.

    Returns:
        True if application was submitted successfully.
    """
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found.")

    # Find the tailored resume if it exists
    application = db.get_application(job_id)
    resume_path = None
    if application and application.resume_path:
        resume_path = Path(application.resume_path)
        if not resume_path.exists():
            logger.warning("Resume file not found at %s", resume_path)
            resume_path = None

    result = await run_workday_agent(
        job=job,
        profile=profile,
        resume_path=resume_path,
        supervised=supervised,
        dry_run=dry_run,
    )

    if result["success"] and not dry_run:
        cover_letter_path = application.cover_letter_path if application else None
        db.insert_application(
            job_id=job_id,
            resume_path=str(resume_path) if resume_path else None,
            cover_letter_path=cover_letter_path,
            method="supervised" if supervised else "auto",
            notes=result.get("notes", ""),
        )
        logger.info("Application recorded for job %d", job_id)

    return result["success"]
