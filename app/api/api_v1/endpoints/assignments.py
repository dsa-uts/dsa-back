from ....crud.db import assignments, utils
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


router = APIRouter()


@router.get("/", response_model=List[schemas.AssignmentBase])
def read_assignments(
    skip: int = 0,
    limit: int = 10,
    is_admin: bool = False,  # 今後adminを作ることを想定して．
    db: Session = Depends(get_db),
) -> List[schemas.AssignmentBase]:
    assignments_list = assignments.get_assignments(db, skip=skip, limit=limit)
    if not is_admin:
        current_time = datetime.now(timezone("Asia/Tokyo"))
        assignments_list = utils.filter_assignments_by_time(
            assignments_list, current_time
        )
    return assignments_list


@router.get("/{id}", response_model=List[schemas.SubAssignmentBase])
def read_sub_assignments(
    id: int, is_admin: bool = False, db: Session = Depends(get_db)
):
    utils.validate_assignment(id, is_admin, db)
    sub_assignments_list = assignments.get_sub_assignments(db, id=id)
    return sub_assignments_list


@router.get("/{id}/{sub_id}", response_model=schemas.SubAssignmentDetail)
def read_sub_assignment(
    id: int, sub_id: int, is_admin: bool = False, db: Session = Depends(get_db)
):
    utils.validate_assignment(id, is_admin, db)
    sub_assignment = assignments.get_sub_assignment(db, id=id, sub_id=sub_id)
    if utils.check_path_exists(sub_assignment.test_output):
        sub_assignment.test_output = utils.read_text_file(sub_assignment.test_output)
    else:
        sub_assignment.test_output = None
    if utils.check_path_exists(sub_assignment.test_program):
        sub_assignment.test_program = utils.read_text_file(sub_assignment.test_program)
    else:
        sub_assignment.test_program = None
    return sub_assignment


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    upload_dir = "uploadedFiles"
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(upload_dir, unique_filename)
    try:
        os.makedirs(upload_dir, exist_ok=True)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return JSONResponse(
            status_code=200, content={"filename": unique_filename, "result": "success"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {e}")
