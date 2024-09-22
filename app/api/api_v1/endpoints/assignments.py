from ....crud.db import assignments, utils, users
from ....crud.utils import send_heartbeat
from ....crud import file_operation
from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session
from ....dependencies import get_db
from ....classes import schemas
from ....classes import models
from typing import List, Optional
from datetime import datetime
from pytz import timezone
from fastapi import UploadFile, File, HTTPException, Security, status
from fastapi.responses import JSONResponse
from app.api.api_v1.endpoints import authenticate_util
from typing import Annotated
import os
import logging
import asyncio
import uuid
import json
import asyncio
from .... import constants as constant
from ....classes import submission_class

logging.basicConfig(level=logging.DEBUG)

router = APIRouter()

"""
/api/v1/assignments/...以下のエンドポイントの定義
"""


async def get_all_lectures(
    db: Session,
    current_user: Annotated[
        schemas.UserRecord, Security(authenticate_util.get_current_active_user)
    ],
) -> list[schemas.LectureRecord]:
    return assignments.get_lecture_list(db)


async def get_lecture_entry(
    db: Session,
    lecture_id: int,
    current_user: Annotated[
        schemas.UserRecord, Security(authenticate_util.get_current_active_user)
    ],
) -> schemas.LectureRecord:
    lecture = assignments.get_lecture(db, lecture_id)
    if lecture is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="授業エントリが見つかりません"
        )
    return lecture


async def get_all_problems(
    db: Session,
    lecture_id: int,
    current_user: Annotated[
        schemas.UserRecord, Security(authenticate_util.get_current_active_user)
    ],
) -> list[schemas.ProblemRecord]:
    return assignments.get_problem_list(db, lecture_id)


async def get_problem_entry(
    db: Session,
    lecture_id: int,
    assignment_id: int,
    for_evaluation: bool,
    current_user: Annotated[
        schemas.UserRecord, Security(authenticate_util.get_current_active_user)
    ],
) -> schemas.ProblemRecord:
    problem = assignments.get_problem_recursive(
        db, lecture_id, assignment_id, for_evaluation
    )
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="課題エントリが見つかりません"
        )
    return problem


# 授業エントリに紐づくデータ(授業エントリ、課題エントリ、評価項目、テストケース)が公開期間内かどうかを確認する
async def check_public_period(
    lecture_entry: Annotated[schemas.LectureRecord, Depends(get_lecture_entry)]
) -> bool:
    return authenticate_util.is_past(
        lecture_entry.start_date
    ) and authenticate_util.is_future(lecture_entry.end_date)


@router.get("/all", response_model=List[schemas.LectureRecord])
async def read_all_lectures(
    db: Annotated[Session, Depends(get_db)],
    lecture_list: Annotated[
        list[schemas.LectureRecord],
        Security(get_all_lectures, scopes=["view_all_problems"]),
    ],
) -> List[schemas.LectureRecord]:
    """
    全ての授業エントリを取得する
    """
    return lecture_list


@router.get("/all/{lecture_id}", response_model=List[schemas.ProblemRecord])
async def read_all_problems(
    problem_list: Annotated[
        list[schemas.ProblemRecord],
        Security(get_all_problems, scopes=["view_all_problems"]),
    ],
) -> List[schemas.ProblemRecord]:
    return problem_list


@router.get("/all/{lecture_id}/{problem_id}/{for_evaluation}")
async def read_problem_entry(
    problem: Annotated[
        schemas.ProblemRecord, Security(get_problem_entry, scopes=["view_all_problems"])
    ],
) -> schemas.ProblemRecord:
    return problem


@router.get("/", response_model=List[schemas.LectureRecord])
def read_lectures(
    lecture_list: Annotated[
        list[schemas.LectureRecord], Security(get_all_lectures, scopes=["me"])
    ],
) -> List[schemas.LectureRecord]:
    """
    公開期間内の授業エントリを取得する
    """
    # 公開期間内の授業エントリのみを返す
    public_lecture_list = [
        lecture
        for lecture in lecture_list
        if authenticate_util.is_past(lecture.start_date)
        and authenticate_util.is_future(lecture.end_date)
    ]
    return public_lecture_list


