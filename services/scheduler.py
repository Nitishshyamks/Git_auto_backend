import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from services.github_fetcher import sync_all_projects
from services.email_notifier import send_dashboard_ready_email

TIMEZONE = "Asia/Kolkata"

async def _job():
    await sync_all_projects()
    send_dashboard_ready_email()
    print("[SCHEDULER] Weekly sync + email done")

def start_scheduler_blocking():
    """
    Runs APScheduler in the same process.
    Use this if you're running on your own VM/container.
    On Render/Vercel you can instead call /trigger-update from cron.
    """
    sched = AsyncIOScheduler(timezone=TIMEZONE)
    # Every Friday at 10:00 IST
    sched.add_job(_job, CronTrigger(day_of_week="fri", hour=10, minute=0))
    sched.start()
    print("[SCHEDULER] Started. Running forever...")
    asyncio.get_event_loop().run_forever()
