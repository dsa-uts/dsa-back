from sqlalchemy.orm import Session
from . import models, schemas


# すべての課題を取得する関数
def get_assignments(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.Assignment).offset(skip).limit(limit).all()


# idに対応するすべてのサブ課題を取得する関数
def get_sub_assignments(db: Session, id: int):
    return db.query(models.SubAssignment).filter(models.SubAssignment.id == id).all()


# 指定されたサブ課題を取得する関数
def get_sub_assignment(db: Session, id: int, sub_id: int):
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
