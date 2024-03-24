from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import pymysql
import json
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # フロントエンドのオリジンを許可
    allow_credentials=True,
    allow_methods=["*"],  # すべてのHTTPメソッドを許可
    allow_headers=["*"],  # すべてのHTTPヘッダーを許可
)

# データベース接続設定
DB_SETTINGS = {
    "host": "db",  # Dockerコンテナ名またはホスト名
    "user": "dsa",
    "password": "dsa-jikken",
    "db": "dsa",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


@app.get("/sidebar")
async def fetch_assignments():
    connection = pymysql.connect(**DB_SETTINGS)
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM assignments"
            cursor.execute(sql)
            result = cursor.fetchall()
            json_content = json.dumps(result, ensure_ascii=False, cls=CustomJSONEncoder)
            return JSONResponse(content=json_content, media_type="application/json")
    finally:
        connection.close()


# ドロップダウンで表示する課題一覧を取得
@app.get("/assignments/{id}")
async def fetch_sub_assignment(id: int):
    connection = pymysql.connect(**DB_SETTINGS)
    try:
        with connection.cursor() as cursor:
            sql = f"SELECT id, sub_id, title FROM sub_assignments WHERE id = {id}"
            cursor.execute(sql)
            result = cursor.fetchall()
            json_content = json.dumps(result, ensure_ascii=False, cls=CustomJSONEncoder)
            print(id, result)
            return JSONResponse(content=json_content, media_type="application/json")
    finally:
        connection.close()


# ドロップダウンで選択された課題の詳細を取得
@app.get("/assignments/{id}/{sub_id}")
async def fetch_sub_assignment_detail(id: int, sub_id: int):
    connection = pymysql.connect(**DB_SETTINGS)
    try:
        with connection.cursor() as cursor:
            sql = f"SELECT * FROM sub_assignments WHERE id = {id} AND sub_id = {sub_id}"
            cursor.execute(sql)
            result = cursor.fetchone()
            json_content = json.dumps(result, ensure_ascii=False, cls=CustomJSONEncoder)
            return JSONResponse(content=json_content, media_type="application/json")
    finally:
        connection.close()
