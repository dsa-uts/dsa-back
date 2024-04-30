from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from ....classes.schemas import UserBase, MakefileUpdate, ExpectedOutputUpdate
from ....crud.db import authorize, utils, users, assignments
from ....dependencies import get_db
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta, datetime
import pytz
from typing import Optional

import logging

router = APIRouter()

logging.basicConfig(level=logging.INFO)


@router.post("/makefile/{id}/{sub_id}")
def edit_makefile(
    id: int,
    sub_id: int,
    makefile: MakefileUpdate,
    user: UserBase = Depends(users.get_current_user),
    db: Session = Depends(get_db),
):
    logging.info(f"Editing makefile for assignment {id} and sub-assignment {sub_id}")
    if user is None or user.disabled or not user.is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        utils.validate_sub_assignment(id, sub_id, user.is_admin, db)
        updated_sub_assignment = assignments.update_makefile(
            db, id, sub_id, makefile.makefile
        )
        if updated_sub_assignment:
            logging.info(f"Makefile updates success")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Makefile updated successfully.",
                },
            )
        else:
            logging.error(f"Makefile update failed")
            return JSONResponse(
                status_code=400,
                content={"status": "failure", "message": "No update performed."},
            )
    except Exception as e:
        logging.error(f"Error updating makefile: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/expected_output/{id}/{sub_id}")
def edit_expected_output(
    id: int,
    sub_id: int,
    expected_output: ExpectedOutputUpdate,
    user: UserBase = Depends(users.get_current_user),
    db: Session = Depends(get_db),
):
    logging.info(f"Editing makefile for assignment {id} and sub-assignment {sub_id}")
    if user is None or user.disabled or not user.is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        utils.validate_sub_assignment(id, sub_id, user.is_admin, db)
        # まだ作ってない
    except Exception as e:
        logging.error(f"Error updating makefile: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
