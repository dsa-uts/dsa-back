from typing import List
from ... import models
from datetime import datetime
from typing import List
import pytz
from fastapi import HTTPException
from sqlalchemy.orm import Session
from pytz import timezone
from . import assignments
from ...dependencies import get_db
from fastapi import Depends
import os


def is_active_assignment(
    assignment: models.Assignment, current_time: datetime, tz: str = "Asia/Tokyo"
) -> bool:
    tz_info = pytz.timezone(tz)
    result = (
        assignment.start_date.astimezone(tz_info)
        <= current_time.astimezone(tz_info)
        <= assignment.end_date.astimezone(tz_info)
    )
    return result


def filter_assignments_by_time(
    assignments: List[models.Assignment], current_time: datetime, tz: str = "Asia/Tokyo"
) -> List[models.Assignment]:
    tz_info = pytz.timezone(tz)
    filtered_assignments = []
    for assignment in assignments:
        if is_active_assignment(assignment, current_time, tz):
            filtered_assignments.append(assignment)
    return filtered_assignments


def validate_assignment(id: int, is_admin: bool = False, db: Session = Depends(get_db)):
    assignment = assignments.get_assignment(db, id=id)
    is_active = is_active_assignment(assignment, datetime.now(timezone("Asia/Tokyo")))
    if assignment is None or not (is_admin or is_active):
        raise HTTPException(status_code=404, detail="Not Found")


def check_path_exists(file_path: str) -> bool:
    return file_path is not None and os.path.exists(file_path)


def read_text_file(file_path: str) -> str:
    with open(file_path, "r") as f:
        text = f.read()
    return text
