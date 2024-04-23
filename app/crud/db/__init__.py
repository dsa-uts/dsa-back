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
from app import constants

DATABASE_URL = f"mysql+pymysql://{constants.DATABASE_USER}:{constants.DATABASE_PASSWORD}@{constants.DATABASE_HOST}/{constants.DATABASE_NAME}"

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
                username=constants.ADMIN_USER,
                password=constants.ADMIN_PASSWORD,
                is_admin=True,
                disabled=False,
                created_at=datetime.now(),
                active_start_date=datetime.fromisoformat(constants.ADMIN_START_DATE),
                active_end_date=datetime.fromisoformat(constants.ADMIN_END_DATE),
            ),
        )
    except Exception as e:
        logging.error(f"Error initializing database: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    init_db()
