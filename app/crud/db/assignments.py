from sqlalchemy.orm import Session
from ... import models, schemas
from typing import List


# idに対応する課題を取得する関数
def get_assignment(db: Session, id: int) -> models.Assignment:
    return db.query(models.Assignment).filter(models.Assignment.id == id).first()


# すべての課題を取得する関数
def get_assignments(
    db: Session, skip: int = 0, limit: int = 100
) -> List[models.Assignment]:
    return db.query(models.Assignment).offset(skip).limit(limit).all()


# idに対応するすべてのサブ課題を取得する関数
def get_sub_assignments(db: Session, id: int) -> List[models.SubAssignment]:
    return db.query(models.SubAssignment).filter(models.SubAssignment.id == id).all()


# 指定されたサブ課題を取得する関数
def get_sub_assignment(db: Session, id: int, sub_id: int) -> models.SubAssignment:
    return (
        db.query(models.SubAssignment)
        .filter(models.SubAssignment.id == id)
        .filter(models.SubAssignment.sub_id == sub_id)
        .first()
    )


def create_assignment(db: Session, assignment: schemas.AssignmentCreate):
    db_assignment = models.Assignment(**assignment.dict())
    db.add(db_assignment)
    db.commit()
    db.refresh(db_assignment)
    return db_assignment
