from ...classes import schemas
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ...classes import models
from ...classes.models import User
from ...classes.schemas import UserInDB, UserBase
from fastapi import HTTPException, Depends, status, Request
from typing import Annotated, List
from ...api.api_v1.dependencies import oauth2_scheme
from ...dependencies import get_db
from ...crud.db import authorize
from jose import JWTError, jwt
from ...api.api_v1.dependencies import (
    SECRET_KEY,
    ALGORITHM,
)
import pytz
from datetime import datetime
from . import utils
from ... import constants
import logging

logging.basicConfig(level=logging.DEBUG)


def get_user(db: Session, student_id: str) -> User | None:
    user: User | None = db.query(User).filter(User.student_id == student_id).first()
    return user


def get_users(db: Session) -> List[User]:
    users = db.query(User).all()
    return users


def exist_user(db: Session, student_id: str) -> bool:
    user = db.query(User).filter(User.student_id == student_id).first()
    if user:
        return True
    return False


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    request: Request,
    db: Session = Depends(get_db),
) -> UserBase:
    if token is None:
        raise HTTPException(status_code=401, detail="Token is not provided")
    try:
        user_id, student_id = authorize.verify_access_token(db, token)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = get_user(db, student_id=student_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    user = await update_disabled_status(db, user)
    user = UserBase(**user.__dict__)
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)]
):
    updated_user = await update_disabled_status(db=None, user=current_user)
    if updated_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


async def update_disabled_status(db: Session, user: User):
    current_time = datetime.now(pytz.timezone("Asia/Tokyo"))
    user.disabled = not utils.is_active_user(user, current_time)
    db.commit()
    db.refresh(user)
    return user


# authorize.pyにおいても良いかも．
def authenticate_user(db: Session, student_id: str, password: str):
    user = get_user(db, student_id)
    if not user:
        return False
    if not authorize.verify_password(password, user.hashed_password):
        return False
    return user


def create_user(db: Session, user: schemas.UserCreate):
    existing_user = exist_user(db, user.student_id)
    if existing_user:
        raise HTTPException(
            status_code=400, detail=f"User {user.student_id} already exists"
        )
    try:
        logging.info(f"Creating user: {user}")
        hashed_password = authorize.get_password_hash(user.raw_password)
        db_user = models.User(
            student_id=user.student_id,
            username=user.username,
            email=user.email,
            hashed_password=hashed_password,
            is_admin=user.is_admin,
            disabled=(
                False
                if user.active_start_date is None
                else datetime.now(pytz.timezone("Asia/Tokyo"))
                < user.active_start_date.astimezone(pytz.timezone("Asia/Tokyo"))
            ),
            created_at=(
                datetime.now(pytz.timezone("Asia/Tokyo"))
                if user.created_at is None
                else user.created_at
            ),
            active_start_date=user.active_start_date,
            active_end_date=user.active_end_date,
        )
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return user.raw_password
    except IntegrityError as e:
        raise HTTPException(status_code=400, detail=e.args[0])


async def delete_users(db: Session, user_ids: List[int]):
    try:
        for user_id in user_ids:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            logging.info(f"Deleting user: {user}")
            if user:
                db.delete(user)
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
