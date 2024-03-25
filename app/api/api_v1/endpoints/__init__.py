from fastapi import APIRouter
from . import assignments

api_router = APIRouter()
api_router.include_router(
    assignments.router, prefix="/assignments", tags=["assignments"]
)
