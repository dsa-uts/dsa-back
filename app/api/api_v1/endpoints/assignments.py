from ....crud.db import assignments, utils, users
from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session
from ....dependencies import get_db
from .... import schemas
from typing import List, Optional
from datetime import datetime
from pytz import timezone
from fastapi import UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import os
import logging
import asyncio
import uuid
import shutil
import json

logging.basicConfig(level=logging.INFO)

router = APIRouter()


@router.get("/", response_model=List[schemas.AssignmentBase])
def read_assignments(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: Optional[schemas.UserBase] = Depends(users.get_current_user),
) -> List[schemas.AssignmentBase]:
    assignments_list = assignments.get_assignments(db, skip=skip, limit=limit)
    if user is None or user.disabled:
        current_time = datetime.now(timezone("Asia/Tokyo"))
        assignments_list = utils.filter_assignments_by_time(
            assignments_list, current_time
        )
    return assignments_list


@router.get("/{id}", response_model=List[schemas.SubAssignmentBase])
def read_sub_assignments(
    id: int,
    db: Session = Depends(get_db),
    user: Optional[schemas.UserBase] = Depends(users.get_current_user),
):
    if user is None or user.disabled:
        utils.validate_assignment(id, False, db)
    else:
        utils.validate_assignment(id, True, db)
    sub_assignments_list = assignments.get_sub_assignments(db, id=id)
    return sub_assignments_list


@router.get("/{id}/{sub_id}", response_model=schemas.SubAssignmentDetail)
def read_sub_assignment(
    id: int,
    sub_id: int,
    db: Session = Depends(get_db),
    user: Optional[schemas.UserBase] = Depends(users.get_current_user),
):
    if user is None or user.disabled:
        utils.validate_assignment(id, False, db)
    else:
        utils.validate_assignment(id, True, db)
    sub_assignment = assignments.get_sub_assignment(db, id=id, sub_id=sub_id)
    detail = schemas.SubAssignmentDetail(
        id=sub_assignment.id,
        sub_id=sub_assignment.sub_id,
        title=sub_assignment.title,
        makefile=sub_assignment.makefile,
        required_file_name=sub_assignment.required_file_name,
        test_file_name=sub_assignment.test_file_name,
        test_input=sub_assignment.test_input_dir,
    )
    if utils.check_path_exists(sub_assignment.test_output_dir):
        combined_path = os.path.join(
            sub_assignment.test_output_dir, sub_assignment.test_case_name
        )
        detail.test_output = utils.read_text_file(combined_path)
    if utils.check_path_exists(sub_assignment.test_program_dir):
        combined_path = os.path.join(
            sub_assignment.test_program_dir, sub_assignment.test_program_name
        )
        detail.test_program = utils.read_text_file(combined_path)
    return detail


# 　ファイルをアップロードするためのAPI．進捗送受信の時に使用するfilenameを返す．
# uuid + filenameにしてるけど，uuidをディレクトリ名にしてその下に普通にfilenameを配置するのでも良いかも．
# その場合makefile等がそのまま使えるはず．uuid + filenameの場合はスペースでsplitして使う(?)
@router.post("/upload/{id}/{sub_id}")
async def upload_file(id: int, sub_id: int, file: UploadFile = File(...)):
    upload_dir = "uploadedFiles"
    unique_filename = f"{uuid.uuid4()}_{file.filename}"
    file_path = os.path.join(upload_dir, unique_filename)
    try:
        os.makedirs(upload_dir, exist_ok=True)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"filename": unique_filename, "result": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {e}")


# 進捗を送信するためのWebSocket API
@router.websocket("/ws/{id}/{sub_id}")
async def process_progress_ws(websocket: WebSocket, id: int, sub_id: int):
    await websocket.accept()

    # filenameを受け取る．uuidがあるためどのファイルかを識別できる．
    data = await websocket.receive_text()
    data_dict = json.loads(data)
    filename = data_dict["filename"]
    # 本来はdockerから進捗を受け取る処理を記述
    # コンパイルすべきファイルが複数ある場合や，実行するファイルが複数ある場合は，(1/n)のように返しても良いかも．
    # 例えば，「コンパイル中(1/3)」
    # statusも"building docker", "compiling", "running", "judging"のように細かく分けても良いかも．
    steps = ["docker起動中", "コンパイル中", "実行中", "判定中"]
    try:
        for i, step in enumerate(steps):
            # エラーにしてみる
            # if i == 2:
            #     raise Exception("エラーが発生しました")
            progress_percentage = round((i + 1) / (len(steps) + 1) * 100)
            progress_message = schemas.ProgressMessage(
                status="progress",
                message=step,
                progress_percentage=progress_percentage,
            )
            logging.info(f"Sending progress: {progress_message}")
            await websocket.send_json(progress_message.dict())
            # 仮の処理として2秒待機
            await asyncio.sleep(2)
        # すべてのステップが完了したら成功メッセージを送信
        success_message = schemas.ProgressMessage(
            status="done",
            message="処理が完了しました",
            progress_percentage=100,
            result={
                "function1": "AC",
                "function2": "WA",  # WAとかじゃなくエラーメッセージとかを詳細にまとめたdictにしたい．
                "function3": "TLE",
            },  # 仮の結果．
        )
        await websocket.send_json(success_message.dict())
    except Exception as e:
        error_message = schemas.ProgressMessage(
            status="error",
            message="エラーが発生しました．アップロードをやり直してください．",
            progress_percentage=-1,
        )
        logging.error(f"Error occurred: {error_message}")
        await websocket.send_json(error_message.dict())
    finally:
        await websocket.close()
