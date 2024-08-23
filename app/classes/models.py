from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, relationship


Base = declarative_base()


class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    test_dir_name = Column(String(255), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    sub_assignments = relationship("SubAssignment", back_populates="assignment")


class SubAssignment(Base):
    __tablename__ = "sub_assignments"
    id = Column(Integer, ForeignKey("assignments.id"), primary_key=True)
    sub_id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    test_dir_name = Column(String(255), nullable=False)
    makefile = Column(String(255), nullable=False)
    required_file_name = Column(String(255), nullable=False)
    main_file_name = Column(String(255), nullable=False)
    test_case_name = Column(String(255), nullable=True)
    assignment = relationship("Assignment", back_populates="sub_assignments")


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(255), nullable=False)
    username = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    disabled = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=True)
    active_start_date = Column(DateTime, nullable=True)
    active_end_date = Column(DateTime, nullable=True)

    access_tokens = relationship("AccessToken", back_populates="user")
    refresh_tokens = relationship("RefreshToken", back_populates="user")

    class Config:
        orm_mode = True


class AccessToken(Base):
    __tablename__ = "access_tokens"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(255), nullable=False)
    expired_at = Column(DateTime, nullable=False)
    is_expired = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", back_populates="access_tokens")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token = Column(String(255), nullable=False)
    expired_at = Column(DateTime, nullable=False)
    is_expired = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User", back_populates="refresh_tokens")


class FunctionTest(Base):
    __tablename__ = "function_test"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sub_id = Column(Integer, primary_key=True)
    func_id = Column(Integer, primary_key=True)
    func_name = Column(String(255), nullable=False)
    exec_command = Column(String(255), nullable=True)
