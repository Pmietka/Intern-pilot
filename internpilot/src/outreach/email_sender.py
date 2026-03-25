"""
Gmail API email sender.
Handles authentication and sending outreach/follow-up emails.
"""
import base64
import logging
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def get_gmail_service():
    """
    Authenticate and return a Gmail API service object.
    Uses OAuth2 with a credentials.json file (Desktop app flow).
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        logger.error(
            "Google API libraries not installed. "
            "Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )
        raise

    from ..utils.config_loader import get_google_credentials_path, get_google_token_path

    token_path = get_google_token_path()
    creds = None

    # Load saved token
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as exc:
            logger.warning("Failed to load token file: %s", exc)

    # Refresh or re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                logger.warning("Token refresh failed: %s. Re-authenticating.", exc)
                creds = None

        if not creds:
            credentials_path = get_google_credentials_path()
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for future use
        with open(str(token_path), "w") as token_file:
            token_file.write(creds.to_json())
        logger.info("Gmail token saved to %s", token_path)

    service = build("gmail", "v1", credentials=creds)
    return service


def send_email(
    to: str,
    subject: str,
    body: str,
    from_email: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """
    Send an email via Gmail API.

    Args:
        to: Recipient email address.
        subject: Email subject.
        body: Email body text.
        from_email: Sender email (uses authenticated account if None).
        dry_run: If True, print email instead of sending.

    Returns:
        True if sent successfully.
    """
    if dry_run:
        print(f"\n[DRY RUN] Would send email:")
        print(f"  To: {to}")
        print(f"  Subject: {subject}")
        print(f"  Body:\n{body}\n")
        return True

    try:
        service = get_gmail_service()

        message = MIMEMultipart("alternative")
        message["to"] = to
        message["subject"] = subject
        if from_email:
            message["from"] = from_email

        text_part = MIMEText(body, "plain", "utf-8")
        message.attach(text_part)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_result = service.users().messages().send(
            userId="me",
            body={"raw": raw},
        ).execute()

        logger.info("Email sent to %s (message id: %s)", to, send_result.get("id"))
        return True

    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)
        return False


def send_outreach_email(
    outreach_id: int,
    db,
    profile: dict,
    dry_run: bool = False,
) -> bool:
    """
    Send a drafted outreach email and mark it as sent in the DB.

    Args:
        outreach_id: ID of the outreach record in DB.
        db: Database instance.
        profile: Candidate profile dict.
        dry_run: If True, simulate without sending.

    Returns:
        True if sent (or dry run succeeded).
    """
    from ..tracker.models import Outreach

    with db._conn() as conn:
        row = conn.execute(
            "SELECT * FROM outreach WHERE id = ?", (outreach_id,)
        ).fetchone()

    if not row:
        raise ValueError(f"Outreach record {outreach_id} not found.")

    outreach = Outreach.from_row(dict(row))

    if not outreach.contact_email:
        logger.error("No contact email for outreach %d", outreach_id)
        return False

    if not outreach.email_body or not outreach.email_subject:
        logger.error("Email content missing for outreach %d", outreach_id)
        return False

    # Append professional signature
    personal = profile.get("personal", {})
    signature = (
        f"\n\n--\n"
        f"{personal.get('first_name', '')} {personal.get('last_name', '')}\n"
        f"DePaul University, Finance, Class of 2027\n"
        f"Keeley Scholars Program\n"
        f"{personal.get('email', '')}\n"
        f"{personal.get('phone', '')}"
    )
    full_body = outreach.email_body + signature

    success = send_email(
        to=outreach.contact_email,
        subject=outreach.email_subject,
        body=full_body,
        dry_run=dry_run,
    )

    if success and not dry_run:
        db.mark_outreach_sent(outreach_id)

    return success
