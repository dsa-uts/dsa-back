from ...api.api_v1.dependencies import (
    pwd_context,
    SECRET_KEY,
    ALGORITHM,
)
from typing import Union, Optional, Tuple
from datetime import datetime, timedelta
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from ...classes.models import AccessToken, RefreshToken
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import pytz
from fastapi import HTTPException

tokyo_tz = pytz.timezone("Asia/Tokyo")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def update_token_expiration(db: Session, auth_token: RefreshToken) -> None:
    """トークンの有効期限が切れている場合に、is_expired フラグを True に更新する"""
    auth_token.is_expired = True
    db.commit()


def verify_refresh_token(db: Session, token: str) -> Optional[Tuple[int, str]]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        username: str = payload.get("sub")
        if user_id is None or username is None:
            return None

        auth_token = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.code == token,
                RefreshToken.user_id == user_id,
                RefreshToken.is_expired == False,
            )
            .first()
        )

        if not auth_token:
            raise HTTPException(status_code=401, detail="No matching token found")
        if tokyo_tz.localize(auth_token.expired_at) <= datetime.now(
            pytz.timezone("Asia/Tokyo")
        ):
            if not auth_token.is_expired:
                update_token_expiration(db, auth_token)
            raise HTTPException(status_code=401, detail="Token expired")

        return (user_id, username)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token decoding failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def update_token_expiration(db: Session, token: AccessToken) -> None:
    token.is_expired = True
    db.commit()


def is_valid_token(db: Session, token: str) -> bool:
    """トークンが有効かどうかを確認し、必要に応じてトークンの状態を更新する"""
    auth_code = db.query(AccessToken).filter(AccessToken.code == token).first()
    if auth_code is None:
        return False
    if auth_code.is_expired:
        return False
    if tokyo_tz.localize(auth_code.expired_at) < datetime.now(tokyo_tz):
        update_token_expiration(db, auth_code)
        return False
    return True


def create_access_token(
    data: dict, db: Session, expires_delta: Union[timedelta, None] = None
):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(tokyo_tz) + expires_delta
    else:
        expire = datetime.now(tokyo_tz) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    auth_code = AccessToken(
        code=encoded_jwt,
        expired_at=expire,
        user_id=data["user_id"],
        is_expired=False,
    )
    db.add(auth_code)
    db.commit()
    return encoded_jwt


def create_refresh_token(
    data: dict, db: Session, expires_delta: Union[timedelta, None] = None
):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(tokyo_tz) + expires_delta
    else:
        expire = datetime.now(tokyo_tz) + timedelta(minutes=24 * 60)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    auth_code = RefreshToken(
        token=encoded_jwt,
        expired_at=expire,
        user_id=data["user_id"],
        is_expired=False,
    )
    db.add(auth_code)
    db.commit()
    return encoded_jwt


def invalidate_token(db: Session, token: str):
    decoded_jwt = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    user_id = decoded_jwt.get("user_id")
    if user_id:
        auth_code = (
            db.query(AccessToken)
            .filter(AccessToken.user_id == user_id, AccessToken.code == token)
            .all()
        )
        for code in auth_code:
            code.is_expired = True
        db.commit()
        return True
    return False


def invalidate_refresh_token(db: Session, token: str):
    decoded_jwt = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    user_id = decoded_jwt.get("user_id")
    if user_id:
        auth_code = (
            db.query(RefreshToken)
            .filter(RefreshToken.user_id == user_id, RefreshToken.code == token)
            .all()
        )
        for code in auth_code:
            code.is_expired = True
        db.commit()
        return True
    return False
