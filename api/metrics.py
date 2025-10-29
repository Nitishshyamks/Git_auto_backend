from typing import Dict, List
from api.models import ProjectTask

def compute_metrics(tasks: List[ProjectTask]) -> Dict[str, int]:
    """
    Returns KPI buckets that drive the dashboard.
    You can extend this for: avg cycle time, reopen rate, etc.
    """

    def has(val, kw):
        return bool(val) and kw in val.lower()

    total = len(tasks)
    completed = len([t for t in tasks if has(t.status, "done")])
    in_progress = len([t for t in tasks if has(t.status, "progress")])
    blocked = len([t for t in tasks if has(t.status, "block")])
    todo = len([t for t in tasks if has(t.status, "todo") or has(t.status, "to do")])

    return {
        "total_tasks": total,
        "completed": completed,
        "in_progress": in_progress,
        "blocked": blocked,
        "todo": todo,
    }
