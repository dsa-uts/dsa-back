from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional, Union, Dict, Any
from . import models
import os
from ..crud import file_operation
from .. import constants
from fastapi import UploadFile
import logging

logging.basicConfig(level=logging.INFO)


class SubAssignmentBase(BaseModel):
    id: int
    sub_id: int
    title: str
    test_dir_name: str


class SubAssignmentDetail(SubAssignmentBase):
    makefile: str
    required_file_name: str
    main_file_name: str
    test_case_name: str
    test_input: Optional[str] = None  # 現状使わないかも．
    test_output: Optional[str] = None
    test_program: Optional[str] = None

    def __init__(self, sub_assignment: models.SubAssignment):
        super().__init__(
            id=sub_assignment.id,
            sub_id=sub_assignment.sub_id,
            title=sub_assignment.title,
            test_dir_name=sub_assignment.test_dir_name,
            makefile=sub_assignment.makefile,
            required_file_name=sub_assignment.required_file_name,
            main_file_name=sub_assignment.main_file_name,
            test_case_name=sub_assignment.test_case_name,
        )

    def set_test_program(self, assignment_title: str) -> str:
        combined_path = os.path.join(
            constants.TEST_PROGRAM_DIR_PATH,
            assignment_title,
            self.test_dir_name,
            self.main_file_name,
        )
        logging.info(f"combined_path: {combined_path}")
        if file_operation.check_path_exists(combined_path):
            with open(combined_path, "r") as f:
                self.test_program = f.read()
        else:
            self.test_program = ""
        logging.info(f"test_program: {self.test_program}")
        return self.test_program

    def set_test_output(self, assignment_title: str) -> str:
        combined_path = os.path.join(
            constants.TEST_CASE_DIR_PATH,
            assignment_title,
            self.test_dir_name,
            "out",
            self.test_case_name,
        )
        if file_operation.check_path_exists(combined_path):
            with open(combined_path, "r") as f:
                self.test_output = f.read()
        else:
            self.test_output = ""
        return self.test_output


class SubAssignment(SubAssignmentBase):
    makefile: str
    required_file_name: str
    main_file_name: str
    test_input_dir: Optional[str] = None
    test_output_dir: Optional[str] = None
    test_program_dir: Optional[str] = None
    test_case_name: Optional[str] = None

    class Config:
        orm_mode = True


class AssignmentBase(BaseModel):
    id: int
    title: str
    test_dir_name: str
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
    refresh_token: str
    token_type: str
    login_time: datetime
    user_id: int
    is_admin: bool


class TokenData(BaseModel):
    username: Union[str, None] = None


class AccessToken(BaseModel):
    id: int
    code: str
    expired_at: datetime
    is_expired: bool
    user_id: Optional[int] = None

    class Config:
        orm_mode = True


class RefreshToken(BaseModel):
    id: int
    token: str
    expired_at: datetime
    is_expired: bool
    user_id: Optional[int] = None

    class Config:
        orm_mode = True


class ProgressMessage(BaseModel):
    status: str
    message: str
    progress_percentage: int
    result: Optional[Dict[str, Any]] = None


class FunctionTest(BaseModel):
    id: int
    sub_id: int
    func_id: int
    func_name: str
    exec_command: str

    class Config:
        orm_mode = True


class File:
    file_path: str
    filename: str

    def __init__(self, file_path: str, upload_file: Optional[UploadFile] = None):
        if file_operation.is_dir(file_path):
            raise ValueError("file_path should be a file path, not a directory path")
        self.file_path = file_path
        if upload_file is not None:
            if os.path.basename(file_path) != upload_file.filename:
                raise ValueError("file_path and upload_file.filename must be the same")
            file_operation.write_uploaded_file(upload_file, self.file_path)
            self.filename = upload_file.filename
        else:
            self.filename = os.path.basename(file_path)
