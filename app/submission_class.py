from .crud import file_operation
from . import constants as constants
import os
from sqlalchemy.orm import Session
from .crud.db import assignments as db_assignments
from .models import SubAssignment
from abc import ABC, abstractmethod
from typing import List, Optional
from . import constants
from fastapi import UploadFile, File
import logging

logging.basicConfig(level=logging.INFO)


class SubmissionToolBaseClass:
    id: int
    test_dir_name: Optional[str]
    unique_ids: List[str]
    root_dir_path: str
    file: UploadFile = File(...)

    def __init__(
        self, id: int, unique_ids: List[str], file: UploadFile, test_dir_name: str
    ) -> None:
        self.id = id
        self.test_dir_name = test_dir_name
        self.unique_ids = unique_ids
        self.file = file

    def create_user_dir(self):
        for unique_id in self.unique_ids:
            bin_path = os.path.join(self.root_dir_path, unique_id, "bin")
            file_operation.mkdir(bin_path)
            submit_path = os.path.join(self.root_dir_path, unique_id, "submit")
            file_operation.mkdir(submit_path)
            logging.info(f"bin_path: {bin_path}")
            logging.info(f"submit_path: {submit_path}")

    # @abstractmethod
    @abstractmethod
    def get_test_program_dir(self, db: Session) -> str:
        pass


class FormatCheckClass(SubmissionToolBaseClass):
    unique_id: str
    sub_assignment: SubAssignment
    test_program_dir: str

    def __init__(
        self, sub_assignment: SubAssignment, unique_ids: List[str], file: UploadFile
    ):
        super().__init__(
            sub_assignment.id, unique_ids, file, sub_assignment.assignment.test_dir_name
        )
        self.sub_assignment = sub_assignment
        self.unique_id = self.unique_ids[0]
        self.root_dir_path = os.path.join(constants.UPLOAD_DIR, self.unique_id)

    def create_test_program_dir(self):
        try:
            dst_test_program_dir = os.path.join(
                self.root_dir_path,
                "test_src",
                self.test_dir_name,
                self.sub_assignment.test_dir_name,
            )
            src_test_program_dir = os.path.join(
                constants.TEST_PROGRAM_DIR_PATH,
                self.test_dir_name,
                self.sub_assignment.test_dir_name,
            )
            file_operation.copy_directory(src_test_program_dir, dst_test_program_dir)
            file_operation.delete_dir(os.path.join(dst_test_program_dir, "makefile"))
        except Exception as e:
            logging.error(f"An error occurred: {e}")

    def create_test_case_dir(self):
        try:
            dst_test_case_in = os.path.join(
                self.root_dir_path,
                "test_case",
                self.test_dir_name,
                self.sub_assignment.test_dir_name,
                "in",
            )
            dst_test_case_out = os.path.join(
                self.root_dir_path,
                "test_case",
                self.test_dir_name,
                self.sub_assignment.test_dir_name,
                "out",
            )
            file_operation.mkdir(dst_test_case_in)
            file_operation.mkdir(dst_test_case_out)
            src_test_case_in = os.path.join(
                constants.TEST_CASE_DIR_PATH,
                self.test_dir_name,
                self.sub_assignment.test_dir_name,
                "in",
                self.sub_assignment.test_case_name,
            )
            src_test_case_out = os.path.join(
                constants.TEST_CASE_DIR_PATH,
                self.test_dir_name,
                self.sub_assignment.test_dir_name,
                "out",
                self.sub_assignment.test_case_name,
            )
            file_operation.copy_file(
                src_test_case_in,
                os.path.join(dst_test_case_in, self.sub_assignment.test_case_name),
            )
            file_operation.copy_file(
                src_test_case_out,
                os.path.join(dst_test_case_out, self.sub_assignment.test_case_name),
            )
        except Exception as e:
            logging.error(f"An error occurred: {e}")

    def set_submission_file(self):
        try:
            dst_file_path = os.path.join(
                self.root_dir_path,
                self.unique_id,
                "submit",
                self.file.filename,
            )
            file_operation.write_uploaded_file(self.file, dst_file_path)
        except Exception as e:
            logging.error(f"An error occurred: {e}")

    def build_docker_mount_directory(self):
        self.create_user_dir()
        self.create_test_case_dir()
        self.create_test_program_dir()
        self.set_submission_file()
        logging.info("build_docker_mount_directory done")