@router.get("/{lecture_id}", response_model=List[schemas.ProblemRecord])
def read_problems(
    lecture_entry: Annotated[schemas.LectureRecord, Depends(get_lecture_entry)],
    problem_list: Annotated[
        list[schemas.ProblemRecord], Security(get_all_problems, scopes=["me"])
    ],
) -> List[schemas.ProblemRecord]:
    """
    公開期間内の授業エントリに紐づく問題のリストを取得する
    """
    # Problemsに対応する授業エントリが公開期間内のみ、問題のリストを返す
    if authenticate_util.is_past(
        lecture_entry.start_date
    ) and authenticate_util.is_future(lecture_entry.end_date):
        return problem_list
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが公開期間内ではありません",
        )


@router.get(
    "/{lecture_id}/{problem_id}/{for_evaluation}", response_model=schemas.ProblemRecord
)
async def read_problem_entry(
    lecture_entry: Annotated[schemas.LectureRecord, Depends(get_lecture_entry)],
    problem: Annotated[
        schemas.ProblemRecord, Security(get_problem_entry, scopes=["me"])
    ],
) -> schemas.ProblemRecord:
    """
    公開期間内の授業エントリに紐づく問題のエントリを取得する
    """
    if authenticate_util.is_past(
        lecture_entry.start_date
    ) and authenticate_util.is_future(lecture_entry.end_date):
        return problem
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが公開期間内ではありません",
        )


@router.get("/{id}/{sub_id}", response_model=schemas.SubAssignmentDetail)
def read_sub_assignment(
    id: int,
    sub_id: int,
    db: Session = Depends(get_db),
    user: Optional[schemas.UserBase] = Depends(users.get_current_user),
):
    utils.validate_assignment(id, user.is_admin, db)
    sub_assignment: models.SubAssignment = assignments.get_sub_assignment(
        db, id=id, sub_id=sub_id
    )
    assignment_title = assignments.get_assignment(db, id).test_dir_name
    detail = schemas.SubAssignmentDetail(sub_assignment=sub_assignment)
    detail.set_test_program(assignment_title)
    detail.set_test_output(assignment_title)
    return detail


# 　ファイルをアップロードするためのAPI．進捗送受信の時に使用するfilenameを返す．
# uuid + filenameにしてるけど，uuidをディレクトリ名にしてその下に普通にfilenameを配置するのでも良いかも．
# その場合makefile等がそのまま使えるはず．uuid + filenameの場合はスペースでsplitして使う(?)
@router.post("/upload/{id}/{sub_id}")
async def upload_file(
    id: int,
    sub_id: int,
    upload_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    unique_id = str(uuid.uuid4())  # UUIDを文字列に変換
    sub_assignment = assignments.get_sub_assignment(db, id, sub_id)
    try:
        function_tests = assignments.get_function_tests_by_sub_id(
            db, sub_assignment.id, sub_assignment.sub_id
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Function test not found: {e}")
    try:
        # 一時的なアップロードディレクトリパスを生成
        try:
            temp_upload_path = os.path.join(constant.TEMP_UPLOAD_DIR, unique_id)
            file_operation.mkdir(temp_upload_path)
            # ファイルを一時ディレクトリに保存
            temp_file_path = os.path.join(temp_upload_path, upload_file.filename)
            file: schemas.File = schemas.File(
                file_path=temp_file_path, upload_file=upload_file
            )
        except Exception as e:
            logging.error(f"File save failed: {e}")
        try:
            submission = submission_class.FormatCheckClass(
                [sub_assignment], unique_id, [unique_id], file
            )
        except Exception as e:
            logging.error(f"Submission class failed: {e}")
        try:
            submission.build_docker_mount_directory(function_tests)
        except Exception as e:
            logging.error(f"Build docker mount directory failed: {e}")
        return {"unique_id": unique_id, "filename": file.filename, "result": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {e}")


# 進捗を送信するためのWebSocket API
@router.websocket("/ws/{id}/{sub_id}")
async def process_progress_ws(websocket: WebSocket, id: int, sub_id: int):
    await websocket.accept()

    # ハートビート送信のタスク開始
    asyncio.create_task(send_heartbeat(websocket))
    # filenameを受け取る．uuidがあるためどのファイルかを識別できる．
    data = await websocket.receive_text()
    data_dict = json.loads(data)
    filename = data_dict["filename"]
    unique_id = data_dict["unique_id"]
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
