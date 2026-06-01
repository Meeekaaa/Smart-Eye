import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from utils import config

logger = logging.getLogger(__name__)


def _send_email_with_config(to_address, subject, body, smtp, html=False):
    logger.debug(
        "Email send requested to=%s host=%s port=%s tls=%s user_set=%s pass_set=%s",
        to_address,
        smtp.get("host"),
        smtp.get("port"),
        smtp.get("tls", True),
        bool(smtp.get("user")),
        bool(smtp.get("password")),
    )
    if not smtp["host"] or not to_address:
        logger.warning("Email send skipped: missing host or recipient (host_set=%s to_set=%s)", bool(smtp.get("host")), bool(to_address))
        return False
    msg = MIMEMultipart()
    msg["From"] = smtp["user"]
    msg["To"] = to_address
    msg["Subject"] = subject
    content_type = "html" if html else "plain"
    msg.attach(MIMEText(body, content_type))
    try:
        server = smtplib.SMTP(smtp["host"], int(smtp["port"]))
        server.ehlo()
        if smtp.get("tls", True):
            server.starttls()
            server.ehlo()
        if smtp["user"] and smtp["password"]:
            server.login(smtp["user"], smtp["password"])
        server.sendmail(smtp["user"], [to_address], msg.as_string())
        server.quit()
        logger.info("Email sent successfully to %s via %s:%s", to_address, smtp.get("host"), smtp.get("port"))
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to_address)
        return False


def send_email_alert(to_address, subject, body, html=False):
    return _send_email_with_config(to_address, subject, body, config.smtp_config(), html=html)


def test_email(to_address):
    return send_email_alert(
        to_address,
        "SmartEye Test Notification",
        "This is a test email from SmartEye.\nIf you received this, email notifications are configured correctly.",
    )


def test_email_with_config(to_address, smtp):
    return _send_email_with_config(
        to_address,
        "SmartEye Test Notification",
        "This is a test email from SmartEye.\nIf you received this, email notifications are configured correctly.",
        smtp,
    )
