import smtplib
from email.mime.text import MIMEText

from ..config import get_settings

settings = get_settings()


def _smtp_details_provided() -> bool:
    return bool(settings.smtp_host and settings.from_email)


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send an email using basic SMTP settings.

    Returns True if the email was queued successfully, False otherwise.
    """

    if not _smtp_details_provided():
        return False

    message = MIMEText(body)
    message["Subject"] = subject
    message["From"] = settings.from_email
    message["To"] = to_email

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            if settings.smtp_username and settings.smtp_password:
                server.starttls()
                server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.from_email, [to_email], message.as_string())
        return True
    except Exception:
        # We intentionally swallow errors to avoid breaking gameplay flows if email fails.
        return False
