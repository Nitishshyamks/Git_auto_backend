import os
import csv
import httpx
import asyncio
from datetime import datetime
from typing import Any, Dict, List
from dotenv import load_dotenv

from api.database import SessionLocal
from api.repository import upsert_tasks

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
ORG = os.getenv("ORG")
PROJECTS_RAW = os.getenv("PROJECT")  # e.g. "6,810"
GITHUB_API = os.getenv("GITHUB_GRAPHQL_URL", "https://api.github.com/graphql")

# Parse all project numbers from env
PROJECT_NUMBERS = [int(p.strip()) for p in PROJECTS_RAW.split(",") if p.strip()]

# Where CSV backups will be written
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

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
        }
      }
    }
  }
}
"""

async def _fetch_one_project(client: httpx.AsyncClient, org: str, number: int):
    """
    Fetches one GitHub ProjectV2 board (all items, paginated).
    Returns (project_meta, items_list).
    """
    after = None
    all_items: List[Dict[str, Any]] = []
    project_meta = None

    while True:
        resp = await client.post(
            GITHUB_API,
            json={
                "query": QUERY,
                "variables": {
                    "org": org,
                    "number": number,
                    "after": after,
                },
            },
            timeout=40,
        )
        resp.raise_for_status()

        payload = resp.json()
        org_data = payload.get("data", {}).get("organization")
        if not org_data:
            raise RuntimeError(f"No organization data for {org} (check ORG / token scope)")

        proj = org_data.get("projectV2")
        if not proj:
            raise RuntimeError(f"Project {number} not found or access denied")

        if not project_meta:
            project_meta = {
                "title": proj["title"],
                "number": proj["number"],
            }

        nodes = proj["items"]["nodes"] or []
        all_items.extend(nodes)

        page_info = proj["items"]["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        after = page_info["endCursor"]

        # be nice to GitHub API rate limits
        await asyncio.sleep(0.25)

    return project_meta, all_items

def _parse_ts(ts: str | None):
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))

def _row_from_node(org: str, meta: Dict[str, Any], node: Dict[str, Any]) -> Dict[str, Any]:
    content = node.get("content") or {}
    assignees = ", ".join(
        a["login"] for a in content.get("assignees", {}).get("nodes", []) if a.get("login")
    )
    labels = ", ".join(
        l["name"] for l in content.get("labels", {}).get("nodes", []) if l.get("name")
    )

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
        "status": "",        # you can extend this: map custom project fields
        "priority": "",
        "labels": labels,
        "milestone": "",
        "iteration": "",
        "due_date": "",
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
    print(f"[CSV] wrote {len(rows)} rows -> {out_path}")

async def sync_all_projects():
    """
    Main sync job:
    - Fetches every configured project board from GitHub
    - Writes CSV backups
    - UPSERTs into NeonDB
    """
    if not GITHUB_TOKEN or not ORG or not PROJECT_NUMBERS:
        raise RuntimeError("Missing GITHUB_TOKEN / ORG / PROJECT env values")

    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}

    async with httpx.AsyncClient(headers=headers) as client:
        async with SessionLocal() as db:
            for pnum in PROJECT_NUMBERS:
                print(f"[SYNC] Fetching project {ORG} #{pnum}")
                meta, items = await _fetch_one_project(client, ORG, pnum)

                # normalize each item node into DB-ready dict
                rows = [_row_from_node(ORG, meta, n) for n in items]

                # optional analytics backup
                _write_csv(ORG, meta["title"], rows)

                # write/upsert into NeonDB
                await upsert_tasks(db, rows)

    print("[SYNC] All projects synced successfully.")

if __name__ == "__main__":
    asyncio.run(sync_all_projects())
