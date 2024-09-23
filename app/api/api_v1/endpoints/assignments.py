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
import shutil
from pathlib import Path
import tempfile
import zipfile

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
async def lecture_is_public(
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


@router.get("/{lecture_id}/all", response_model=List[schemas.ProblemRecord])
async def read_all_problems(
    problem_list: Annotated[
        list[schemas.ProblemRecord],
        Security(get_all_problems, scopes=["view_all_problems"]),
    ],
) -> List[schemas.ProblemRecord]:
    return problem_list


@router.get("/{lecture_id}/{problem_id}/all", response_model=schemas.ProblemRecord)
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
    if lecture_is_public(lecture_entry):
        return problem_list
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが公開期間内ではありません",
        )


@router.get("/{lecture_id}/{problem_id}", response_model=schemas.ProblemRecord)
async def read_problem_entry(
    lecture_entry: Annotated[schemas.LectureRecord, Depends(get_lecture_entry)],
    problem: Annotated[
        schemas.ProblemRecord, Security(get_problem_entry, scopes=["me"])
    ],
) -> schemas.ProblemRecord:
    """
    公開期間内の授業エントリに紐づく問題のエントリを取得する
    """
    if lecture_is_public(lecture_entry):
        return problem
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが公開期間内ではありません",
        )


@router.post("/{lecture_id}/{assignment_id}/judge/single")
async def single_judge(
    file_list: list[UploadFile],
    user_id: str,  # 採点対象のユーザID(ログインユーザじゃないこともある)
    db: Annotated[Session, Depends(get_db)],
    # 注) manager以上がバッチ提出も単体提出も両方使えることを想定していため、スコープはbatchにしている。
    problem_entry: Annotated[
        schemas.ProblemRecord, Security(get_problem_entry, scopes=["batch"])
    ],
) -> schemas.SubmissionRecord:
    """
    単体の採点リクエストを受け付ける

    注) 採点用のエンドポイントで、学生が使うことを想定していない。
    """
    # ジャッジリクエストをSubmissionテーブルに登録する
    submission_record = assignments.register_submission(
        db=db,
        batch_id=None,
        user_id=user_id,
        lecture_id=problem_entry.lecture_id,
        assignment_id=problem_entry.assignment_id,
        for_evaluation=problem_entry.for_evaluation,
    )

    # アップロードされたファイルを/upload/{submission_id}に配置する
    # それと同時にUploadedFilesテーブルに登録する
    upload_dir = Path(constant.UPLOAD_DIR) / "single" / str(submission_record.id)
    if upload_dir.exists():
        shutil.rmtree(upload_dir)

    upload_dir.mkdir(parents=True, exist_ok=True)

    for file in file_list:
        with file.file as source_file:
            dest_path = upload_dir / file.filename
            with open(dest_path, "wb") as dest_file:
                shutil.copyfileobj(source_file, dest_file)
            assignments.register_uploaded_file(
                db=db, submission_id=submission_record.id, path=dest_path
            )

    # 提出エントリをキューに登録する
    submission_record.progress = schemas.SubmissionProgressStatus.QUEUED
    assignments.modify_submission(db=db, submission_record=submission_record)

    return submission_record


