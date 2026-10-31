import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

class EmailDispatchResult:
    def __init__(self, success: bool, message: str = "", error: Optional[str] = None):
        self.success = success
        self.message = message
        self.error = error

    def __repr__(self):
        return f"<EmailDispatchResult success={self.success} message='{self.message}'>"

class SMTPEmailService:
    def __init__(self, is_mock: bool = False):
        self.is_mock = is_mock
        self.mock_sent_emails: List[Dict[str, Any]] = []

    def send_lesson_email(
        self,
        recipient_email: str,
        subject: str,
        text_content: str,
        html_content: str,
    ) -> EmailDispatchResult:
        """
        Transmits a multi-part HTML & plain-text lesson email via SMTP.
        Falls back to safe mock logging if DRY_RUN is active, is_mock is True, or credentials are placeholders.
        """
        recipient_clean = recipient_email.strip().lower()

        # Check if dry-run or mock mode is needed
        if self.is_mock or settings.DRY_RUN or not settings.is_smtp_configured:
            logger.info(
                f"[MOCK/DRY-RUN SMTP] Email prepared for {recipient_clean}. Subject: '{subject}'"
            )
            record = {
                "to": recipient_clean,
                "subject": subject,
                "text": text_content,
                "html": html_content,
            }
            self.mock_sent_emails.append(record)
            return EmailDispatchResult(
                success=True,
                message=f"[Mock/Dry-Run] Email to {recipient_clean} recorded successfully.",
            )

        # Real SMTP Transmission
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
            msg["To"] = recipient_clean

            # Attach plain-text fallback first, then HTML part
            part_text = MIMEText(text_content, "plain", "utf-8")
            part_html = MIMEText(html_content, "html", "utf-8")
            msg.attach(part_text)
            msg.attach(part_html)

            logger.info(f"Connecting to SMTP server {settings.SMTP_HOST}:{settings.SMTP_PORT}...")

            if settings.SMTP_USE_SSL:
                server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT)
            else:
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=settings.SMTP_TIMEOUT)
                if settings.SMTP_USE_TLS:
                    server.starttls()

            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

            server.sendmail(settings.SMTP_FROM_EMAIL, [recipient_clean], msg.as_string())
            server.quit()

            logger.info(f"Successfully delivered email via SMTP to {recipient_clean}.")
            return EmailDispatchResult(
                success=True,
                message=f"Delivered via SMTP to {recipient_clean}.",
            )

        except Exception as e:
            err_msg = f"SMTP transmission to {recipient_clean} failed: {e}"
            logger.error(err_msg, exc_info=True)
            return EmailDispatchResult(
                success=False,
                message=err_msg,
                error=str(e),
            )

email_service = SMTPEmailService()
