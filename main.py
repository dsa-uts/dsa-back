from fastapi import FastAPI
import pymysql
import json

app = FastAPI()

# データベース接続設定
DB_SETTINGS = {
    "host": "db",  # Dockerコンテナ名またはホスト名
    "user": "dsa",
    "password": "dsa-jikken",
    "db": "dsa",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}


@app.get("/assignments")
async def fetch_assignments():
    connection = pymysql.connect(**DB_SETTINGS)
    try:
        with connection.cursor() as cursor:
            sql = "SELECT * FROM assignments"  # assignmentsはあなたのテーブル名に置き換えてください
            cursor.execute(sql)
            result = cursor.fetchall()
            return json.dumps(
                result, ensure_ascii=False, default=str
            )  # 日付などの特殊な型を文字列に変換
    finally:
        connection.close()
