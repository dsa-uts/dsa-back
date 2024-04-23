from .schemas import UserBase

GUEST = UserBase(
    id=-1,
    username="guest",
    is_admin=False,
    disabled=True,
)

UPLOAD_DIR = "/app/uploadedFiles"

TEST_PROGRAM_DIR = "/app/dsa_test_program"
