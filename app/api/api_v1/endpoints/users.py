from fastapi import (
    UploadFile,
    APIRouter,
    Depends,
    HTTPException,
    Security,
    status,
)
from typing import Annotated
from sqlalchemy.orm import Session
from ....crud.db import users
from ....dependencies import get_db
from ....classes.schemas import UserCreate, User, UserDelete
from typing import List
import logging
from pydantic import ValidationError
import pandas as pd
from app.api.api_v1.endpoints import authenticate_util
from app.classes import schemas
from datetime import timedelta
from app.crud.db import users as crud_users

logging.basicConfig(level=logging.DEBUG)

router = APIRouter()


@router.post("/register")
async def create_user(
    user: UserCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        User, Security(authenticate_util.get_current_user, scopes=["account"])
    ],
) -> schemas.Message:
    if db is None or current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized"
        )

    # パスワードのハッシュ化
    hashed_password = authenticate_util.get_password_hash(user.plain_password)

    ########################### Vital ######################################
    # 現状は、role: adminのユーザをAPI経由で作成することはできないようにする。
    if user.role == schemas.Role.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden to create admin user.",
        )
    #######################################################################

    user_record = schemas.UserRecord(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        hashed_password=hashed_password,
        role=user.role,
        disabled=user.disabled,
        created_at=authenticate_util.get_current_time(),
        active_start_date=(
            authenticate_util.get_current_time()
            if user.active_start_date is None
            else user.active_start_date
        ),
        active_end_date=(
            authenticate_util.get_current_time() + timedelta(days=365)
            if user.active_end_date is None
            else user.active_end_date
        ),
    )

    try:
        crud_users.create_user(db, user_record)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return schemas.Message(message="ユーザーが正常に作成されました。")


@router.post("/register/multiple")
async def register_multiple_users(
    upload_file: UploadFile,
    db: Annotated[Session, Depends(get_db)],
    # current_userが使われることはないが、sccountというスコープを持つユーザー(admin)のみがこのAPIを利用できるようにするために必要
    current_user: Annotated[
        User, Security(authenticate_util.get_current_user, scopes=["account"])
    ],
) -> schemas.Message:
    if upload_file.filename.endswith(".csv"):
        df = pd.read_csv(upload_file.file)
    elif upload_file.filename.endswith(".xlsx"):
        df = pd.read_excel(upload_file.file)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a .csv or .xlsx file.",
        )

    required_columns = [
        "user_id",
        "username",
        "email",
        "password",
        "role",
        "active_start_date",
        "active_end_date",
    ]
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required columns in the file: {', '.join(missing_columns)}",
        )

    error_messages = []
    for index, row in df.iterrows():
        if pd.isna(row["password"]) or row["password"] == "":
            generated_password = authenticate_util.generate_password()
            df.at[index, "password"] = generated_password
        else:
            generated_password = row["password"]

        try:
            user_data = schemas.UserRecord(
                user_id=str(row["user_id"]),
                username=row["username"],
                email=row["email"],
                hashed_password=authenticate_util.get_password_hash(generated_password),
                role=schemas.Role(row["role"]),
                disabled=False,
                active_start_date=pd.to_datetime(row["active_start_date"]).tz_localize(
                    "Asia/Tokyo"
                ),
                active_end_date=pd.to_datetime(row["active_end_date"]).tz_localize(
                    "Asia/Tokyo"
                ),
            )

            crud_users.create_user(db, user_data)
        except Exception as e:
            error_messages.append(f"Error creating user {row['user_id']}: {str(e)}")

    # Return the updated file to the client
    return schemas.Message(
        message="user registrations done.", error_messages=error_messages
    )


@router.get("/all", response_model=List[User])
async def get_users_list(
    db: Annotated[Session, Depends(get_db)],
    # current_userが使われることはないが、view_usersというスコープを持つユーザー(admin, manager)のみがこのAPIを利用できるようにするために必要
    current_user: Annotated[
        User, Security(authenticate_util.get_current_user, scopes=["view_users"])
    ],
):
    # パスワードを除外して返す
    return [user.model_dump(exclude={"hashed_password"}) for user in users.get_users(db=db)]


@router.post("/delete")
async def delete_users(
    user_ids: UserDelete,
    db: Annotated[Session, Depends(get_db)],
    # current_userが使われることはないが、accountというスコープを持つユーザー(admin)のみがこのAPIを利用できるようにするために必要
    current_user: Annotated[
        User, Security(authenticate_util.get_current_user, scopes=["account"])
    ],
):
    try:
        await users.delete_users(db=db, user_ids=user_ids.user_ids)
        return {"msg": "ユーザーが正常に削除されました。"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
