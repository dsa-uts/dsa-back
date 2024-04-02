from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Union


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
    test_input_dir: Optional[str] = None
    test_output_dir: Optional[str] = None
    test_program_dir: Optional[str] = None
    test_case_name: Optional[str] = None
    test_program_name: Optional[str] = None

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


class UserLogin(BaseModel):
    username: str
    password: str


class UserBase(BaseModel):
    id: int
    username: str
    is_admin: bool
    disabled: bool


class UserCreate(BaseModel):
    username: str
    password: str  # 暗号化前のパスワード
    is_admin: bool = False
    disabled: bool = False
    created_at: Optional[datetime] = None
    active_start_date: Optional[datetime] = None
    active_end_date: Optional[datetime] = None


class UserDelete(BaseModel):
    user_ids: List[int]


class User(UserBase):
    id: int
    hashed_password: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    active_start_date: Optional[datetime] = None
    active_end_date: Optional[datetime] = None

    class Config:
        orm_mode = True


class UserInDB(User):
    hashed_password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    login_time: datetime
    user_id: int
    is_admin: bool


class TokenData(BaseModel):
    username: Union[str, None] = None


class AuthCode(BaseModel):
    id: int
    code: str
    expired_at: datetime
    is_expired: bool
    user_id: Optional[int] = None

    class Config:
        orm_mode = True
