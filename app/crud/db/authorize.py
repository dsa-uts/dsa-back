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
import logging

logging.basicConfig(level=logging.DEBUG)

tokyo_tz = pytz.timezone("Asia/Tokyo")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def update_token_expiration(db: Session, auth_token: RefreshToken) -> None:
    """トークンの有効期限が切れている場合に、is_expired フラグを True に更新する"""
    auth_token.is_expired = True
    db.commit()


def is_access_token_expired(db: Session, token: AccessToken) -> bool:
    if tokyo_tz.localize(token.expired_at) <= datetime.now(tokyo_tz):
        if not token.is_expired:
            invalidate_access_token(db, token.token)
        return True
    return False


def is_refresh_token_expired(db: Session, token: RefreshToken) -> bool:
    if tokyo_tz.localize(token.expired_at) <= datetime.now(tokyo_tz):
        if not token.is_expired:
            invalidate_refresh_token(db, token.token)
        return True
    return False


def verify_access_token(db: Session, token: str) -> Optional[Tuple[int, str]]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        student_id: str = payload.get("sub")
        if user_id is None or student_id is None:
            return None
        auth_token = (
            db.query(AccessToken)
            .filter(
                AccessToken.token == token,
                AccessToken.user_id == user_id,
                AccessToken.is_expired == False,
            )
            .first()
        )
        if not auth_token:
            raise HTTPException(
                status_code=401, detail="No matching access token found"
            )
        if is_access_token_expired(db, auth_token):
            raise HTTPException(status_code=401, detail="Token has expired")
        return (user_id, student_id)
    except JWTError:
        try:
            # トークンの期限が切れてdecodeできない場合は，トークンを無効化する
            auth_token = (
                db.query(AccessToken).filter(AccessToken.token == token).first()
            )
            if not auth_token:
                raise HTTPException(
                    status_code=401, detail="No matching access token found"
                )
            if is_access_token_expired(db, auth_token):
                raise HTTPException(status_code=401, detail="Token has expired")
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def verify_refresh_token(db: Session, token: str) -> Optional[Tuple[int, str]]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        student_id: str = payload.get("sub")
        if user_id is None or student_id is None:
            return None

        auth_token = (
            db.query(RefreshToken)
            .filter(
                RefreshToken.token == token,
                RefreshToken.user_id == user_id,
                RefreshToken.is_expired == False,
            )
            .first()
        )

        if not auth_token:
            raise HTTPException(
                status_code=401, detail=f"No matching refresh token found: {token}"
            )
        if is_refresh_token_expired(db, auth_token):
            raise HTTPException(status_code=401, detail="Token expired")

        return (user_id, student_id)
    except JWTError:
        try:
            # トークンの期限が切れてdecodeできない場合は，トークンを無効化する
            auth_token = (
                db.query(RefreshToken).filter(RefreshToken.token == token).first()
            )
            if not auth_token:
                raise HTTPException(
                    status_code=401, detail=f"No matching refresh token found: {token}"
                )
            if is_refresh_token_expired(db, auth_token):
                raise HTTPException(status_code=401, detail="Token expired")
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def update_token_expiration(db: Session, token: AccessToken) -> None:
    token.is_expired = True
    db.commit()


def create_access_token(
    data: dict, db: Session, expires_delta: Union[timedelta, None] = None
):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(tokyo_tz) + expires_delta
    else:
        expire = datetime.now(tokyo_tz) + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    auth_code = AccessToken(
        token=encoded_jwt,
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


def invalidate_access_token(db: Session, token: str):
    try:
        decoded_jwt = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = decoded_jwt.get("user_id")
        if user_id:
            auth_code = (
                db.query(AccessToken)
                .filter(AccessToken.user_id == user_id, AccessToken.token == token)
                .all()
            )
        for code in auth_code:
            code.is_expired = True
            db.commit()
            return True
    except JWTError:
        try:
            auth_code = db.query(AccessToken).filter(AccessToken.token == token).first()
            if not auth_code:
                return True
            auth_code.is_expired = True
            db.commit()
            return True
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return False


def invalidate_refresh_token(db: Session, token: str):
    try:
        decoded_jwt = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = decoded_jwt.get("user_id")
        if user_id:
            auth_code = (
                db.query(RefreshToken)
                .filter(RefreshToken.user_id == user_id, RefreshToken.token == token)
                .all()
            )
            for code in auth_code:
                code.is_expired = True
            db.commit()
            return True
    except JWTError:
        try:
            auth_code = (
                db.query(RefreshToken).filter(RefreshToken.token == token).first()
            )
            if not auth_code:
                return True
            auth_code.is_expired = True
            db.commit()
            return True
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return False
