from pydantic import BaseModel, Field, field_serializer
from datetime import datetime
from typing import List, Optional, Union, Dict, Any
from enum import Enum
from . import models
import os
from ..crud import file_operation
from .. import constants
from fastapi import UploadFile
import logging

logging.basicConfig(level=logging.DEBUG)


class Message(BaseModel):
    message: str

    model_config = {"extra": "allow"}


class SubmissionProgressStatus(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"


# 実行結果の集約をするための、順序定義
# 各テストケースの実行結果が、["AC", "WA", "AC", "TLE"]の場合、
# 全体の結果はmaxを取って"TLE"となる。
JudgeStatusOrder: Dict[str, int] = {
    # (value) : (order)
    "AC": 0,  # Accepted
    "WA": 1,  # Wrong Answer
    "TLE": 2,  # Time Limit Exceed
    "MLE": 3,  # Memory Limit Exceed
    "RE": 4,  # Runtime Error
    "CE": 5,  # Compile Error
    "OLE": 6,  # Output Limit Exceed (8000 bytes)
    "IE": 7,  # Internal Error (e.g., docker sandbox management)
    "FN": 8,  # File Not found
}


class BaseJudgeStatusWithOrder(Enum):
    def __str__(self):
        return self.name

    def __lt__(self, other):
        if self.__class__ is other.__class__:
            return JudgeStatusOrder[self.value] < JudgeStatusOrder[other.value]
        return NotImplemented

    def __gt__(self, other):
        if self.__class__ is other.__class__:
            return JudgeStatusOrder[self.value] > JudgeStatusOrder[other.value]
        return NotImplemented

    def __le__(self, other):
        if self.__class__ is other.__class__:
            return JudgeStatusOrder[self.value] <= JudgeStatusOrder[other.value]
        return NotImplemented

    def __ge__(self, other):
        if self.__class__ is other.__class__:
            return JudgeStatusOrder[self.value] >= JudgeStatusOrder[other.value]
        return NotImplemented


class SingleJudgeStatus(BaseJudgeStatusWithOrder):
    AC = "AC"  # Accepted
    WA = "WA"  # Wrong Answer
    TLE = "TLE"  # Time Limit Exceed
    MLE = "MLE"  # Memory Limit Exceed
    RE = "RE"  # Runtime Error
    CE = "CE"  # Compile Error
    OLE = "OLE"  # Output Limit Exceed (8000 bytes)
    IE = "IE"  # Internal Error (e.g., docker sandbox management)


class EvaluationSummaryStatus(BaseJudgeStatusWithOrder):
    AC = "AC"  # Accepted
    WA = "WA"  # Wrong Answer
    TLE = "TLE"  # Time Limit Exceed
    MLE = "MLE"  # Memory Limit Exceed
    RE = "RE"  # Runtime Error
    CE = "CE"  # Compile Error
    OLE = "OLE"  # Output Limit Exceed (8000 bytes)
    IE = "IE"  # Internal Error (e.g., docker sandbox management)


class SubmissionSummaryStatus(BaseJudgeStatusWithOrder):
    AC = "AC"  # Accepted
    WA = "WA"  # Wrong Answer
    TLE = "TLE"  # Time Limit Exceed
    MLE = "MLE"  # Memory Limit Exceed
    RE = "RE"  # Runtime Error
    CE = "CE"  # Compile Error
    OLE = "OLE"  # Output Limit Exceed (8000 bytes)
    IE = "IE"  # Internal Error (e.g., docker sandbox management)
    FN = "FN"  # File Not found


class LectureRecord(BaseModel):
    id: int
    title: str = Field(max_length=255)
    start_date: datetime
    end_date: datetime
    
    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }


class ArrangedFileRecord(BaseModel):
    str_id: str
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    path: str
    
    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }


class BatchSubmissionRecord(BaseModel):
    id: int
    ts: datetime
    user_id: str
    
    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }


class SubmissionRecord(BaseModel):
    id: int
    ts: datetime
    batch_id: int | None
    user_id: str
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    progress: SubmissionProgressStatus
    total_task: int = Field(default=0)
    completed_task: int = Field(default=0)

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }

    @field_serializer("progress")
    def serialize_progress(self, progress: SubmissionProgressStatus, _info):
        return progress.value


class TestCaseRecord(BaseModel):
    id: int
    eval_id: str
    description: str | None
    command: str  # nullable=False
    argument_path: str | None
    stdin_path: str | None
    stdout_path: str | None
    stderr_path: str | None
    exit_code: int  # default: 0

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }


class EvaluationType(Enum):
    Built = "Built"
    Judge = "Judge"


class EvaluationItemRecord(BaseModel):
    str_id: str
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    title: str
    description: str | None
    score: int
    type: EvaluationType
    arranged_file_id: str | None
    message_on_fail: str | None
    # 紐づいているTestCaseRecordのリスト
    testcase_list: list[TestCaseRecord] = Field(default_factory=list)

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }

    @field_serializer("type")
    def serialize_type(self, type: EvaluationType, _info):
        return type.value


class ProblemRecord(BaseModel):
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    title: str
    description_path: str
    timeMS: int
    memoryMB: int
    # 紐づいているEvaluationItemRecordのリスト
    evaluation_item_list: list[EvaluationItemRecord] = Field(default_factory=list)

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }


