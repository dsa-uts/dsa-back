from fastapi import APIRouter
from . import assignments
from . import authorize
from . import users

api_router = APIRouter()
api_router.include_router(
    assignments.router, prefix="/assignments", tags=["assignments"]
)

api_router.include_router(authorize.router, prefix="/authorize", tags=["authorize"])

api_router.include_router(users.router, prefix="/users", tags=["users"])
