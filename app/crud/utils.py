import asyncio
import json
from fastapi import WebSocket
import string
import secrets


# websocketを使ってハートビートを送信する
# ハートビートはクライアントが接続しているかどうかを確認するために使われる
async def send_heartbeat(websocket: WebSocket):
    while True:
        try:
            await websocket.send_json({"type": "heartbeat", "message": "ping"})
            await asyncio.sleep(10)  # 10秒ごとにハートビートを送信
        except Exception as e:
            print(f"Error sending heartbeat: {e}")
            break  # エラーが発生した場合はループを抜ける


def generate_password(length=10):
    characters = string.ascii_letters + string.digits + string.punctuation
    return "".join(secrets.choice(characters) for _ in range(length))
