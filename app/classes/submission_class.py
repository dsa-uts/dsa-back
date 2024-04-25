from ..crud import file_operation
from .. import constants as constants
import os
from sqlalchemy.orm import Session
from ..crud.db import assignments as db_assignments
from . import models
from abc import ABC, abstractmethod
from typing import List, Optional
from .. import constants
from fastapi import UploadFile, File
import logging
from .schemas import File
import json

logging.basicConfig(level=logging.INFO)


class SubmissionToolBaseClass:
    id: int
    test_dir_name: Optional[str]
    unique_id: str  # 提出されたファイルに対する識別子
    unique_ids: Optional[List[str]]
    root_dir_path: str
    file: File
    sub_assignments: Optional[List[models.SubAssignment]]

    def __init__(
        self,
        id: int,
        unique_id: str,
        file: File,
        test_dir_name: str,
        sub_assignments: Optional[List[models.SubAssignment]] = None,
    ) -> None:
        self.id = id
        self.test_dir_name = test_dir_name
        self.unique_id = unique_id
        self.file = file
        self.root_dir_path = os.path.join(constants.UPLOAD_DIR, self.unique_id)
        self.sub_assignments = sub_assignments

    def __init__(
        self,
        id: int,
        unique_id: str,
        unique_ids: List[str],
        file: File,
        test_dir_name: str,
        sub_assignments: Optional[List[models.SubAssignment]] = None,
    ) -> None:
        self.id = id
        self.test_dir_name = test_dir_name
        self.unique_id = unique_id
        self.unique_ids = unique_ids
        self.file = file
        self.root_dir_path = os.path.join(constants.UPLOAD_DIR, self.unique_id)
        self.sub_assignments = sub_assignments

    def create_user_dir(self):
        for unique_id in self.unique_ids:
            submit_path = os.path.join(self.root_dir_path, unique_id, "submit")
            file_operation.mkdir(submit_path)
            for sub_assignment in self.sub_assignments:
                bin_path = os.path.join(
                    self.root_dir_path,
                    unique_id,
                    "bin",
                    self.test_dir_name,
                    sub_assignment.test_dir_name,
                )
                file_operation.mkdir(bin_path)

    def set_makefile(self):
        try:
            src_makefile_path = os.path.join(
                constants.TEST_PROGRAM_DIR_PATH,
                "makefile",
            )
            dst_makefile_dir_path = os.path.join(self.root_dir_path, "makefile")
            file_operation.mkdir(dst_makefile_dir_path)
            file_operation.copy_file(
                src_makefile_path, os.path.join(dst_makefile_dir_path, "makefile")
            )
        except Exception as e:
            logging.error(f"An error occurred at set_makefile: {e}")

    @abstractmethod
    def create_test_case_dir(self):
        pass

    @abstractmethod
    def create_test_program_dir(self):
        pass

    @abstractmethod
    def build_docker_mount_directory(self):
        pass

    @abstractmethod
    def create_setting_json(self):
        pass


class SubmissionJsonBuilder:
    root_dir_path: str
    unique_ids: List[str]
    sub_assignments: List[models.SubAssignment]

    def __init__(
        self,
        root_dir_path: str,
        unique_ids: List[str],
        sub_assignments: List[models.SubAssignment],
    ):
        self.root_dir_path = root_dir_path
        self.unique_ids = unique_ids
        self.sub_assignments = sub_assignments


class FormatCheckClass(SubmissionToolBaseClass):
    sub_assignment: models.SubAssignment

    def __init__(
        self,
        sub_assignments: List[models.SubAssignment],
        unique_id: str,
        unique_ids: List[str],
        file: File,
    ):
        super().__init__(
            sub_assignments[0].id,
            unique_id,
            unique_ids,
            file,
            sub_assignments[0].assignment.test_dir_name,
            sub_assignments,
        )
        self.sub_assignment = sub_assignments[0]

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
            logging.error(f"An error occurred at create_test_program_dir: {e}")

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
            logging.error(f"An error occurred at create_test_case_dir: {e}")

    def set_submission_file(self):
        try:
            dst_file_path = os.path.join(
                self.root_dir_path,
                self.unique_id,
                "submit",
                self.file.filename,
            )
            file_operation.copy_file(self.file.file_path, dst_file_path)
        except Exception as e:
            logging.error(f"An error occurred at set_submission_file: {e}")

    def build_setting_json(self, function_tests: List[models.FunctionTest]):
        setting = {"unique_id": self.unique_ids, "assignment": {}}
        for func_test in function_tests:
            report_name = self.test_dir_name
            sub_name = self.sub_assignment.test_dir_name
            src_name = self.sub_assignment.required_file_name
            if report_name not in setting["assignment"]:
                setting["assignment"][report_name] = {}
            setting["assignment"][report_name][sub_name] = {
                "src_name": src_name,
                "functions": {},
            }
            if func_test.id == self.id and func_test.sub_id == self.sub_assignment.id:
                exec_command = (
                    func_test.exec_command
                    if func_test.exec_command
                    else f"./{{unique_id}}/bin/{report_name}/{sub_name}/{func_test.func_name}"
                )
            function_detail = {
                "name": func_test.func_name,
                "exec_command": exec_command,
            }
            setting["assignment"][report_name][sub_name]["functions"][
                func_test.func_name
            ] = function_detail
        return setting

    def create_setting_json(self, function_tests: List[models.FunctionTest]):
        try:
            setting = self.build_setting_json(function_tests)
            setting_json_path = os.path.join(
                self.root_dir_path, "makefile", "setting.json"
            )
            with open(setting_json_path, "w") as f:
                json.dump(setting, f, indent=4)
        except Exception as e:
            logging.error(f"An error occurred in create_setting_json: {e}")

    def build_docker_mount_directory(self, function_tests: List[models.FunctionTest]):
        self.create_user_dir()
        self.create_test_case_dir()
        self.create_test_program_dir()
        self.set_submission_file()
        self.set_makefile()
        self.create_setting_json(function_tests)
        logging.info("build_docker_mount_directory done")


