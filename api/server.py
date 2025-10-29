from fastapi import FastAPI, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from api.database import get_db, init_db, engine, Base
from api.metrics import compute_metrics
from api.repository import (
    get_all_tasks,
    get_tasks_for_project,
    get_all_project_names,
)

from services.github_fetcher import sync_all_projects
from services.email_notifier import send_dashboard_ready_email

app = FastAPI(title="Nucleus Productivity API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in prod: ["https://your-frontend-url"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    # make sure DB tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[STARTUP] DB ready.")

@app.get("/")
async def health():
    return {
        "status": "OK",
        "time": datetime.utcnow().isoformat(),
        "message": "Nucleus Productivity API running",
    }

@app.post("/trigger-update")
async def trigger_update(background_tasks: BackgroundTasks):
    """
    Your Render/Vercel cron job or internal ops can call this.
    It will:
    1. Sync GitHub → NeonDB
    2. Send summary email
    """
    background_tasks.add_task(sync_all_projects)
    background_tasks.add_task(send_dashboard_ready_email)
    return {"status": "started", "message": "sync + email queued"}

@app.get("/metrics")
async def metrics(
    project: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    if project:
        tasks = await get_tasks_for_project(db, project)
    else:
        tasks = await get_all_tasks(db)

    data = compute_metrics(tasks)
    return {
        "project": project or "All",
        "metrics": data,
        "last_updated": datetime.utcnow().isoformat(),
    }

@app.get("/projects")
async def projects(db: AsyncSession = Depends(get_db)):
    names = await get_all_project_names(db)
    return {"projects": names}

@app.get("/tasks")
async def tasks(
    db: AsyncSession = Depends(get_db),
    project: str | None = None
):
    if project:
        rows = await get_tasks_for_project(db, project)
    else:
        rows = await get_all_tasks(db)

    # convert ORM rows → dicts for frontend table
    out = []
    for r in rows:
        out.append({
            "organization": r.organization,
            "project_name": r.project_name,
            "project_number": r.project_number,
            "project_item_id": r.project_item_id,
            "task_title": r.task_title,
            "assignees": r.assignees,
            "assigned_by": r.assigned_by,
            "status": r.status,
            "priority": r.priority,
            "labels": r.labels,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })
    return {"tasks": out}
