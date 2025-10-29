from sqlalchemy import Column, Integer, String, DateTime, func
from api.database import Base
from sqlalchemy.sql import func

class ProjectTask(Base):
    __tablename__ = "project_tasks"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    organization = Column(String, nullable=False)
    project_name = Column(String, nullable=False)
    project_number = Column(Integer, nullable=False)

    # This is the stable unique key from GitHub ProjectV2 items
    project_item_id = Column(String, unique=True, nullable=False)

    item_type = Column(String)
    repo = Column(String)
    issue_pr_number = Column(String)

    task_title = Column(String)
    task_description = Column(String)

    assignees = Column(String)        # "alice; bob"
    assigned_by = Column(String)      # task creator / author

    status = Column(String)
    priority = Column(String)
    labels = Column(String)
    milestone = Column(String)
    iteration = Column(String)
    due_date = Column(String)

    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

    url = Column(String)

    last_fetched_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
