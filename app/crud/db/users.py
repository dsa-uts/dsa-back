from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ... import models, schemas
from ...models import User
from ...schemas import UserInDB, UserBase
from fastapi import HTTPException, Depends, status
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

logging.basicConfig(level=logging.INFO)


def get_user(db: Session, username: str) -> User | None:
    user: User | None = db.query(User).filter(User.username == username).first()
    return user


def get_users(db: Session) -> List[User]:
    users = db.query(User).all()
    return users


def exist_user(db: Session, username: str) -> bool:
    user = db.query(User).filter(User.username == username).first()
    if user:
        return True
    return False


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)
) -> UserBase:
    if token is None or authorize.is_valid_token(db, token) is False:
        return constants.GUEST
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return constants.GUEST
    except JWTError:
        return constants.GUEST
    user = get_user(db, username=username)
    if user is None:
        return constants.GUEST
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
def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return False
    if not authorize.verify_password(password, user.hashed_password):
        return False
    return user


def create_user(db: Session, user: schemas.UserCreate):
    existing_user = exist_user(db, user.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    try:
        hashed_password = authorize.get_password_hash(user.password)
        db_user = models.User(
            username=user.username,
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
        return db_user
    except IntegrityError:
        raise HTTPException(status_code=400, detail="User already exists")


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
