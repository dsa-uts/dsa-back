import logging
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from .api.api_v1.endpoints import api_router
from .crud.db import init_db
from contextlib import asynccontextmanager
from .classes.models import AccessToken, RefreshToken
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from .dependencies import get_db
import os

# ロギング設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # アプリケーションの起動時に実行される処理
    init_db()
    # スケジューラの設定
    scheduler = BackgroundScheduler()

    def delete_expired_tokens():
        with get_db() as db:  # セッションを取得
            expiration_threshold = datetime.utcnow() - timedelta(hours=24)

            # 失効から24時間以上経過したアクセストークンを削除
            db.query(AccessToken).filter(
                AccessToken.expired_at < expiration_threshold,
                AccessToken.is_expired == True,
            ).delete(synchronize_session=False)

            # 失効から24時間以上経過したリフレッシュトークンを削除
            db.query(RefreshToken).filter(
                RefreshToken.expired_at < expiration_threshold,
                RefreshToken.is_expired == True,
            ).delete(synchronize_session=False)

            db.commit()
            logger.info("Expired tokens deleted")

    # 毎日1回実行するジョブをスケジュール
    scheduler.add_job(delete_expired_tokens, "interval", days=1)
    scheduler.start()

    yield
    # アプリケーションの終了時にスケジューラを停止
    scheduler.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan)

    # カスタムHTTPExceptionハンドラー
    @app.exception_handler(HTTPException)
    async def custom_http_exception_handler(request: Request, exc: HTTPException):
        logger.error(f"HTTPException: {exc.detail} - Path: {request.url.path}")
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    # 一般的な例外ハンドラー（オプション）
    @app.exception_handler(Exception)
    async def custom_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unexpected error: {str(exc)} - Path: {request.url.path}")
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred. Please try again later."},
        )

    # 一時ファイルを削除するミドルウェア
    @app.middleware("http")
    async def remove_temp_file(request: Request, call_next):
        response = await call_next(request)
        if isinstance(response, FileResponse):
            try:
                os.remove(response.path)
            except Exception as e:
                logger.error(f"Error deleting temporary file: {str(e)}")
        return response

    app.include_router(api_router, prefix="/api/v1")
    return app


# フロントエンドサーバ(オリジン: http://localhost:3000)からのアクセスを許可するための
# CORS設定
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
