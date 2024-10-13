from pydantic import BaseModel, Field, field_serializer, field_validator, ValidationInfo
from datetime import datetime
from typing import List, Optional, Dict, Literal
from enum import Enum
import logging
from app.classes.schemas import EvaluationType, StudentSubmissionStatus, SubmissionSummaryStatus, SubmissionProgressStatus, SingleJudgeStatus, Role

logging.basicConfig(level=logging.DEBUG)


class Message(BaseModel):
    message: str

    model_config = {"extra": "allow"}


class Lecture(BaseModel):
    id: int
    title: str
    start_date: datetime
    end_date: datetime
    
    problems: list["Problem"] = Field(default_factory=list)
    
    model_config = {"from_attributes": True}
    
    @field_serializer("start_date")
    def serialize_start_date(self, start_date: datetime, _info):
        return start_date.isoformat()
    
    @field_serializer("end_date")
    def serialize_end_date(self, end_date: datetime, _info):
        return end_date.isoformat()


class Problem(BaseModel):
    lecture_id: int
    assignment_id: int
    title: str
    # description_pathはレスポンスには含めない。
    # timeMSとmemoryMBはProblemDetailで返す。
    detail: "ProblemDetail" | None = Field(default=None)
    
    model_config = {"from_attributes": True}


class ProblemDetail(Problem):
    
    description: str | None = Field(default=None) # description_pathをファイルから読み込んだ文字列
    
    executables: list["Executables"]
    arranged_files: list["ArrangedFiles"]
    required_files: list["RequiredFiles"]
    test_cases: list["TestCases"]
    
    model_config = {"from_attributes": True}
    
    @field_validator("description")
    def get_description_from_context(cls, value: str | None, info: ValidationInfo) -> str:
        if info.context is not None and "description" in info.context:
            return info.context["description"]
        else:
            raise ValueError("description is not set")


class Executables(BaseModel):
    eval: bool
    name: str

    model_config = {"from_attributes": True}


