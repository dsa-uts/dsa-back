import logging
from fastapi import FastAPI
from .api.api_v1.endpoints import api_router
from fastapi.middleware.cors import CORSMiddleware
from .crud.db import init_db
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # アプリケーションの起動時に実行される処理
    init_db()
    yield
    # アプリケーションの終了時に実行される処理（ここでは特に何もしない）


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)

    app.include_router(api_router, prefix="/api/v1")
    return app


origins = [
    "http://localhost:3000",
]

app = create_app()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
