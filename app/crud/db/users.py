from ...classes import schemas
from sqlalchemy.orm import Session
from ...classes import models
from typing import List, Optional
from app import constants
import logging
from sqlalchemy import or_
logging.basicConfig(level=logging.DEBUG)
from datetime import datetime


def get_user(db: Session, user_id: str) -> schemas.UserRecord | None:
    user: models.Users | None = (
        db.query(models.Users).filter(models.Users.user_id == user_id).first()
    )
    return schemas.UserRecord.model_validate(user) if user else None


def get_users(db: Session, user_id: Optional[int] = None, role: Optional[str] = None) -> List[schemas.UserRecord]:
    query = db.query(models.Users)
    if user_id or role:
        filter_conditions = []
        if user_id:
            filter_conditions.append(models.Users.user_id == user_id)
        if role:
            filter_conditions.append(models.Users.role == role)
        query = query.filter(or_(*filter_conditions))
    users = query.all()
    return [schemas.UserRecord.model_validate(user) for user in users]


def exist_user(db: Session, student_id: str) -> bool:
    user = db.query(models.Users).filter(models.Users.user_id == student_id).first()
    return user is not None


def create_user(db: Session, user: schemas.UserRecord) -> schemas.UserRecord:
    try:
        db_user = models.Users(**user.model_dump())
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        return schemas.UserRecord.model_validate(db_user)
    except Exception as e:
        db.rollback()
        raise e

def update_user(db: Session, user: schemas.UserRecord) -> schemas.UserRecord:
    existing_user = db.query(models.Users).filter(models.Users.user_id == user.user_id).first()
    if existing_user is None:
        raise ValueError(f"ユーザーID {user.user_id} が見つかりません")

    update_data = user.model_dump(exclude_unset=True)
    if not update_data.get('hashed_password'):
        update_data.pop('hashed_password', None)
    update_data.pop('created_at', None)

    for key, value in update_data.items():
        setattr(existing_user, key, value)

    db.commit()
    db.refresh(existing_user)
    return schemas.UserRecord.model_validate(existing_user)


def delete_users(db: Session, user_ids: List[str]) -> None:
    db.query(models.Users).filter(models.Users.user_id.in_(user_ids)).delete()
    db.commit()


def update_password(db: Session, user_id: str, new_hashed_password: str, updated_at: datetime) -> None:
    user = db.query(models.Users).filter(models.Users.user_id == user_id).first()
    if user:
        user.hashed_password = new_hashed_password
        user.updated_at = updated_at
        db.commit()
    return None


def update_disabled_status(db: Session, user_id: str, disabled: bool) -> None:
    user = db.query(models.Users).filter(models.Users.user_id == user_id).first()
    if user:
        user.disabled = disabled
        db.commit()
    return None


def admin_user_exists(db: Session) -> bool:
    user = db.query(models.Users).filter(models.Users.user_id == constants.ADMIN_USER_ID).first()
    return user is not None