class GradingClass(SubmissionToolBaseClass):
    sub_assignments: List[
        models.SubAssignment
    ]  # 1つの課題に対して複数の提出物があるためList

    def __init__(
        self,
        sub_assignments: List[models.SubAssignment],
        unique_id: str,
        file: UploadFile,
    ):
        super().__init__(
            sub_assignments[0].id,
            unique_id,
            file,
            sub_assignments[0].assignment.test_dir_name,
        )
        self.sub_assignments = sub_assignments

    def open_compressed_file(self):
        dst_compressed_file_path = os.path.join(self.root_dir_path, self.file.filename)
        file_operation.write_uploaded_file(self.file, dst_compressed_file_path)
        extracted_items: List[str] = file_operation.extract_compressed_file(
            dst_compressed_file_path, self.root_dir_path
        )
        # 一応Listにしてるけど解凍するとディレクトリが1つ出てくるはず．
        # そのディレクトリ名をunique_idに変更する．
        file_operation.rename_dir(extracted_items[0], self.unique_id)

    def build_docker_mount_directory(self):
        self.create_user_dir()


# --- あとでSRPを意識してリファクタリングするかも． ---

# class TestProgramDirectoryCreator:
#     root_dir_path: str
#     test_dir_name: str
#     sub_assignments: List[models.SubAssignment]

#     def __init__(
#         self,
#         root_dir_path: str,
#         test_dir_name: str,
#         sub_assignments: List[models.SubAssignment],
#     ):
#         self.root_dir_path = root_dir_path
#         self.test_dir_name = test_dir_name
#         self.sub_assignments = sub_assignments

#     def create(self):
#         for sub_assignment in self.sub_assignments:
#             dst_test_program_dir = os.path.join(
#                 self.root_dir_path,
#                 "test_src",
#                 self.test_dir_name,
#                 sub_assignment.test_dir_name,
#             )
#             src_test_program_dir = os.path.join(
#                 constants.TEST_PROGRAM_DIR_PATH,
#                 self.test_dir_name,
#                 sub_assignment.test_dir_name,
#             )
#             file_operation.copy_directory(src_test_program_dir, dst_test_program_dir)
#             file_operation.delete_dir(os.path.join(dst_test_program_dir, "makefile"))


# class TestCaseDirectoryCreator:
#     root_dir_path: str
#     test_dir_name: str
#     sub_assignments: List[models.SubAssignment]

#     def __init__(
#         self,
#         root_dir_path: str,
#         test_dir_name: str,
#         sub_assignments: List[models.SubAssignment],
#     ):
#         self.root_dir_path = root_dir_path
#         self.test_dir_name = test_dir_name
#         self.sub_assignments = sub_assignments

#     def create_for_format_check(self):
#         for sub_assignment in self.sub_assignments:
#             dst_test_case_in = os.path.join(
#                 self.root_dir_path,
#                 "test_case",
#                 self.test_dir_name,
#                 sub_assignment.test_dir_name,
#                 "in",
#             )
#             dst_test_case_out = os.path.join(
#                 self.root_dir_path,
#                 "test_case",
#                 self.test_dir_name,
#                 sub_assignment.test_dir_name,
#                 "out",
#             )
#             file_operation.mkdir(dst_test_case_in)
#             file_operation.mkdir(dst_test_case_out)
#             src_test_case_in = os.path.join(
#                 constants.TEST_CASE_DIR_PATH,
#                 self.test_dir_name,
#                 sub_assignment.test_dir_name,
#                 "in",
#                 sub_assignment.test_case_name,
#             )
#             src_test_case_out = os.path.join(
#                 constants.TEST_CASE_DIR_PATH,
#                 self.test_dir_name,
#                 sub_assignment.test_dir_name,
#                 "out",
#                 sub_assignment.test_case_name,
#             )
#             file_operation.copy_file(
#                 src_test_case_in,
#                 os.path.join(dst_test_case_in, sub_assignment.test_case_name),
#             )
#             file_operation.copy_file(
#                 src_test_case_out,
#                 os.path.join(dst_test_case_out, sub_assignment.test_case_name),
#             )

#     def create_for_grading(self):
#         for sub_assignment in self.sub_assignments:
#             dst_test_case = os.path.join(
#                 self.root_dir_path,
#                 "test_case",
#                 self.test_dir_name,
#                 sub_assignment.test_dir_name,
#             )
#             src_test_case = os.path.join(
#                 constants.TEST_CASE_DIR_PATH,
#                 self.test_dir_name,
#                 sub_assignment.test_dir_name,
#             )
#             file_operation.copy_directory(src_test_case, dst_test_case)

#     def create(self, for_format_check: bool = False):
#         if for_format_check:
#             self.create_for_format_check()
#         else:
#             self.create_for_grading()
