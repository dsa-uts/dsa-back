from typing import List
from ...classes import models
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
import logging
from ...classes import schemas

logging.basicConfig(level=logging.INFO)


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


def is_active_user(
    user: models.User, current_time: datetime, tz: str = "Asia/Tokyo"
) -> bool:
    tz_info = pytz.timezone(tz)
    current_time_tz = current_time.astimezone(tz_info)
    start_date_check = (
        user.active_start_date is None
        or user.active_start_date.astimezone(tz_info) <= current_time_tz
    )
    end_date_check = (
        user.active_end_date is None
        or current_time_tz <= user.active_end_date.astimezone(tz_info)
    )
    result = start_date_check and end_date_check or user.disabled
    logging.info(f"User: {user.username}, is_active: {result}")
    return result


def filter_assignments_by_time(
    assignments: List[models.Assignment], current_time: datetime, tz: str = "Asia/Tokyo"
) -> List[models.Assignment]:
    filtered_assignments = []
    for assignment in assignments:
        if is_active_assignment(assignment, current_time, tz):
            filtered_assignments.append(assignment)
    return filtered_assignments


def validate_assignment(id: int, is_admin: bool = False, db: Session = Depends(get_db)):
    assignment = assignments.get_assignment(db, id=id)
    if assignment is None:
        logging.error(f"Assignment not found: {id}")
        raise HTTPException(status_code=404, detail="Assignment not found")
    if not is_admin:
        is_active = is_active_assignment(
            assignment, datetime.now(timezone("Asia/Tokyo"))
        )
        if not is_active:
            raise HTTPException(status_code=404, detail="Assignment not active")


def validate_sub_assignment(
    id: int, sub_id: int, is_admin: bool = False, db: Session = Depends(get_db)
):
    sub_assignment = assignments.get_sub_assignment(db, id=id, sub_id=sub_id)
    if sub_assignment is None:
        logging.error(f"SubAssignment not found: {id}, {sub_id}")
        raise HTTPException(status_code=404, detail="SubAssignment not found")
    if not is_admin:
        is_active = is_active_assignment(
            sub_assignment.assignment, datetime.now(timezone("Asia/Tokyo"))
        )
        if not is_active:
            raise HTTPException(status_code=404, detail="SubAssignment not active")
