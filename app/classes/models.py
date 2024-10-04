from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    Boolean,
    Enum,
    text,
)
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


class Lecture(Base):
    __tablename__ = "Lecture"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    problems = relationship("Problem", back_populates="lecture")


class Problem(Base):
    __tablename__ = "Problem"
    lecture_id = Column(
        Integer, ForeignKey("Lecture.id"), primary_key=True, nullable=False
    )
    assignment_id = Column(Integer, primary_key=True, nullable=False)
    for_evaluation = Column(Boolean, primary_key=True, nullable=False)
    title = Column(String(255), nullable=False)
    description_path = Column(String(255), nullable=False)
    timeMS = Column(Integer, nullable=False)
    memoryMB = Column(Integer, nullable=False)
    lecture = relationship("Lecture", back_populates="problems")


class Executables(Base):
    __tablename__ = "Executables"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"))
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"))
    for_evaluation = Column(Boolean, ForeignKey("Problem.for_evaluation"))
    name = Column(String(255), nullable=False)


class ArrangedFiles(Base):
    __tablename__ = "ArrangedFiles"
    str_id = Column(String(255), primary_key=True)
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"))
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"))
    for_evaluation = Column(Boolean, ForeignKey("Problem.for_evaluation"))
    path = Column(String(255), nullable=False)


class RequiredFiles(Base):
    __tablename__ = "RequiredFiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"))
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"))
    for_evaluation = Column(Boolean, ForeignKey("Problem.for_evaluation"))
    name = Column(String(255), nullable=False)


class EvaluationItems(Base):
    __tablename__ = "EvaluationItems"
    str_id = Column(String(255), primary_key=True)
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"))
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"))
    for_evaluation = Column(Boolean, ForeignKey("Problem.for_evaluation"))
    title = Column(String(255), nullable=False)
    description = Column(String)
    score = Column(Integer, nullable=False)
    type = Column(Enum("Built", "Judge"), nullable=False)
    arranged_file_id = Column(String(255), ForeignKey("ArrangedFiles.str_id"))
    message_on_fail = Column(String(255))


class TestCases(Base):
    __tablename__ = "TestCases"
    id = Column(Integer, primary_key=True, autoincrement=True)
    eval_id = Column(String(255), ForeignKey("EvaluationItems.str_id"), nullable=False)
    description = Column(String)
    command = Column(String(255), nullable=False)
    argument_path = Column(String(255))
    stdin_path = Column(String(255))
    stdout_path = Column(String(255))
    stderr_path = Column(String(255))
    exit_code = Column(Integer, nullable=False, default=0)


class Users(Base):
    __tablename__ = "Users"
    user_id = Column(String(255), primary_key=True)
    username = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum("admin", "manager", "student"), nullable=False)
    disabled = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    updated_at = Column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=text("CURRENT_TIMESTAMP"),
    )
    active_start_date = Column(DateTime, default=None)
    active_end_date = Column(DateTime, default=None)


class LoginHistory(Base):
    __tablename__ = "LoginHistory"
    user_id = Column(
        String(255), ForeignKey("Users.user_id"), primary_key=True, nullable=False
    )
    login_at = Column(DateTime, nullable=False, primary_key=True)
    logout_at = Column(DateTime, nullable=False)
    refresh_count = Column(Integer, default=0, nullable=False)


class BatchSubmission(Base):
    __tablename__ = "BatchSubmission"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    user_id = Column(String(255), ForeignKey("Users.user_id"))


class Submission(Base):
    __tablename__ = "Submission"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    batch_id = Column(Integer, ForeignKey("BatchSubmission.id"))
    user_id = Column(String(255), ForeignKey("Users.user_id"), nullable=False)
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"), nullable=False)
    for_evaluation = Column(
        Boolean, ForeignKey("Problem.for_evaluation"), nullable=False
    )
    progress = Column(Enum("pending", "queued", "running", "done"), default="pending")
    total_task = Column(Integer, nullable=False, default=0)
    completed_task = Column(Integer, nullable=False, default=0)


