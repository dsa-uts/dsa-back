from fastapi import APIRouter, Depends, HTTPException, status
from ..dependencies import oauth2_scheme, ACCESS_TOKEN_EXPIRE_MINUTES
from sqlalchemy.orm import Session
from ....schemas import UserBase, Token
from ....crud.db import authorize, utils, users
from ....dependencies import get_db
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta, datetime
import pytz
from typing import Optional

import logging

router = APIRouter()

logging.basicConfig(level=logging.INFO)


@router.post("/token")
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
) -> Token:
    logging.info(f"form_data: {form_data}")
    user = users.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = authorize.create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=access_token_expires,
        db=db,
    )
    tokyo_tz = pytz.timezone("Asia/Tokyo")
    login_time = datetime.now(tokyo_tz).strftime("%Y-%m-%d %H:%M:%S")
    user_id = user.id
    is_admin = user.is_admin
    logging.info(f"username: {user.username}, user_id: {user_id}, is_admin: {is_admin}")
    return Token(
        access_token=access_token,
        token_type="bearer",
        login_time=login_time,
        user_id=user_id,
        is_admin=is_admin,
    )


@router.post("/logout")
async def logout(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token"
        )
    try:
        authorize.invalidate_token(db, token)
        return {"msg": "ログアウトに成功しました。"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
