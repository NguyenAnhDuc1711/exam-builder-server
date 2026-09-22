import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_otp_email(to_email: str, otp: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = "Your password reset code"
    msg["From"] = settings.SMTP_FROM_ADDRESS
    msg["To"] = to_email
    msg.set_content(f"Your code is {otp}. It expires in 5 minutes.")

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("otp_email_sent", extra={"to": to_email})
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("otp_email_failed", extra={"to": to_email, "error": str(exc)})

