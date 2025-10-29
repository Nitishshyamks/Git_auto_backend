import os
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

SENDER = os.getenv("EMAIL_SENDER")
PASSWORD = os.getenv("EMAIL_PASSWORD")
RECIPIENTS = os.getenv("EMAIL_RECEIVER", "")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "https://dashboard.example.com")

def send_dashboard_ready_email():
    now_str = datetime.now().strftime("%d %b %Y, %I:%M %p")

    subject = "Weekly Project Dashboard is Ready"
    body = f"""
Hello Team,

Your weekly engineering dashboard has been refreshed.

Dashboard: {DASHBOARD_URL}
Synced At: {now_str}

– Nucleus Automation
"""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = SENDER
    msg["To"] = RECIPIENTS

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(SENDER, PASSWORD)
            s.sendmail(
                SENDER,
                [r.strip() for r in RECIPIENTS.split(",") if r.strip()],
                msg.as_string(),
            )
        print("[EMAIL] Dashboard notification sent")
    except Exception as e:
        print(f"[EMAIL] Error sending notification: {e}")
