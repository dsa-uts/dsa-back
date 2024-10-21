from ...classes import schemas
from sqlalchemy.orm import Session
from ...classes import models
from typing import List
from app import constants
import logging

logging.basicConfig(level=logging.DEBUG)


def get_user(db: Session, user_id: str) -> schemas.UserRecord | None:
    user: models.Users | None = (
        db.query(models.Users).filter(models.Users.user_id == user_id).first()
    )
    return schemas.UserRecord.model_validate(user) if user else None


def get_users(db: Session) -> List[schemas.UserRecord]:
    users = db.query(models.Users).all()
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


def delete_users(db: Session, user_ids: List[str]) -> None:
    db.query(models.Users).filter(models.Users.user_id.in_(user_ids)).delete()
    db.commit()


def update_password(db: Session, user_id: str, new_hashed_password: str) -> None:
    user = db.query(models.Users).filter(models.Users.user_id == user_id).first()
    if user:
        user.hashed_password = new_hashed_password
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
