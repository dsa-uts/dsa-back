from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ....crud.db import users
from ....dependencies import get_db
from ....schemas import UserCreate, User, UserDelete
from typing import List, Optional
import logging

logging.basicConfig(level=logging.INFO)

router = APIRouter()


@router.post("/register", response_model=User)
async def create_user(
    user: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(users.get_current_user),
):
    if not current_user.is_admin or current_user.disabled:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        return users.create_user(db=db, user=user)
    except HTTPException as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/all", response_model=List[User])
async def get_users_list(
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(users.get_current_user),
):
    if current_user is None or not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden")

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
