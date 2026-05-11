"""
Alert service for 5G Network Slicing
Handles email notifications
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


class AlertService:
    """Service for sending alerts via email (SMTP)."""

    def __init__(self):
        from config import (
            ALERT_EMAIL,
            SMTP_SERVER,
            SMTP_PORT,
            SMTP_USERNAME,
            SMTP_PASSWORD,
        )

        self.alert_email = ALERT_EMAIL
        self.smtp_server = SMTP_SERVER
        self.smtp_port = SMTP_PORT
        self.smtp_username = SMTP_USERNAME
        self.smtp_password = SMTP_PASSWORD

    def send_email_alert(self, subject, message, severity="INFO"):
        """Send email alert"""
        if not self.alert_email or not self.smtp_username:
            print("Email not configured")
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = self.smtp_username
            msg["To"] = self.alert_email
            msg["Subject"] = f"[{severity}] {subject}"

            body = f"""
            Alert Details:
            - Severity: {severity}
            - Timestamp: {datetime.now().isoformat()}
            - Message: {message}
            """

            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)

            print(f"Email alert sent: {subject}")
            return True

        except Exception as e:
            print(f"Failed to send email: {e}")
            return False


# Singleton instance
alert_service = AlertService()
