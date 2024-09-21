from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from ..dependencies import (
    pwd_context,
    oauth2_scheme,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_MINUTES,
    SCOPES,
)
from sqlalchemy.orm import Session
from ....classes import schemas
from ....classes.schemas import UserBase, Token, JWTTokenPayload, UserRecord
from ....crud.db import authorize, utils, users
from ....classes import models
from ....dependencies import get_db
import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from typing import Annotated
from fastapi.security import OAuth2PasswordRequestForm
from datetime import timedelta, datetime, timezone
import pytz
from typing import Optional

import logging

router = APIRouter()

logging.basicConfig(level=logging.DEBUG)

tokyo_tz = pytz.timezone("Asia/Tokyo")

access_token_duration = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
refresh_token_duration = timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def is_past(ts: datetime) -> bool:
    return tokyo_tz.localize(ts) <= datetime.now(tokyo_tz)


def authenticate_user(
    db: Session, username: str, plain_password: str
) -> UserRecord | bool:
    user: UserRecord | None = users.get_user(db=db, user_id=username)
    if user is None:
        return False
    if not verify_password(
        plain_password=plain_password, hashed_password=user.hashed_password
    ):
        return False
    return user


def get_password_hash(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def is_token_expired(payload: JWTTokenPayload) -> bool:
    if tokyo_tz.localize(payload.expire) <= datetime.now(tokyo_tz):
        return True
    return False


# JWTトークンをデコードし、ペイロードを返す
def verify_token(token: str) -> JWTTokenPayload:
    scope_str = ""
    try:
        # tokenのデコード
        raw_token_payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_payload = JWTTokenPayload.model_validate(raw_token_payload)
        scope_str = " ".join(token_payload.scopes)
    except (InvalidTokenError, ValidationError):
        # トークンのフォーマットが無効、または各フィールドのValidationに失敗した場合
        # NOTE: authenticate_valueの設定については、ここまで厳密にやらなくても問題ない
        if scope_str == "":
            authenticate_value = "Bearer"
        else:
            authenticate_value = f'Bearer scope="{scope_str}"'
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": authenticate_value},
        )

    return token_payload


"""
/api/v1/authorize/...以下のエンドポイントの定義
"""


@router.post("/token")
async def login_for_access_token(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
) -> Token:
    logging.info(f"login_for_access_token, form_data: {form_data.username}")
    user = authenticate_user(
        db=db, username=form_data.username, plain_password=form_data.password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect user_id or password",
        )

    login_at = datetime.now(tz=tokyo_tz)

    # アクセストークンのペイロード
    access_token_payload = JWTTokenPayload(
        sub=user.user_id,
        login=login_at,
        expire=login_at + access_token_duration,
        scopes=form_data.scopes,
    )

    # リフレッシュトークンのペイロード
    refresh_token_payload = JWTTokenPayload(
        sub=user.user_id,
        login=login_at,
        expire=login_at + refresh_token_duration,
        scopes=form_data.scopes,
    )

    ############################## Vital Code ##################################
    ############################################################################
    # form_data.scopesでリクエストされているscopeが、ユーザに認められているスコープと合致しているか検証する
    # ユーザに認められているスコープ(権限情報)の取得
    permitted_scope_list = (
        [] if UserRecord.role.value not in SCOPES else SCOPES[UserRecord.role.value]
    )
    # リクエストされたスコープが、そのユーザに対して全て認められているか調べる
    for requested_scope in form_data.scopes:
        if requested_scope not in permitted_scope_list:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="your requested access rights is not permitted.",
            )
    ############################################################################
    ############################################################################

    # access_token, refresh_tokenを発行する
    access_token: str = jwt.encode(
        data=access_token_payload.model_dump(), key=SECRET_KEY, algorithm=ALGORITHM
    )
    refresh_token: str = jwt.encode(
        data=refresh_token_payload.model_dump(), key=SECRET_KEY, algorithm=ALGORITHM
    )
    response.delete_cookie(key="refresh_token")
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="Lax",
        expires=datetime.now(timezone.utc) + refresh_token_duration,
    )

    # LoginHistoryに登録
    authorize.add_login_history(
        db=db,
        login_history_record=schemas.LoginHistoryRecord(
            user_id=user.user_id,
            login_at=login_at,
            logout_at=login_at + access_token_duration,
            refresh_count=0,
            current_access_token=access_token,
            current_refresh_token=refresh_token,
        ),
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        login_time=login_at,
        user_id=user.user_id,
        role=UserRecord.role,
    )


