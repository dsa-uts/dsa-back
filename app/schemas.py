from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional


class SubAssignmentBase(BaseModel):
    id: int
    sub_id: int
    title: str


class SubAssignmentDetail(SubAssignmentBase):
    makefile: str
    required_file_name: str
    test_file_name: str
    test_input: Optional[str] = None
    test_output: Optional[str] = None
    test_program: Optional[str] = None


class SubAssignment(SubAssignmentBase):
    makefile: str
    required_file_name: str
    test_file_name: str
    test_input: Optional[str] = None
    test_output: Optional[str] = None
    test_program: Optional[str] = None

    class Config:
        orm_mode = True


class AssignmentBase(BaseModel):
    id: int
    title: str
    start_date: datetime
    end_date: datetime


class AssignmentCreate(AssignmentBase):
    pass


class Assignment(AssignmentBase):
    id: int
    sub_assignments: List[SubAssignment] = []

    class Config:
        orm_mode = True
