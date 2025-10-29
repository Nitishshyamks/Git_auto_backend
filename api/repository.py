from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from datetime import datetime, timezone
from typing import List, Dict, Any
from api.models import ProjectTask

async def upsert_tasks(db: AsyncSession, rows: List[Dict[str, Any]]):
    """
    Insert rows if new, update if existing.
    We de-dupe on project_item_id so the same task doesn't get reinserted every week.
    """
    for r in rows:
        q = await db.execute(
            select(ProjectTask).where(ProjectTask.project_item_id == r["project_item_id"])
        )
        existing = q.scalars().first()

        if existing:
            # update in place
            await db.execute(
                update(ProjectTask)
                .where(ProjectTask.project_item_id == r["project_item_id"])
                .values(
                    organization=r["organization"],
                    project_name=r["project_name"],
                    project_number=r["project_number"],
                    item_type=r["item_type"],
                    repo=r["repo"],
                    issue_pr_number=r["issue_pr_number"],
                    task_title=r["task_title"],
                    task_description=r["task_description"],
                    assignees=r["assignees"],
                    assigned_by=r["assigned_by"],
                    status=r["status"],
                    priority=r["priority"],
                    labels=r["labels"],
                    milestone=r["milestone"],
                    iteration=r["iteration"],
                    due_date=r["due_date"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                    url=r["url"],
                    last_fetched_at=datetime.now(timezone.utc),
                )
            )
        else:
            # insert new
            obj = ProjectTask(
                **r,
                last_fetched_at=datetime.now(timezone.utc),
            )
            db.add(obj)

    await db.commit()

async def get_all_tasks(db: AsyncSession):
    q = await db.execute(select(ProjectTask))
    return q.scalars().all()

async def get_tasks_for_project(db: AsyncSession, project_name: str):
    q = await db.execute(
        select(ProjectTask).where(ProjectTask.project_name == project_name)
    )
    return q.scalars().all()

async def get_all_project_names(db: AsyncSession):
    q = await db.execute(select(ProjectTask.project_name).distinct())
    return [row[0] for row in q.all()]