class UploadedFiles(Base):
    __tablename__ = "UploadedFiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    submission_id = Column(Integer, ForeignKey("Submission.id"))
    path = Column(String(255), nullable=False)


class JudgeResult(Base):
    __tablename__ = "JudgeResult"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, server_default=text("CURRENT_TIMESTAMP"))
    parent_id = Column(Integer, ForeignKey("EvaluationSummary.id"), nullable=False)
    submission_id = Column(Integer, ForeignKey("Submission.id"), nullable=False)
    testcase_id = Column(Integer, ForeignKey("TestCases.id"), nullable=False)
    result = Column(
        Enum("AC", "WA", "TLE", "MLE", "RE", "CE", "OLE", "IE"), nullable=False
    )
    timeMS = Column(Integer, nullable=False)
    memoryKB = Column(Integer, nullable=False)
    exit_code = Column(Integer, nullable=False)
    stdout = Column(String, nullable=False)
    stderr = Column(String, nullable=False)
    description = Column(String)
    command = Column(String, nullable=False)
    stdin = Column(String)
    expected_stdout = Column(String)
    expected_stderr = Column(String)
    expected_exit_code = Column(Integer, nullable=False, default=0)


class EvaluationSummary(Base):
    __tablename__ = "EvaluationSummary"
    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_id = Column(Integer, ForeignKey("SubmissionSummary.submission_id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("BatchSubmission.id"))
    user_id = Column(String(255), ForeignKey("Users.user_id"), nullable=False)
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"), nullable=False)
    for_evaluation = Column(
        Boolean, ForeignKey("Problem.for_evaluation"), nullable=False
    )
    eval_id = Column(String(255), ForeignKey("EvaluationItems.str_id"), nullable=False)
    arranged_file_id = Column(String(255), ForeignKey("ArrangedFiles.str_id"))
    result = Column(
        Enum("AC", "WA", "TLE", "MLE", "RE", "CE", "OLE", "IE"), nullable=False
    )
    message = Column(String(255))
    detail = Column(String(255))
    score = Column(Integer, nullable=False)
    timeMS = Column(Integer, nullable=False, default=0)
    memoryKB = Column(Integer, nullable=False, default=0)
    eval_title = Column(String(255), nullable=False)
    eval_description = Column(String)
    eval_type = Column(Enum("Built", "Judge"), nullable=False)
    arranged_file_path = Column(String(255))


class SubmissionSummary(Base):
    __tablename__ = "SubmissionSummary"
    submission_id = Column(Integer, ForeignKey("Submission.id"), primary_key=True)
    batch_id = Column(Integer, ForeignKey("BatchSubmission.id"))
    user_id = Column(String(255), ForeignKey("Users.user_id"))
    lecture_id = Column(Integer, ForeignKey("Problem.lecture_id"), nullable=False)
    assignment_id = Column(Integer, ForeignKey("Problem.assignment_id"), nullable=False)
    for_evaluation = Column(
        Boolean, ForeignKey("Problem.for_evaluation"), nullable=False
    )
    result = Column(
        Enum("AC", "WA", "TLE", "MLE", "RE", "CE", "OLE", "IE", "FN"), nullable=False
    )
    message = Column(String(255))
    detail = Column(String(255))
    score = Column(Integer, nullable=False)
    timeMS = Column(Integer, nullable=False, default=0)
    memoryKB = Column(Integer, nullable=False, default=0)


class EvaluationResult(Base):
    __tablename__ = "EvaluationResult"
    user_id = Column(String(255), ForeignKey("Users.user_id"), primary_key=True)
    lecture_id = Column(Integer, ForeignKey("Lecture.id"), primary_key=True)
    score = Column(Integer, nullable=True)
    report_path = Column(String(255), nullable=True)
    comment = Column(String, nullable=True)
