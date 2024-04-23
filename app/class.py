from .crud import file_operation
from . import constants as constants
import os
from sqlalchemy.orm import Session
from .crud.db import assignments as db_assignments
from .models import SubAssignment
from abc import ABC, abstractmethod
from typing import List


class SubmissionToolBaseClass:
    id: int
    unique_ids: List[str]
    root_dir_path: str

    @abstractmethod
    def get_test_program_dir(self, db: Session) -> str:
        pass


class FormatCheckDirectoryCreator:
    sub_id: int
    unique_id: str
    sub_assignment: SubAssignment
    test_program_dir: str

    def __init__(self, id: int, sub_id: int, unique_id: str, file_name: str):
        self.id = id
        self.sub_id = sub_id
        self.unique_id = unique_id
        self.root_dir = os.path.join(constants.UPLOAD_DIR, self.unique_id)
        self.upload_dir = os.path.join(self.root_dir, "submit")
        self.file_name = file_name

    def get_test_program_dir(self, db: Session) -> str:
        self.sub_assignment = db_assignments.get_sub_assignment(
            db, self.id, self.sub_id
        )
        if self.sub_assignment and self.sub_assignment.test_program_dir:
            self.test_program_dir = self.sub_assignment.test_program_dir
            return self.test_program_dir
        else:
            return ""

    def create_bin_dir(self):
        file_path = os.path.join(self.root_dir, "bin")
        file_operation.create_dir(file_path)

    def create_test_case_dir(self):
        dst_test_case_in = os.path.join(self.root_dir, "test_case", "in")
        dst_test_case_out = os.path.join(self.root_dir, "test_case", "out")
        file_operation.mkdir(dst_test_case_in)
        file_operation.mkdir(dst_test_case_out)

    def copy_makefile_dir(self):
        src_makefile = os.path.join(self.test_program_dir, "makefile")
        dst_makefile = os.path.join(self.root_dir, "makefile")
        file_operation.copy_directory(src_makefile, dst_makefile)

    def copy_test_case(self):
        src_test_case_in = os.path.join(
            self.sub_assignment.test_input_dir, self.sub_assignment.test_case_name
        )
        src_test_case_out = os.path.join(
            self.sub_assignment.test_output_dir, self.sub_assignment.test_case_name
        )
        if not file_operation.is_file(src_test_case_in):
            raise FileNotFoundError(
                f"Input test case file not found: {src_test_case_in}"
            )
        if not file_operation.is_file(src_test_case_out):
            raise FileNotFoundError(
                f"Output test case file not found: {src_test_case_out}"
            )

        file_operation.copy_file(
            src_test_case_in,
            os.path.join(
                self.root_dir, "test_case", "in", self.sub_assignment.test_case_name
            ),
        )
        file_operation.copy_file(
            src_test_case_out,
            os.path.join(
                self.root_dir, "test_case", "out", self.sub_assignment.test_case_name
            ),
        )

    # def copy_test_program(self):
