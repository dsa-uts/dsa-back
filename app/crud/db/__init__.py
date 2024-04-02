import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base
from app.schemas import UserCreate
from app.crud.db.authorize import get_password_hash
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ...models import Base
import os

DATABASE_USER = os.getenv("DATABASE_USER")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD")
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_NAME = os.getenv("DATABASE_NAME")

ADMIN_USER = os.getenv("INIT_ADMIN_USER")
ADMIN_PASSWORD = os.getenv("INIT_ADMIN_PASSWORD")
ADMIN_START_DATE = os.getenv("INIT_ADMIN_START_DATE")
ADMIN_END_DATE = os.getenv("INIT_ADMIN_END_DATE")

DATABASE_URL = f"mysql+pymysql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}/{DATABASE_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)
logging.basicConfig(level=logging.INFO)


def init_db():
    db = SessionLocal()
    try:
        from .users import create_user

        create_user(
            db=db,
            user=UserCreate(
                username=ADMIN_USER,
                password=ADMIN_PASSWORD,
                is_admin=True,
                disabled=False,
                created_at=datetime.now(),
                active_start_date=datetime.fromisoformat(ADMIN_START_DATE),
                active_end_date=datetime.fromisoformat(ADMIN_END_DATE),
            ),
        )
    except Exception as e:
        logging.error(f"Error initializing database: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
