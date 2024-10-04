from .crud.db.__init__ import SessionLocal
import tempfile
from pathlib import Path
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_temporary_directory():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)
