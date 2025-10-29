"""
Main control script.

Usage:
    python main.py init-db     -> create tables in NeonDB
    python main.py fetch       -> sync GitHub -> DB
    python main.py email       -> send dashboard email
    python main.py serve       -> run FastAPI API server
    python main.py schedule    -> run in-process scheduler (APScheduler)
"""
import sys
import asyncio
import uvicorn
from dotenv import load_dotenv

from api.database import init_db
from services.github_fetcher import sync_all_projects
from services.email_notifier import send_dashboard_ready_email
from services.scheduler import start_scheduler_blocking

load_dotenv()

async def cmd_init_db():
    print("🔧 Initializing DB tables...")
    await init_db()
    print("✅ DB initialized.")

async def cmd_fetch():
    print("📦 Syncing GitHub → NeonDB...")
    await sync_all_projects()
    print("✅ Sync complete.")

def cmd_email():
    print("✉ Sending dashboard email...")
    send_dashboard_ready_email()
    print("✅ Email sent.")

def cmd_serve():
    print("🚀 Starting API server on http://0.0.0.0:8000 ...")
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=True)

def cmd_schedule():
    print("⏰ Starting scheduler (weekly job)...")
    start_scheduler_blocking()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "init-db":
        asyncio.run(cmd_init_db())
    elif command == "fetch":
        asyncio.run(cmd_fetch())
    elif command == "email":
        cmd_email()
    elif command == "serve":
        cmd_serve()
    elif command == "schedule":
        cmd_schedule()
    else:
        print(__doc__)
