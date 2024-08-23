from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
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
from datetime import timedelta, datetime, timezone
import pytz
from typing import Optional

import logging

router = APIRouter()

logging.basicConfig(level=logging.DEBUG)


@router.post("/token")
async def login_for_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
) -> Token:
    logging.info(f"login_for_access_token, form_data: {form_data.username}")
    user = users.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect student_id or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    access_token = authorize.create_access_token(
        data={"sub": user.student_id, "user_id": user.id},
        expires_delta=access_token_expires,
        db=db,
    )
    refresh_token = authorize.create_refresh_token(
        data={"sub": user.student_id, "user_id": user.id},
        expires_delta=refresh_token_expires,
        db=db,
    )
    response.delete_cookie(key="refresh_token")
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="Lax",
        expires=datetime.now(timezone.utc) + refresh_token_expires,
    )
    tokyo_tz = pytz.timezone("Asia/Tokyo")
    login_time = datetime.now(tokyo_tz).strftime("%Y-%m-%d %H:%M:%S")
    user_id = user.id
    is_admin = user.is_admin
    return Token(
        access_token=access_token,
        token_type="bearer",
        login_time=login_time,
        user_id=user_id,
        is_admin=is_admin,
    )


@router.get("/token/update")
async def update_token(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    logging.info(f"update_token, token: {token}")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token is not provided",
        )
    try:
        result = authorize.verify_access_token(db, token)
        if result:
            return {"msg": "Token is valid", "is_valid": True, "access_token": token}
    except HTTPException as e:
        logging.info(f"Access token verification failed: {str(e)}")
    # アクセストークンが無効な場合、リフレッシュトークンを確認
    old_refresh_token = request.cookies.get("refresh_token")

    if old_refresh_token:
        refresh_result = authorize.verify_refresh_token(db, old_refresh_token)
        """
        アクセストークンは切れているがリフレッシュトークンは有効の時，
        新しいアクセストークンとリフレッシュトークンを発行する
        """
        if refresh_result:
            user_id, student_id = refresh_result

            # 古いリフレッシュトークンを失効させる
            authorize.invalidate_refresh_token(db, old_refresh_token)

            # 新しいアクセストークンとリフレッシュトークンを生成
            access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            refresh_token_expires = timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)

            new_access_token = authorize.create_access_token(
                data={"sub": student_id, "user_id": user_id},
                expires_delta=access_token_expires,
                db=db,
            )
            new_refresh_token = authorize.create_refresh_token(
                data={"sub": student_id, "user_id": user_id},
                expires_delta=refresh_token_expires,
                db=db,
            )

            # 新しいリフレッシュトークンをクッキーにセット
            response.set_cookie(
                key="refresh_token",
                value=new_refresh_token,
                httponly=True,
                secure=False,
                samesite="Lax",
                expires=datetime.now(timezone.utc) + refresh_token_expires,
            )

            return {
                "msg": "新しいアクセストークンとリフレッシュトークンが発行されました",
                "access_token": new_access_token,
                "token_type": "bearer",
                "is_valid": True,
            }
        else:
            raise HTTPException(status_code=401, detail="invalid refresh token")

    raise HTTPException(status_code=401, detail="invalid token")


@router.post("/token/validate")
async def validate_token(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        return {"msg": "Token is not provided", "is_valid": False}

    result = authorize.verify_access_token(db, token)
    if result:
        return {"msg": "Token is valid", "is_valid": True}
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            is_valid=False,
        )


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token"
        )
    refresh_token = request.cookies.get("refresh_token")
    authorize.invalidate_access_token(db, token)
    authorize.invalidate_refresh_token(db, refresh_token)
    response.delete_cookie(key="refresh_token")
    return {"msg": "ログアウトしました。"}
