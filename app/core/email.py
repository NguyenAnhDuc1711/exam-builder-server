"""Synchronous OTP email sender (AD-2, FR-8, T001).

Synchronous by design — it is only ever invoked as a FastAPI
``BackgroundTasks`` callable, and Starlette runs sync background callables
in a threadpool, so this never blocks the event loop.

``logger.info`` / ``logger.error`` must be at a level ``caplog`` can assert
on in tests (FR-8's "outcome is logged" acceptance criterion).
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_otp_email(to_email: str, otp: str) -> None:
    """Build and send the OTP email via SMTP + STARTTLS.

    Logs success or failure — never raises, so a broken relay doesn't crash
    the background task runner.
    """
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