@router.get("/token/update")
async def update_token(
    response: Response,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    token: Annotated[str, Depends(oauth2_scheme)],
) -> str:
    logging.info(f"update_token, token: {token}")

    # アクセストークンのデコード
    access_token_payload = verify_token(token=token)

    # アクセストークンの有効期限が切れていない場合、元のアクセストークンを返す
    if not is_past(access_token_payload.expire):
        return token

    # アクセストークンが無効な場合、リフレッシュトークンを確認
    old_refresh_token = request.cookies.get("refresh_token")

    if old_refresh_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )

    # リフレッシュトークンのデコード
    refresh_token_payload = verify_token(token=old_refresh_token)

    # リフレッシュトークンの有効期限が切れている場合、何も返さない
    if is_past(refresh_token_payload.expire):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    # アクセストークンとリフレッシュトークンが正しいペアかどうか検証する
    if (
        access_token_payload.sub != refresh_token_payload
        or access_token_payload.login != refresh_token_payload.login
        or set(access_token_payload.scopes) != set(refresh_token_payload.scopes)
        or access_token_payload.role != refresh_token_payload.role
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token and refresh token pair",
        )

    user_id = access_token_payload.sub
    login_at = access_token_payload.login

    # ログイン履歴を取得する
    login_history = authorize.get_login_history(
        db=db, user_id=user_id, login_at=login_at
    )

    if login_history is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="login history not found"
        )

    # リフレッシュ回数が上限値を超えているのならば、該当ログイン履歴を削除し、HTTPExceptionを吐く
    if login_history.refresh_count > 3:
        authorize.remove_login_history(db=db, user_id=user_id, login_at=login_at)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="your login session has expired"
        )

    # アクセストークンが無効でリフレッシュトークンが有効のとき、
    # 新しいアクセストークンとリフレッシュトークンを発行する
    new_access_token_payload = JWTTokenPayload(
        sub=access_token_payload.sub,
        login=access_token_payload.login,
        ################## Vital ###############################################
        # 以前のアクセストークンの失効時間からアクセストークンの有効期間の分だけ伸ばす
        expire=access_token_payload.expire + access_token_duration,
        ########################################################################
        scopes=access_token_payload.scopes
    )
    new_access_token: str = jwt.encode(
        data=new_access_token_payload.model_dump(), key=SECRET_KEY, algorithm=ALGORITHM
    )
    
    new_refresh_token_payload = JWTTokenPayload(
        sub=refresh_token_payload.sub,
        login=refresh_token_payload.login,
        ################## Vital ###############################################
        # 以前の**アクセストークン**の失効時間から**リフレッシュトークン**の有効期間の分だけ
        # 伸ばす
        expire=access_token_payload.expire + refresh_token_duration,
        ########################################################################
        scopes=refresh_token_payload.scopes
    )
    new_refresh_token: str = jwt.encode(
        data=new_refresh_token_payload.model_dump(), key=SECRET_KEY, algorithm=ALGORITHM
    )
    
    # 新しいトークンペアをLoginHistoryに登録 + refresh_countを1加算
    login_history.logout_at = new_access_token_payload.expire
    login_history.refresh_count += 1
    login_history.current_access_token = new_access_token
    login_history.current_refresh_token = new_refresh_token
    authorize.update_login_history(db=db, login_history_record=login_history)
    
    # 新しいリフレッシュトークンをクッキーにセット
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=False,
        samesite="Lax",
        expires=datetime.now(timezone.utc) + refresh_token_duration
    )
    
    return new_access_token

@router.post("/token/validate")
async def validate_token(
    token: str = Depends(oauth2_scheme),
) -> bool:
    # アクセストークンをデコードする
    token_payload = verify_token(token=token)
    
    # 有効期限が過ぎているのなら、False, 過ぎていないならTrue
    return not is_past(token_payload.expire)


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme),
):
    # アクセストークンをデコードする
    access_token_payload = verify_token(token=token)
    
    # 該当するLoginHistoryを削除
    authorize.remove_login_history(
        db=db,
        user_id=access_token_payload.sub,
        login_at=access_token_payload.login
    )
    
    # クッキーからrefresh_tokenを削除
    response.delete_cookie(key="refresh_token")
    return {"msg": "ログアウトしました。"}
