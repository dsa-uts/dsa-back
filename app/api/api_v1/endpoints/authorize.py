from fastapi import APIRouter, Depends, HTTPException, Response, status
from ..dependencies import (
    oauth2_scheme,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_MINUTES,
)
from sqlalchemy.orm import Session
from ....classes.schemas import UserBase, Token
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
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
) -> Token:
    user = users.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    access_token = authorize.create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=access_token_expires,
        db=db,
    )
    refresh_token = authorize.create_refresh_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=refresh_token_expires,
        db=db,
    )

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=True,
        samesite="Strict",
    )
    tokyo_tz = pytz.timezone("Asia/Tokyo")
    login_time = datetime.now(tokyo_tz).strftime("%Y-%m-%d %H:%M:%S")
    user_id = user.id
    is_admin = user.is_admin
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        login_time=login_time,
        user_id=user_id,
        is_admin=is_admin,
    )


@router.post("/refresh")
async def refresh_access_token(
    response: Response,
    db: Session = Depends(get_db),
    refresh_token: str = Depends(oauth2_scheme),
) -> Token:
    result = authorize.verify_refresh_token(db, refresh_token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    user_id, username = result

    new_access_token = authorize.create_access_token(
        data={"sub": username, "user_id": user_id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        db=db,
    )
    return {"access_token": new_access_token, "token_type": "bearer"}


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
        authorize.invalidate_refresh_token(db, token)
        return {"msg": "ログアウトに成功しました。"}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
