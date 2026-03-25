"""
Cross-platform desktop notification system.
Falls back gracefully to logging if desktop notifications are unavailable.
"""
import logging
import sys

logger = logging.getLogger(__name__)


def notify(title: str, message: str, urgency: str = "normal") -> None:
    """
    Send a desktop notification with graceful fallback to logging.

    Args:
        title: Notification title.
        message: Notification body.
        urgency: "low", "normal", or "critical".
    """
    log_fn = logger.warning if urgency == "critical" else logger.info
    log_fn("[NOTIFY] %s: %s", title, message)

    if sys.platform == "win32":
        _notify_windows(title, message)
    elif sys.platform == "darwin":
        _notify_macos(title, message)
    else:
        _notify_linux(title, message, urgency)


def _notify_windows(title: str, message: str) -> None:
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message[:255],
            app_name="InternPilot",
            timeout=10,
        )
    except Exception:
        pass  # Already logged above


def _notify_macos(title: str, message: str) -> None:
    try:
        import subprocess
        safe_title = title.replace('"', '\\"')
        safe_msg = message.replace('"', '\\"')
        subprocess.run(
            ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}"'],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass


def _notify_linux(title: str, message: str, urgency: str = "normal") -> None:
    try:
        import subprocess
        subprocess.run(
            ["notify-send", "-u", urgency, title, message],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass
