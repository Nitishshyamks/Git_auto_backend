import os
import csv
import httpx
import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List
from dotenv import load_dotenv

from api.database import SessionLocal
from api.repository import upsert_tasks

# -------------------------------------------------------------------------
# Environment + Setup
# -------------------------------------------------------------------------
load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ORG = os.getenv("ORG")
PROJECTS_RAW = os.getenv("PROJECT")  # e.g. "6,810"
GITHUB_API = os.getenv("GITHUB_GRAPHQL_URL", "https://api.github.com/graphql")

PROJECT_NUMBERS = [int(p.strip()) for p in PROJECTS_RAW.split(",") if p.strip()]
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# GraphQL Query
# -------------------------------------------------------------------------
QUERY = """
query($org: String!, $number: Int!, $after: String) {
  organization(login: $org) {
    projectV2(number: $number) {
      id
      title
      number
      items(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          content {
            __typename
            ... on Issue {
              title
              body
              url
              createdAt
              updatedAt
              author { login }
              assignees(first: 50) { nodes { login } }
              repository { name }
              labels(first: 20) { nodes { name } }
            }
            ... on PullRequest {
              title
              body
              url
              createdAt
              updatedAt
              author { login }
              assignees(first: 50) { nodes { login } }
              repository { name }
              labels(first: 20) { nodes { name } }
            }
            ... on DraftIssue {
              title
              body
              createdAt
              updatedAt
              assignees(first: 50) { nodes { login } }
            }
          }
          fieldValues(first: 50) {
            nodes {
              __typename
              ... on ProjectV2ItemFieldTextValue {
                field { ... on ProjectV2FieldCommon { name } }
                text
              }
              ... on ProjectV2ItemFieldDateValue {
                field { ... on ProjectV2FieldCommon { name } }
                date
              }
              ... on ProjectV2ItemFieldNumberValue {
                field { ... on ProjectV2FieldCommon { name } }
                number
              }
              ... on ProjectV2ItemFieldSingleSelectValue {
                field { ... on ProjectV2FieldCommon { name } }
                name
              }
              ... on ProjectV2ItemFieldIterationValue {
                field { ... on ProjectV2FieldCommon { name } }
                title
              }
            }
          }
        }
      }
    }
  }
}
"""

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
def _norm(s: str | None) -> str:
    return (s or "").strip()

def _parse_ts(ts: str | None):
    """Parse ISO8601 timestamps safely into UTC-aware datetime."""
    if not ts:
        return None
    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc)

def _extract_project_fields(nodes: List[Dict[str, Any]]) -> Dict[str, str]:
    """Extract normalized field values like status, priority, iteration, etc."""
    if not nodes:
        return {}
    wanted = {
        "status": "status",
        "priority": "priority",
        "iteration": "iteration",
        "due date": "due_date",
    }
    out: Dict[str, str] = {}
    for node in nodes:
        field_name = _norm((node.get("field") or {}).get("name", "")).lower()
        val = (
            node.get("text")
            or node.get("date")
            or node.get("name")
            or node.get("title")
            or (str(node.get("number")) if node.get("number") is not None else "")
        )
        if field_name in wanted and val:
            out[wanted[field_name]] = val.strip()
    return out

def _row_from_node(org: str, meta: Dict[str, Any], node: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten one ProjectV2 node into a DB-ready row dict."""
    content = node.get("content") or {}
    assignees = ", ".join(
        a["login"] for a in content.get("assignees", {}).get("nodes", []) if a.get("login")
    )
    labels = ", ".join(
        l["name"] for l in content.get("labels", {}).get("nodes", []) if l.get("name")
    )
    fields = _extract_project_fields(node.get("fieldValues", {}).get("nodes", []))

    return {
        "organization": org,
        "project_name": meta["title"],
        "project_number": meta["number"],
        "project_item_id": node["id"],
        "item_type": content.get("__typename", ""),
        "repo": (content.get("repository") or {}).get("name", ""),
        "issue_pr_number": "",
        "task_title": (content.get("title") or "").strip(),
        "task_description": (content.get("body") or "").strip(),
        "assignees": assignees,
        "assigned_by": (content.get("author") or {}).get("login", ""),
        "status": fields.get("status", "Unknown"),
        "priority": fields.get("priority", "Normal"),
        "labels": labels,
        "milestone": "",
        "iteration": fields.get("iteration", ""),
        "due_date": fields.get("due_date", ""),
        "created_at": _parse_ts(content.get("createdAt")),
        "updated_at": _parse_ts(content.get("updatedAt")),
        "url": content.get("url", ""),
    }

def _write_csv(org: str, project_name: str, rows: List[dict]):
    if not rows:
        return
    safe_name = project_name.replace(" ", "_").replace("/", "_")
    out_path = os.path.join(DATA_DIR, f"{org}_{safe_name}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    logger.info(f"[CSV] Wrote {len(rows)} rows → {out_path}")

# -------------------------------------------------------------------------
# Fetch + Sync Logic
# -------------------------------------------------------------------------
async def _fetch_one_project(client: httpx.AsyncClient, org: str, number: int):
    """Fetch all items from one GitHub project (paginated)."""
    after = None
    all_items: List[Dict[str, Any]] = []
    meta = None

    while True:
        resp = await client.post(
            GITHUB_API,
            json={"query": QUERY, "variables": {"org": org, "number": number, "after": after}},
            timeout=60,
        )

        if resp.status_code == 401:
            raise RuntimeError("❌ Unauthorized: Check GITHUB_TOKEN or access rights.")
        elif resp.status_code == 403:
            logger.warning("[WARN] Rate limit reached. Sleeping 60s...")
            await asyncio.sleep(60)
            continue

        resp.raise_for_status()
        payload = resp.json()

        org_data = payload.get("data", {}).get("organization")
        if not org_data:
            raise RuntimeError(f"No organization data for {org}")

        proj = org_data.get("projectV2")
        if not proj:
            raise RuntimeError(f"Project #{number} not found or no access")

        if not meta:
            meta = {"title": proj["title"], "number": proj["number"]}

        items = proj["items"]["nodes"] or []
        all_items.extend(items)

        page_info = proj["items"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        after = page_info["endCursor"]
        await asyncio.sleep(0.25)  # rate-limiting safety

    return meta, all_items

async def sync_all_projects():
    """Main entry point: fetch all GitHub projects, save CSVs, upsert to NeonDB."""
    if not GITHUB_TOKEN or not ORG or not PROJECT_NUMBERS:
        raise RuntimeError("Missing GITHUB_TOKEN / ORG / PROJECT in .env")

    logger.info("🚀 Syncing GitHub → NeonDB...")
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/json"}

    async with httpx.AsyncClient(headers=headers) as client:
        async with SessionLocal() as db:
            for pnum in PROJECT_NUMBERS:
                logger.info(f"[SYNC] Fetching project {ORG} #{pnum}")
                meta, items = await _fetch_one_project(client, ORG, pnum)

                rows = [_row_from_node(ORG, meta, n) for n in items]
                _write_csv(ORG, meta["title"], rows)
                await upsert_tasks(db, rows)

    logger.info("[DONE] All GitHub projects synced successfully!")

# -------------------------------------------------------------------------
# Run Manually
# -------------------------------------------------------------------------
if __name__ == "__main__":
    asyncio.run(sync_all_projects())
