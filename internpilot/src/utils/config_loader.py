"""
Config loader: reads YAML config files and .env secrets.
"""
import os
import logging
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Resolve the project root (internpilot/ directory)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"


def load_env() -> None:
    """Load .env file from config directory (or project root as fallback)."""
    env_path = CONFIG_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.debug("Loaded .env from %s", env_path)
    else:
        # Fallback: look in project root
        root_env = PROJECT_ROOT / ".env"
        if root_env.exists():
            load_dotenv(root_env)
            logger.debug("Loaded .env from %s", root_env)
        else:
            logger.warning(
                "No .env file found. Expected at %s. "
                "Copy config/.env.example to config/.env and fill in values.",
                env_path,
            )


def _load_yaml(path: Path) -> Any:
    """Load and parse a YAML file, with error reporting."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
            logger.debug("Loaded YAML from %s", path)
            return data
    except FileNotFoundError:
        logger.error("Config file not found: %s", path)
        raise
    except yaml.YAMLError as exc:
        logger.error("YAML parse error in %s: %s", path, exc)
        raise


def load_profile() -> dict:
    return _load_yaml(CONFIG_DIR / "profile.yaml")


def load_employers() -> dict:
    return _load_yaml(CONFIG_DIR / "employers.yaml")


def load_searches() -> dict:
    return _load_yaml(CONFIG_DIR / "searches.yaml")


def get_anthropic_api_key() -> str:
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY is not set. "
            "Add it to config/.env or your environment."
        )
    return key


def get_google_credentials_path() -> Path:
    path_str = os.getenv("GOOGLE_CREDENTIALS_PATH", "")
    if not path_str:
        raise EnvironmentError(
            "GOOGLE_CREDENTIALS_PATH is not set. "
            "Add it to config/.env or your environment."
        )
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(
            f"Google credentials file not found: {path}"
        )
    return path


def get_google_token_path() -> Path:
    path_str = os.getenv("GOOGLE_TOKEN_PATH", str(CONFIG_DIR / "token.json"))
    return Path(path_str)


def scan_for_placeholders(data, path: str = "") -> list[str]:
    """
    Recursively scan a config dict/list for unfilled [FILL IN] placeholders.
    Returns a list of dot-paths where placeholders were found.
    """
    found = []
    if isinstance(data, dict):
        for key, value in data.items():
            child_path = f"{path}.{key}" if path else key
            found.extend(scan_for_placeholders(value, child_path))
    elif isinstance(data, list):
        for i, item in enumerate(data):
            found.extend(scan_for_placeholders(item, f"{path}[{i}]"))
    elif isinstance(data, str) and "[FILL IN]" in data:
        found.append(path)
    return found


def validate_configs() -> list[str]:
    """
    Validate all YAML config files and env vars.
    Returns a list of error/warning strings (empty means all OK).
    """
    issues = []

    # Profile — deep scan for any remaining [FILL IN] placeholders
    try:
        profile = load_profile()
        placeholders = scan_for_placeholders(profile)
        for p in placeholders:
            issues.append(f"profile.yaml: {p} still has [FILL IN] placeholder")
        if not profile.get("education"):
            issues.append("profile.yaml: no education entries found")
        if not profile.get("experience"):
            issues.append("profile.yaml: no experience entries found")
    except Exception as exc:
        issues.append(f"profile.yaml: failed to load ({exc})")

    # Employers
    try:
        employers = load_employers()
        for emp in employers.get("employers", []):
            if "[FILL IN]" in str(emp.get("workday_url", "")):
                issues.append(
                    f"employers.yaml: {emp['name']} workday_url needs to be filled in"
                )
    except Exception as exc:
        issues.append(f"employers.yaml: failed to load ({exc})")

    # Searches
    try:
        searches = load_searches()
        if not searches.get("searches"):
            issues.append("searches.yaml: no search entries found")
    except Exception as exc:
        issues.append(f"searches.yaml: failed to load ({exc})")

    # Env
    if not os.getenv("ANTHROPIC_API_KEY"):
        issues.append(".env: ANTHROPIC_API_KEY is not set")
    if not os.getenv("GOOGLE_CREDENTIALS_PATH"):
        issues.append(".env: GOOGLE_CREDENTIALS_PATH is not set (required for email outreach)")

    return issues
