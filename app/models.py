from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Assignment(Base):
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    sub_assignments = relationship("SubAssignment", back_populates="assignment")


class SubAssignment(Base):
    __tablename__ = "sub_assignments"
    id = Column(Integer, ForeignKey("assignments.id"), primary_key=True)
    sub_id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    makefile = Column(String(255), nullable=False)
    required_file_name = Column(String(255), nullable=False)
    test_file_name = Column(String(255), nullable=False)
    test_input = Column(String, nullable=True)
    test_output = Column(String, nullable=True)
    test_program = Column(String, nullable=True)
    assignment = relationship("Assignment", back_populates="sub_assignments")
