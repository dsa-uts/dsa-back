from fastapi import UploadFile, File, APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ....crud.db import users
from ....crud.utils import generate_password
from ....dependencies import get_db
from ....classes.schemas import UserCreate, User, UserDelete
from typing import List, Optional
import logging
import pandas as pd
from tempfile import NamedTemporaryFile
from fastapi.responses import FileResponse

logging.basicConfig(level=logging.DEBUG)

router = APIRouter()


@router.post("/register", response_model=User)
async def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(users.get_current_user),
):
    if not current_user.is_admin or current_user.disabled:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        return users.create_user(db=db, user=user)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/register/multiple")
async def register_multiple_users(
    upload_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(users.get_current_user),
):
    if not current_user.is_admin or current_user.disabled:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if upload_file.filename.endswith(".csv"):
        df = pd.read_csv(upload_file.file)
    elif upload_file.filename.endswith(".xlsx"):
        df = pd.read_excel(upload_file.file)
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Please upload a .csv or .xlsx file.",
        )

    required_columns = [
        "student_id",
        "username",
        "email",
        "password",
        "is_admin",
        "active_start_date",
        "active_end_date",
    ]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns in the file: {', '.join(missing_columns)}",
        )

    users_to_create = []
    for index, row in df.iterrows():
        if pd.isna(row["password"]) or row["password"] == "":
            generated_password = generate_password()
            df.at[index, "password"] = generated_password
        else:
            generated_password = row["password"]

        user_data = UserCreate(
            student_id=str(row["student_id"]),
            username=row["username"],
            email=row["email"],
            password=generated_password,
            is_admin=row["is_admin"],
            active_start_date=pd.to_datetime(row["active_start_date"]).tz_localize(
                "Asia/Tokyo"
            ),
            active_end_date=pd.to_datetime(row["active_end_date"]).tz_localize(
                "Asia/Tokyo"
            ),
        )

        # Register user in the database
        error_message = users.create_user(db, user_data)
        if error_message:
            # If an error occurred, add it to the password column
            df.at[index, "password"] = error_message

    # Save the updated DataFrame to a temporary file
    with NamedTemporaryFile(
        delete=False,
        suffix=".xlsx" if upload_file.filename.endswith(".xlsx") else ".csv",
    ) as temp_file:
        if upload_file.filename.endswith(".xlsx"):
            df.to_excel(temp_file.name, index=False)
        else:
            df.to_csv(temp_file.name, index=False)

        temp_file_path = temp_file.name

    # Return the updated file to the client
    return FileResponse(temp_file_path, filename=f"updated_{upload_file.filename}")


@router.get("/all", response_model=List[User])
async def get_users_list(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(users.get_current_user),
):
    if current_user is None or not current_user.is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return users.get_users(db=db)


@router.post("/delete")
async def delete_users(
    user_ids: UserDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(users.get_current_user),
):
    if current_user is None or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        await users.delete_users(db=db, user_ids=user_ids.user_ids)
        return {"msg": "ユーザーが正常に削除されました。"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