class JudgeResultRecord(BaseModel):
    parent_id: int
    submission_id: int
    testcase_id: int
    result: SingleJudgeStatus
    timeMS: int
    memoryKB: int
    exit_code: int
    stdout: str
    stderr: str
    # TestCasesレコードから取ってくる値
    description: str | None
    command: str
    stdin: str | None
    expected_stdout: str | None
    expected_stderr: str | None
    expected_exit_code: int = Field(default=0)
    # テーブル挿入時に自動で決まる値
    id: int = (
        1  # テーブルに挿入する際は自動設定されるので、コンストラクタで指定する必要が無いように適当な値を入れている
    )
    ts: datetime = Field(default_factory=lambda: datetime(1998, 6, 6, 12, 32, 41))

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }

    @field_serializer("result")
    def serialize_result(self, result: SingleJudgeStatus, _info):
        return result.value


class EvaluationSummaryRecord(BaseModel):
    parent_id: int
    batch_id: int | None
    user_id: str
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    eval_id: str
    arranged_file_id: str | None
    result: EvaluationSummaryStatus
    message: str | None
    detail: str | None
    score: int
    timeMS: int = Field(default=0)
    memoryKB: int = Field(default=0)
    # 外部キー関係ではないけどEvaluationItemsやArrangedFilesから取ってくる値
    eval_title: str  # EvaluationItems.title
    eval_description: str | None  # EvaluationItems.description
    eval_type: EvaluationType  # EvaluationItems.type
    arranged_file_path: str | None  # Arrangedfiles.path
    # テーブルに挿入時に自動で値が決まるフィールド
    id: int = 0  # auto increment PK
    # 以降、クライアントで必要になるフィールド
    judge_result_list: list[JudgeResultRecord] = Field(default_factory=list)

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }

    @field_serializer("result")
    def serialize_result(self, result: EvaluationSummaryStatus, _info):
        return result.value


class SubmissionSummaryRecord(BaseModel):
    submission_id: int
    batch_id: int | None
    user_id: str
    lecture_id: int
    assignment_id: int
    for_evaluation: bool
    result: SubmissionSummaryStatus
    message: str | None
    detail: str | None
    score: int
    timeMS: int = Field(default=0)
    memoryKB: int = Field(default=0)
    # 以降、クライアントで必要になるフィールド
    evaluation_summary_list: list[EvaluationSummaryRecord] = Field(default_factory=list)

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }

    @field_serializer("result")
    def serialize_result(self, result: SubmissionSummaryStatus, _info):
        return result.value


class EvaluationResultRecord(BaseModel):
    user_id: str
    lecture_id: int
    score: int | None
    report_path: str | None
    comment: str | None
    
    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }


class LoginHistoryRecord(BaseModel):
    user_id: str
    login_at: datetime
    logout_at: datetime
    refresh_count: int

    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }


class Role(Enum):
    admin = "admin"
    manager = "manager"
    student = "student"


class UserRecord(BaseModel):
    user_id: str = Field(max_length=255)
    username: str = Field(max_length=255)
    email: str = Field(max_length=255)
    hashed_password: str = Field(max_length=255)
    role: Role
    disabled: bool
    created_at: datetime
    updated_at: datetime
    active_start_date: datetime
    active_end_date: datetime
    
    @field_serializer("role")
    def serialize_role(self, role: Role, _info):
        return role.value
    
    model_config = {
        # sqlalchemyのレコードデータからマッピングするための設定
        "from_attributes": True
    }


class UserCreate(BaseModel):
    user_id: str
    username: str
    email: str
    plain_password: str  # 暗号化前のパスワード
    role: Role
    disabled: bool = False
    active_start_date: Optional[datetime] = None
    active_end_date: Optional[datetime] = None


class UserDelete(BaseModel):
    user_ids: List[int]


class Token(BaseModel):
    access_token: str
    token_type: str
    login_time: datetime
    user_id: str
    role: Role
    refresh_count: int = Field(default=0)

    @field_serializer("role")
    def serialize_role(self, role: Role, _info):
        return role.value


class JWTTokenPayload(BaseModel):
    sub: str = Field(max_length=255)
    login: datetime
    expire: datetime
    scopes: list[str] = Field(default_factory=list)
    role: Role

    model_config = {
        # JWTトークンのdict型からJWTTokenPayloadへ変換するための設定
        "from_attributes": True
    }

    # dict型に変換するときに、mysqlのDATETIMEフォーマットに合わせるためのシリアライズ関数
    @field_serializer("login", "expire")
    def serialize_datetime_fields(self, dt: datetime, _info):
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    @field_serializer("role")
    def serialize_role(self, role: Role, _info):
        return role.value


class TokenValidateResponse(BaseModel):
    is_valid: bool


class TextDataResponse(BaseModel):
    text: str


# 提出の進捗状況と結果を取得するためのスキーマ
class JudgeProgressAndStatus(BaseModel):
    id: int  # submission.id
    ts: datetime  # submission.ts
    user_id: str  # submission.user_id
    lecture_id: int  # submission.lecture_id
    assignment_id: int  # submission.assignment_id
    for_evaluation: bool  # submission.for_evaluation
    progress: SubmissionProgressStatus  # submission.progress
    completed_task: int  # submission.completed_task
    total_task: int  # submission.total_task
    result: SubmissionSummaryStatus | None
    message: str | None
    score: int | None
    timeMS: int | None
    memoryKB: int | None


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
