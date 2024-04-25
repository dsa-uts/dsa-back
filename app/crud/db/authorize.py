from ...api.api_v1.dependencies import (
    pwd_context,
    SECRET_KEY,
    ALGORITHM,
)
from typing import Union
from datetime import datetime, timedelta
from jose import jwt
from sqlalchemy.orm import Session
from ...classes.models import AuthCode
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import pytz

tokyo_tz = pytz.timezone("Asia/Tokyo")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def expire_token(db: Session, token: str):
    return
    auth_code = db.query(AuthCode).filter(AuthCode.code == token).first()
    current_time = datetime.now(tokyo_tz)
    if auth_code.expired_at < current_time:
        auth_code.is_expired = True
        # とりあえずlogoutの時だけexpireするようにしとく
        # db.commit()


def is_valid_token(db: Session, token: str) -> bool:
    auth_code = db.query(AuthCode).filter(AuthCode.code == token).first()
    if auth_code is None:
        return False
    expire_token(db, token)
    if auth_code.is_expired == False:
        return True
    return False


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
    auth_code = AuthCode(
        code=encoded_jwt,
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
            db.query(AuthCode)
            .filter(AuthCode.user_id == user_id, AuthCode.code == token)
            .all()
        )
        for code in auth_code:
            code.is_expired = True
        db.commit()
        return True
    return False
