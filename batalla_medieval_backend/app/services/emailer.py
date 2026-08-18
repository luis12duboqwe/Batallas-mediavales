import logging
import smtplib
from email.mime.text import MIMEText

from ..config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _smtp_details_provided() -> bool:
    return bool(settings.smtp_host and settings.from_email)


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send an account email through the configured SMTP server.

    The caller decides whether delivery failure is fatal for the current
    environment. This function never logs message bodies or credentials.
    """

    if not _smtp_details_provided():
        return False

    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = settings.from_email
    message["To"] = to_email

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_use_starttls:
                server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.from_email, [to_email], message.as_string())
        return True
    except Exception:
        logger.exception("SMTP delivery failed for account email")
        return False
