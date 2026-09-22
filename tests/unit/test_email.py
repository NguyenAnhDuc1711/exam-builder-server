"""T001 — Unit tests for send_otp_email (FR-8, TRACE-1).

Asserts that send_otp_email sends an email with the correct recipient, subject,
and body, and emits log records assertable by caplog for both success and failure.
"""

import logging
import smtplib
from unittest.mock import MagicMock, patch

from app.core.email import send_otp_email


def test_send_otp_email_success(caplog):
    mock_smtp_instance = MagicMock()
    mock_smtp_instance.__enter__.return_value = mock_smtp_instance

    with patch("app.core.email.smtplib.SMTP", return_value=mock_smtp_instance) as mock_smtp_class:
        with caplog.at_level(logging.INFO, logger="app.core.email"):
            send_otp_email("user@example.com", "123456")

        mock_smtp_class.assert_called_once()
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once()
        mock_smtp_instance.send_message.assert_called_once()

        # Check msg contents
        sent_msg = mock_smtp_instance.send_message.call_args[0][0]
        assert sent_msg["To"] == "user@example.com"
        assert sent_msg["Subject"] == "Your password reset code"
        assert "123456" in sent_msg.get_content()

        # Check caplog assertion (FR-8, TRACE-1)
        assert any(
            record.levelname == "INFO" and record.message == "otp_email_sent"
            for record in caplog.records
        )


def test_send_otp_email_failure_logs_error(caplog):
    mock_smtp_instance = MagicMock()
    mock_smtp_instance.__enter__.return_value = mock_smtp_instance
    mock_smtp_instance.send_message.side_effect = smtplib.SMTPException("Relay error")

    with patch("app.core.email.smtplib.SMTP", return_value=mock_smtp_instance):
        with caplog.at_level(logging.ERROR, logger="app.core.email"):
            # Must not raise an exception
            send_otp_email("user@example.com", "123456")

        assert any(
            record.levelname == "ERROR" and record.message == "otp_email_failed"
            for record in caplog.records
        )