class ArrangedFiles(BaseModel):
    eval: bool
    name: str
    content: str | None = Field(default=None) # ファイルの中身

    model_config = {"from_attributes": True}
    
    @field_validator("content")
    def get_content_from_context(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.context is not None and "content" in info.context:
            return info.context["content"]
        elif value is not None:
            return value
        else:
            raise ValueError("content is not set")


class RequiredFiles(BaseModel):
    name: str

    model_config = {"from_attributes": True}


class TestCases(BaseModel):
    eval: bool
    type: EvaluationType
    score: int
    title: str
    description: str | None
    command: str
    args: str | None
    stdin: str | None = Field(default=None) # response時にファイルから読み込む
    stdout: str | None = Field(default=None) # response時にファイルから読み込む
    stderr: str | None = Field(default=None) # response時にファイルから読み込む
    exit_code: int
    
    model_config = {"from_attributes": True}
    
    @field_validator("stdin", "stdout", "stderr")
    def get_from_context(cls, value: str | None, info: ValidationInfo) -> str | None:
        if info.context is not None and info.field_name in info.context:
            return info.context[info.field_name]
        else:
            # stdin, stdout, stderrが未指定の場合も許容する
            return value

    @field_serializer("type")
    def serialize_type(self, type: EvaluationType, _info):
        return type.value


class BatchSubmission(BaseModel):
    id: int
    ts: datetime
    user_id: str
    lecture_id: int
    message: str | None
    status: Literal["queued", "running", "done"] = Field(default="queued")
    complete_judge: int | None
    total_judge: int | None
    
    model_config = {"from_attributes": True}
    
    @field_serializer("ts")
    def serialize_ts(self, ts: datetime, _info):
        return ts.isoformat()
    
    @field_validator("status")
    def validate_status(cls, status: Literal["queued", "running", "done"]) -> Literal["queued", "running", "done"]:
        if status not in ["queued", "running", "done"]:
            raise ValueError("status is invalid")
        
        if cls.complete_judge is None or cls.total_judge is None:
            return "queued"
        elif cls.complete_judge == cls.total_judge:
            return "done"
        else:
            return "running"


class BatchSubmissionSummary(BaseModel):
    batch_id: int
    user_id: str
    status: StudentSubmissionStatus
    result: SubmissionSummaryStatus | None
    # BatchSubmissionSummaryテーブルのupload_dirがNULLじゃない場合はTrue
    upload_file_exists: bool = Field(default=False)
    # BatchSubmissionSummaryテーブルのreport_pathがNULLじゃない場合はTrue
    report_exists: bool = Field(default=False)
    submit_date: datetime | None
    
    # 該当学生の各課題の採点結果のリスト(SubmissionSummaryテーブルから取得してcontextで渡される)
    submission_summary_list: list["SubmissionSummary"] = Field(default_factory=list)
    
    model_config = {"from_attributes": True}
    
    @field_serializer("status")
    def serialize_status(self, status: StudentSubmissionStatus, _info):
        return status.value
    
    @field_serializer("result")
    def serialize_result(self, result: SubmissionSummaryStatus | None, _info):
        return result.value if result is not None else None
    
    @field_serializer("submit_date")
    def serialize_submit_date(self, submit_date: datetime | None, _info):
        return submit_date.isoformat() if submit_date is not None else None
    
    @field_validator("upload_file_exists")
    def validate_upload_file_exists(cls, upload_file_exists: bool, info: ValidationInfo):
        if info.context is not None and "upload_dir" in info.context:
            return info.context["upload_dir"] is not None
        else:
            return upload_file_exists
    
    @field_validator("report_exists")
    def validate_report_exists(cls, report_exists: bool, info: ValidationInfo):
        if info.context is not None and "report_path" in info.context:
            return info.context["report_path"] is not None
        else:
            return report_exists
        
    @field_validator("submission_summary_list")
    def validate_submission_summary_list(cls, submission_summary_list: list["SubmissionSummary"], info: ValidationInfo):
        if info.context is not None and "submission_summary_list" in info.context:
            return info.context["submission_summary_list"]
        else:
            return submission_summary_list


class Submission(BaseModel):
    id: int
    ts: datetime
    user_id: str
    lecture_id: int
    assignment_id: int
    eval: bool
    progress: SubmissionProgressStatus
    total_task: int
    completed_task: int

    # uploaded_filesはResponseでは返さない。別のFileResponse(ZIP)で内容ごと返す
    
    # SubmissionSummaryから取ってくるフィールド
    # ジャッジが終わっていない場合はNone
    result: SubmissionSummaryStatus | None = Field(default=None)
    score: int | None = Field(default=None)
    timeMS: int | None = Field(default=None)
    memoryKB: int | None = Field(default=None)
    
    model_config = {"from_attributes": True}
    
    @field_serializer("result")
    def serialize_result(self, result: SubmissionSummaryStatus | None, _info):
        return result.value if result is not None else None
    
    @field_serializer("ts")
    def serialize_ts(self, ts: datetime, _info):
        return ts.isoformat()
    
    @field_validator("result", "score", "timeMS", "memoryKB")
    def validate_judge_result(cls, value: int | None, info: ValidationInfo):
        if value is None and info.field_name in info.context:
            return info.context[info.field_name]
        else:
            return value


class SubmissionSummary(Submission):
    submission_id: int
    batch_id: int | None
    user_id: str
    result: SubmissionSummaryStatus
    message: str | None
    detail: str | None
    score: int
    timeMS: int = Field(default=0)
    memoryKB: int = Field(default=0)
    
    judge_results: list["JudgeResult"] = Field(default_factory=list)
    
    model_config = {"from_attributes": True}
    
    @field_serializer("result")
    def serialize_result(self, result: SubmissionSummaryStatus, _info):
        return result.value


class JudgeResult(BaseModel):
    id: int = Field(default=0)
    ts: datetime = Field(default=datetime(year=1998, month=6, day=6))
    submission_id: int
    testcase_id: int
    result: SingleJudgeStatus
    timeMS: int
    memoryKB: int
    exit_code: int
    stdout: str # DBに生のデータが入っているので、ファイルからは読み込まない
    stderr: str # DBに生のデータが入っているので、ファイルからは読み込まない
    
    model_config = {"from_attributes": True}
    
    @field_serializer("ts")
    def serialize_ts(self, ts: datetime, _info):
        return ts.isoformat()
    
    @field_serializer("result")
    def serialize_result(self, result: SingleJudgeStatus, _info):
        return result.value


class User(BaseModel):
    user_id: str
    username: str
    email: str
    role: Role
    disabled: bool
    active_start_date: datetime | None
    active_end_date: datetime | None

    model_config = {"from_attributes": True}
    
    @field_serializer("role")
    def serialize_role(self, role: Role, _info):
        return role.value

    @field_serializer("active_start_date", "active_end_date")
    def serialize_datetime(self, dt: datetime | None, _info):
        return dt.isoformat() if dt is not None else None


class TokenValidateResponse(BaseModel):
    is_valid: bool


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