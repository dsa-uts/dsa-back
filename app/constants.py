import os
from dotenv import load_dotenv

load_dotenv()

# --- データベース関連 ---
DATABASE_USER = os.getenv("DATABASE_USER")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_NAME = os.getenv("DATABASE_NAME")

ADMIN_USER = os.getenv("INIT_ADMIN_USER")
ADMIN_PASSWORD = os.getenv("INIT_ADMIN_PASSWORD")
ADMIN_START_DATE = os.getenv("INIT_ADMIN_START_DATE")
ADMIN_END_DATE = os.getenv("INIT_ADMIN_END_DATE")

# --- パス関連 ---
TEMP_UPLOAD_DIR = os.getenv("TEMP_UPLOAD_DIR_PATH", "/app/temp_upload")
UPLOAD_DIR = os.getenv("UPLOAD_DIR_PATH", "/app/uploaded_file")

TEST_CASE_DIR_PATH = os.getenv("TEST_CASE_DIR_PATH", "/app/dsa_test_case")
TEST_PROGRAM_DIR_PATH = os.getenv("TEST_PROGRAM_DIR_PATH", "/app/dsa_test_program")
