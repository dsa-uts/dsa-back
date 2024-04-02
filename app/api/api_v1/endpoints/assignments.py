from ....crud.db import assignments, utils, users
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ....dependencies import get_db
from .... import schemas
from typing import List
from datetime import datetime
from pytz import timezone
from fastapi import UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
import shutil
import uuid
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO)

router = APIRouter()


@router.get("/", response_model=List[schemas.AssignmentBase])
def read_assignments(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: Optional[schemas.UserBase] = Depends(users.get_current_user),
) -> List[schemas.AssignmentBase]:
    assignments_list = assignments.get_assignments(db, skip=skip, limit=limit)
    if user is None or user.disabled:
        current_time = datetime.now(timezone("Asia/Tokyo"))
        assignments_list = utils.filter_assignments_by_time(
            assignments_list, current_time
        )
    return assignments_list


@router.get("/{id}", response_model=List[schemas.SubAssignmentBase])
def read_sub_assignments(
    id: int,
    db: Session = Depends(get_db),
    user: Optional[schemas.UserBase] = Depends(users.get_current_user),
):
    if user is None or user.disabled:
        utils.validate_assignment(id, False, db)
    else:
        utils.validate_assignment(id, True, db)
    sub_assignments_list = assignments.get_sub_assignments(db, id=id)
    return sub_assignments_list


@router.get("/{id}/{sub_id}", response_model=schemas.SubAssignmentDetail)
def read_sub_assignment(
    id: int,
    sub_id: int,
    db: Session = Depends(get_db),
    user: Optional[schemas.UserBase] = Depends(users.get_current_user),
):
    if user is None or user.disabled:
        utils.validate_assignment(id, False, db)
    else:
        utils.validate_assignment(id, True, db)
    sub_assignment = assignments.get_sub_assignment(db, id=id, sub_id=sub_id)
    detail = schemas.SubAssignmentDetail(
        id=sub_assignment.id,
        sub_id=sub_assignment.sub_id,
        title=sub_assignment.title,
        makefile=sub_assignment.makefile,
        required_file_name=sub_assignment.required_file_name,
        test_file_name=sub_assignment.test_file_name,
        test_input=sub_assignment.test_input_dir,
    )
    if utils.check_path_exists(sub_assignment.test_output_dir):
        combined_path = os.path.join(
            sub_assignment.test_output_dir, sub_assignment.test_case_name
        )
        detail.test_output = utils.read_text_file(combined_path)
    if utils.check_path_exists(sub_assignment.test_program_dir):
        combined_path = os.path.join(
            sub_assignment.test_program_dir, sub_assignment.test_program_name
        )
        detail.test_program = utils.read_text_file(combined_path)
    return detail


@router.post("/upload/{id}/{sub_id}")
async def upload_file(id: int, sub_id: int, file: UploadFile = File(...)):
    upload_dir = "uploadedFiles"
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(upload_dir, unique_filename)
    print(id, sub_id, file_path)
    try:
        os.makedirs(upload_dir, exist_ok=True)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return JSONResponse(
            status_code=200, content={"filename": unique_filename, "result": "success"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {e}")
