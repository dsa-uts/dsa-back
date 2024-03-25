from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ....dependencies import get_db
from .... import crud, schemas
from typing import List

router = APIRouter()


@router.get("/", response_model=List[schemas.AssignmentBase])
def read_assignments(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    assignments = crud.get_assignments(db, skip=skip, limit=limit)
    return assignments


@router.get("/{id}", response_model=List[schemas.SubAssignmentBase])
def read_sub_assignments(id: int, db: Session = Depends(get_db)):
    db_assignment = crud.get_sub_assignments(db, id=id)
    return db_assignment


@router.get("/{id}/{sub_id}", response_model=schemas.SubAssignment)
def read_sub_assignment(id: int, sub_id: int, db: Session = Depends(get_db)):
    db_assignment = crud.get_sub_assignment(db, id=id, sub_id=sub_id)
    return db_assignment
