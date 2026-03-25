"""
Generic Browser Use form-filling logic and helper utilities.
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path(__file__).resolve().parents[2] / "outputs" / "screenshots"


def build_profile_answers(profile: dict) -> dict:
    """
    Flatten the profile YAML into a key-value map that the Workday agent
    can use to answer form fields.

    Returns:
        Dict mapping common Workday field labels to profile values.
    """
    personal = profile.get("personal", {})
    address = personal.get("address", {})
    edu = profile.get("education", [{}])[0]
    screening = profile.get("screening_defaults", {})
    work_auth = profile.get("work_authorization", {})
    demographics = profile.get("demographics", {})

    answers = {
        # Personal
        "first name": personal.get("first_name", ""),
        "last name": personal.get("last_name", ""),
        "email": personal.get("email", ""),
        "email address": personal.get("email", ""),
        "phone": personal.get("phone", ""),
        "phone number": personal.get("phone", ""),
        "mobile phone": personal.get("phone", ""),
        "address line 1": address.get("street", ""),
        "street address": address.get("street", ""),
        "city": address.get("city", ""),
        "state": address.get("state", ""),
        "zip": address.get("zip", ""),
        "zip code": address.get("zip", ""),
        "postal code": address.get("zip", ""),
        "country": address.get("country", "US"),
        "linkedin": personal.get("linkedin", ""),
        "linkedin profile": personal.get("linkedin", ""),
        "linkedin url": personal.get("linkedin", ""),

        # Education
        "school": edu.get("institution", ""),
        "university": edu.get("institution", ""),
        "college": edu.get("institution", ""),
        "institution": edu.get("institution", ""),
        "degree": edu.get("degree", ""),
        "degree type": edu.get("degree", ""),
        "major": edu.get("major", ""),
        "field of study": edu.get("major", ""),
        "gpa": edu.get("gpa", ""),
        "graduation date": edu.get("expected_graduation", ""),
        "expected graduation": edu.get("expected_graduation", ""),
        "graduation year": screening.get("expected_graduation_year", "2027"),

        # Work authorization
        "authorized to work in the us": "Yes" if work_auth.get("authorized_to_work_in_us") else "No",
        "will you require sponsorship": "No" if not work_auth.get("require_sponsorship") else "Yes",
        "require visa sponsorship": "No" if not work_auth.get("require_sponsorship") else "Yes",
        "willing to relocate": "Yes" if work_auth.get("willing_to_relocate") else "No",

        # Screening questions
        "are you 18 or older": "Yes" if screening.get("are_you_18_or_older") else "No",
        "have you previously worked here": "No" if not screening.get("have_you_worked_here_before") else "Yes",
        "how did you hear about us": screening.get("how_did_you_hear", "University Career Services"),
        "how did you hear about this position": screening.get("how_did_you_hear", "University Career Services"),
        "willing to take a drug test": "Yes" if screening.get("willing_to_take_drug_test") else "No",
        "class year": screening.get("class_year", "Sophomore"),
        "current class year": screening.get("class_year", "Sophomore"),

        # Demographics (EEO)
        "gender": demographics.get("gender", "Prefer not to answer"),
        "race": demographics.get("race_ethnicity", "Prefer not to answer"),
        "ethnicity": demographics.get("race_ethnicity", "Prefer not to answer"),
        "veteran status": demographics.get("veteran_status", "No"),
        "disability status": demographics.get("disability_status", "Prefer not to answer"),
    }

    # Remove empty values
    return {k: v for k, v in answers.items() if v and "[FILL IN]" not in str(v)}


def get_screenshot_path(company: str, page_num: int) -> Path:
    """Generate a screenshot path for a given company and page number."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_company = "".join(
        c if c.isalnum() or c in " _" else "" for c in company
    ).strip().replace(" ", "_")
    return SCREENSHOTS_DIR / f"{safe_company}_page_{page_num:02d}.png"