@router.post("/{lecture_id}/judge/batch")
async def batch_judge(
    zip_file: UploadFile,
    lecture_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> schemas.BatchSubmissionRecord:
    """
    バッチ採点リクエストを受け付ける

    注) 採点用のエンドポイントで、学生が使うことを想定していない。
    """

    # lecture_idに紐づいたProblemRecordのリストを取得する
    problem_list = assignments.get_problem_list(db, lecture_id)
    
    # for_evaluationがTrueのProblemRecordのリストを抽出する
    problem_list = [problem for problem in problem_list if problem.for_evaluation]

    # 各Problemエントリに対応する、要求されているファイルのリストを取得する
    required_files_for_problem: list[list[str]] = []
    for problem in problem_list:
        required_files_for_problem.append(
            assignments.get_required_files(
                db=db,
                lecture_id=problem.lecture_id,
                assignment_id=problem.assignment_id,
                for_evaluation=problem.for_evaluation,
            )
        )

    # バッチ採点のリクエストをBatchSubmissionテーブルに登録する
    batch_submission_record = assignments.register_batch_submission(
        db=db,
        user_id=current_user.user_id,
    )

    batch_id = batch_submission_record.id

    # アップロードされたzipファイルをテンポラリディレクトリに解凍する。
    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(zip_file.file, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        # 展開先のディレクトリで、フォルダが一個しかない場合、Zipファイルのbase名でネストされて
        # いる可能性がある。その場合、もう一つネストした先にフォーカスする
        current_dir = Path(temp_dir)
        if len(list(current_dir.iterdir())) == 1:
            nested_dir = current_dir / list(current_dir.iterdir())[0]
            if nested_dir.is_dir():
                current_dir = nested_dir

        # current_dirには、"202211479@001202214795"といったような
        # "学籍番号@UTID13"のフォルダが並んでいて、その下に提出されたソースコードやレポートが
        # 入っている

        # ユーザごとに各課題のジャッジリクエストを発行する
        for user_dir in current_dir.iterdir():
            if not user_dir.is_dir():
                continue

            # 学籍番号を取得する
            user_id = user_dir.name.split("@")[0]
            
            # ファイルのリストを取得
            file_list = [file_path for file_path in user_dir.iterdir() if file_path.is_file()]
            
            # 各課題のジャッジリクエストを作成する
            for problem, required_file_list in zip(problem_list, required_files_for_problem):
                
                # ジャッジリクエストをSubmissionテーブルに登録する
                submission_record = assignments.register_submission(
                    db=db,
                    batch_id=batch_id,
                    user_id=user_id,
                    lecture_id=problem.lecture_id,
                    assignment_id=problem.assignment_id,
                    for_evaluation=problem.for_evaluation,
                )
                
                # アップロード先
                upload_dir = Path(constant.UPLOAD_DIR) / "single" / str(submission_record.id)
                if upload_dir.exists():
                    shutil.rmtree(upload_dir)

                upload_dir.mkdir(parents=True, exist_ok=True)

                for file in file_list:
                    if file.name not in required_file_list:
                        continue
                    
                    with file.file as source_file:
                        dest_path = upload_dir / file.name
                        with open(dest_path, "wb") as dest_file:
                            shutil.copyfileobj(source_file, dest_file)
                        assignments.register_uploaded_file( 
                           db=db, submission_id=submission_record.id, path=dest_path
                        )
                
                # 提出エントリをキューに登録する
                submission_record.progress = schemas.SubmissionProgressStatus.QUEUED
                assignments.modify_submission(db=db, submission_record=submission_record)
            
            # PDFファイルを探す
            report_path: Path | None = None
            for file in file_list:
                if file.name.endswith(".pdf"):
                    # "UPLOAD_DIR/report/{user_id}/{lecture_id}/"にアップロード
                    report_path = upload_dir / "report" / user_id / str(problem.lecture_id) / file.name
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(file, report_path)
                    break
            
            # EvaluationResultレコードを登録する
            assignments.register_evaluation_result(
                db=db,
                evaluation_result_record=schemas.EvaluationResultRecord(
                    user_id=user_id,
                    lecture_id=problem.lecture_id,
                    score=None,
                    report_path=str(report_path) if report_path is not None else None,
                    comment=None,
                )
            )
                
    return batch_submission_record


# TODO: 提出の進捗状況を送信するAPIも作る
# @router.get("/{submission_id}/status")
# async def read_submission_status(
#     submission_id: int,
#     db: Annotated[Session, Depends(get_db)],
#     current_user
# ) -> schemas.SubmissionRecord:
#     """
#     提出の進捗状況を取得する
#     """
#     return assignments.get_submission(db, submission_id)


