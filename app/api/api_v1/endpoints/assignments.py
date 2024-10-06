from ....crud.db import assignments, users
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ....dependencies import get_db
from ....classes import schemas
from typing import List, Optional, Dict, Literal
from datetime import datetime
from pytz import timezone
from fastapi import UploadFile, File, HTTPException, Security, status
from fastapi.responses import FileResponse
from app.api.api_v1.endpoints import authenticate_util
from typing import Annotated
import logging
from app import constants as constant
import shutil
from pathlib import Path
import tempfile
import zipfile
import re
from app.api.api_v1.endpoints import assignments_util
from pydantic import BaseModel
import pandas as pd
from starlette.background import BackgroundTask

logging.basicConfig(level=logging.DEBUG)

router = APIRouter()

"""
/api/v1/assignments/...以下のエンドポイントの定義
"""


# 授業エントリに紐づくデータ(授業エントリ、課題エントリ、評価項目、テストケース)が公開期間内かどうかを確認する
def lecture_is_public(lecture_entry: schemas.LectureRecord) -> bool:
    return authenticate_util.is_past(
        lecture_entry.start_date
    ) and authenticate_util.is_future(lecture_entry.end_date)


def access_sanitize(
    open: bool | None = None,  # 公開期間内かどうか
    evaluation: bool | None = None,  # 評価問題かどうか
    role: schemas.Role | None = None,  # ユーザのロール
) -> None:
    """
    アクセス権限のチェックを行う
    """
    if role not in [schemas.Role.manager, schemas.Role.admin]:
        # ユーザがManager, Adminでない場合は、公開期間外の情報を取得することはできない
        if open is not None and open is False:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="公開期間外の情報を取得する権限がありません",
            )
        # ユーザがManager, Adminでない場合は、評価問題の情報を取得することはできない
        if evaluation is not None and evaluation is True:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="評価問題を取得する権限がありません",
            )


def delete_temp_dir(temp_dir: tempfile.TemporaryDirectory):
    temp_dir.cleanup()


def get_zip_file_size(path: Path) -> int:
    """
    zipファイルの容量をMB単位で返す
    """
    with zipfile.ZipFile(path, "r") as zip_ref:
        return sum([zinfo.file_size for zinfo in zip_ref.filelist]) / 1024 / 1024 # MB


def unfold_zip(uploaded_zip_file: Path, dest_dir: Path) -> str | None:
    """
    uploaded_zip_fileが以下の条件を満たすかチェックしながら、dest_dirにファイルを配置していく。
    * 拡張子がzipであること
    * 展開前のファイル名が"class{lecture_id}.zip"であること
    * 展開した後、以下のパターンしか想定しない
        * フォルダが1個しか存在しないパターン
        * zipファイルは存在せず、かつフォルダが存在しないパターン
        
    何も問題が無ければNoneを返し、問題があればエラーメッセージを返す。
    """
    # zip提出の場合
    if not uploaded_zip_file.name.endswith(".zip"):
        return "zipファイルを提出してください。",

    # zipファイルの容量が30MBを超える場合はエラー
    if get_zip_file_size(uploaded_zip_file) > 30:
        return "zipファイルの展開後の容量が30MBを超えています。"

    # 展開する
    with zipfile.ZipFile(uploaded_zip_file, "r") as zip_ref:
        zip_ref.extractall(dest_dir)
    
    # 空の場合
    if len(list(dest_dir.iterdir())) == 0:
        return "提出ファイルが空です。"
    
    # dest_dir下に1つのフォルダのみがある場合、そのフォルダの中身をdest_dirに移動する
    # (ex "temp_dir/dir"のみ)
    if len(list(dest_dir.iterdir())) == 1 and list(dest_dir.iterdir())[0].is_dir():
        folded_dir = list(dest_dir.iterdir())[0]
        try:
            for file in folded_dir.iterdir():
                shutil.move(file, dest_dir)
        except Exception as e:
            return f"zipファイル名と同じ名前のフォルダがあるため、展開時にエラーが発生しました。"
        
        # folded_dirを削除する
        if len(list(folded_dir.iterdir())) > 0:
            return "フォルダの展開に失敗しました。"
        shutil.rmtree(folded_dir)
    
    # それでもtemp_dir内にフォルダがある場合、またはzipファイルが存在する場合はエラー
    folder_num = len([f for f in dest_dir.iterdir() if f.is_dir()])
    if folder_num > 1:
        return "圧縮後のディレクトリが3階層以上あります。"
    
    zip_num = len([f for f in dest_dir.iterdir() if f.is_file() and f.suffix == ".zip"])
    if zip_num > 0:
        return "zipの中にzipを含めないでください。"

    return None


@router.get("/info", response_model=List[schemas.LectureRecord])
async def read_lectures(
    open: Annotated[bool, Query(description="公開期間内の授業エントリを取得する場合はTrue、そうでない場合はFalse")],  # 公開期間内かどうか
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[schemas.LectureRecord]:
    """
    授業エントリを取得する
    """
    ############################### Vital #####################################
    access_sanitize(open=open, role=current_user.role)
    ############################### Vital #####################################

    lecture_list = assignments.get_lecture_list(db)
    if open is True:
        return [lecture for lecture in lecture_list if lecture_is_public(lecture)]
    else:
        return [lecture for lecture in lecture_list if not lecture_is_public(lecture)]


@router.get("/info/{lecture_id}", response_model=List[schemas.ProblemRecord])
async def read_problems(
    lecture_id: int,
    evaluation: bool,  # 評価問題かどうか
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[schemas.ProblemRecord]:
    """
    授業エントリに紐づく練習問題のリストを取得する
    """
    ############################### Vital #####################################
    access_sanitize(evaluation=evaluation, role=current_user.role)
    ############################### Vital #####################################
    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )
    
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        if not lecture_is_public(lecture_entry):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="授業エントリが公開期間内ではありません",
            )

    problem_list = assignments.get_problem_list(
        db, lecture_id, for_evaluation=evaluation
    )
    return problem_list


@router.get("/info/{lecture_id}/{assignment_id}", response_model=schemas.ProblemRecord)
async def read_problem(
    lecture_id: int,
    assignment_id: int,
    evaluation: bool,  # 評価問題かどうか
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.ProblemRecord:
    """
    授業エントリに紐づく練習問題のエントリを取得する
    """
    ############################### Vital #####################################
    access_sanitize(evaluation=evaluation, role=current_user.role)
    ############################### Vital #####################################

    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )
    
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        if not lecture_is_public(lecture_entry):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="授業エントリが公開期間内ではありません",
            )

    problem_entry = assignments.get_problem(
        db=db,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=evaluation,
    )
    if problem_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="課題エントリが見つかりません",
        )
    return problem_entry


@router.get("/info/{lecture_id}/{assignment_id}/detail", response_model=schemas.ProblemRecord)
async def read_problem_detail(
    lecture_id: int,
    assignment_id: int,
    evaluation: bool,  # 評価問題かどうか
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.ProblemRecord:
    """
    授業エントリに紐づく練習問題のエントリの詳細(評価項目、テストケース)を取得する
    """
    ############################### Vital #####################################
    access_sanitize(evaluation=evaluation, role=current_user.role)
    ############################### Vital #####################################

    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )
    
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        if not lecture_is_public(lecture_entry):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="授業エントリが公開期間内ではありません",
            )

    problem_entry = assignments.get_problem_recursive(
        db=db,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=evaluation,
    )
    if problem_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="課題エントリが見つかりません",
        )
    return problem_entry


@router.get(
    "/info/{lecture_id}/{assignment_id}/description",
    response_model=schemas.TextDataResponse,
)
async def read_problem_description(
    lecture_id: int,
    assignment_id: int,
    evaluation: bool,  # 評価問題かどうか
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.TextDataResponse:
    """
    授業エントリに紐づく練習問題の説明を取得する
    """
    ############################### Vital #####################################
    access_sanitize(evaluation=evaluation, role=current_user.role)
    ############################### Vital #####################################
    
    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )
    
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        if not lecture_is_public(lecture_entry):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="授業エントリが公開期間内ではありません",
            )
    
    problem_entry = assignments.get_problem(
        db=db,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=evaluation,
    )
    if problem_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="課題エントリが見つかりません",
        )

    # problem_entry.description_pathのファイルの内容を読み込む
    description_path = Path(constant.RESOURCE_DIR) / problem_entry.description_path
    if not description_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="説明ファイルが見つかりません",
        )
    with open(description_path, "r") as f:
        description = f.read()
    return schemas.TextDataResponse(text=description)


@router.get("/info/{lecture_id}/{assignment_id}/required-files")
async def read_required_files(
    lecture_id: int,
    assignment_id: int,
    evaluation: bool,  # 評価問題かどうか
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[str]:
    """
    授業エントリに紐づく練習問題のリストを取得する
    """
    ############################### Vital #####################################
    access_sanitize(evaluation=evaluation, role=current_user.role)
    ############################### Vital #####################################

    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )
    
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        if not lecture_is_public(lecture_entry):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="授業エントリが公開期間内ではありません",
            )
        
        if evaluation is True:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="評価問題の必要ファイルは取得できません",
            )
    
    # 必要なファイルのリストを取得する
    required_files = assignments.get_required_files(
        db=db,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=evaluation,
    )
    return required_files


@router.post("/judge/{lecture_id}/{assignment_id}")
async def single_judge(
    file_list: list[UploadFile],
    lecture_id: int,
    assignment_id: int,
    evaluation: bool,  # 評価問題かどうか
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.SubmissionRecord:
    """
    単体の採点リクエストを受け付ける
    """
    ############################### Vital #####################################
    access_sanitize(evaluation=evaluation, role=current_user.role)
    ############################### Vital #####################################

    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )
        
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        if not lecture_is_public(lecture_entry):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="授業エントリが公開期間内ではありません",
            )

    # 課題エントリ(lecture_id, assignment_id, for_evaluation=False)を取得する
    problem_entry = assignments.get_problem_recursive(
        db=db,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=evaluation,
    )
    if problem_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="課題エントリが見つかりません",
        )

    # ジャッジリクエストをSubmissionテーブルに登録する
    submission_record = assignments.register_submission(
        db=db,
        batch_id=None,
        user_id=current_user.user_id,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=evaluation,
    )

    # アップロードされたファイルを/upload/{submission_record.ts}-{current_user.user_id}-{submission_id}に配置する
    upload_dir = Path(constant.UPLOAD_DIR) / f"{submission_record.ts.strftime('%Y-%m-%d-%H-%M-%S')}-{current_user.user_id}-{submission_record.id}"
    if upload_dir.exists():
        shutil.rmtree(upload_dir)

    upload_dir.mkdir(parents=True, exist_ok=True)

    for file in file_list:
        with file.file as source_file:
            dest_path = upload_dir / file.filename
            with open(dest_path, "wb") as dest_file:
                shutil.copyfileobj(source_file, dest_file)
            # アップロードされたファイルをUploadedFilesテーブルに登録する
            assignments.register_uploaded_file(
                db=db, submission_id=submission_record.id, path=dest_path.relative_to(Path(constant.UPLOAD_DIR))
            )

    # 提出エントリをキューに登録する
    submission_record.progress = schemas.SubmissionProgressStatus.QUEUED
    assignments.modify_submission(db=db, submission_record=submission_record)

    return submission_record


@router.post("/judge/{lecture_id}")
async def judge_all_by_lecture(
    uploaded_zip_file: UploadFile,
    lecture_id: int,
    evaluation: bool,  # 評価問題かどうか
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[schemas.SubmissionRecord]:
    """
    授業エントリに紐づく全ての練習問題を採点する
    
    学生がmanabaに提出する最終成果物が、ちゃんと自動採点されることを確認するために用意している。
    """
    ############################### Vital #####################################
    access_sanitize(evaluation=evaluation, role=current_user.role)
    ############################### Vital #####################################
    
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理者のみがこのエンドポイントを利用できます",
        )
    
    # 授業エントリを取得する
    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )

    # 授業エントリに紐づく全ての練習問題を採点する
    problem_list = assignments.get_problem_list(
        db, lecture_id, for_evaluation=evaluation
    )
    
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
    
    if uploaded_zip_file.filename != f"class{lecture_id}.zip":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="zipファイル名が不正です",
        )
        
    # zipファイルの内容を{UPLOAD_DIR}/format-check/{user_id}/{lecture_id}/{current_timestamp}に配置する
    upload_dir = Path(constant.UPLOAD_DIR) / "format-check" / current_user.user_id / str(lecture_id) / datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    if upload_dir.exists():
        shutil.rmtree(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # アップロードされたzipファイルをtemp_dir下にコピーする
        temp_uploaded_zip_file_path = Path(temp_dir) / uploaded_zip_file.filename
        with open(temp_uploaded_zip_file_path, "wb") as temp_uploaded_zip_file:
            shutil.copyfileobj(uploaded_zip_file.file, temp_uploaded_zip_file)
        # アップロードされたzipファイルをtemp_dirに解凍する
        unzip_result = unfold_zip(temp_uploaded_zip_file_path, upload_dir)
        if unzip_result is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=unzip_result,
        )
    
    workspace_dir = upload_dir
    
    '''
    この時点でのworkspace_dirの構成
    .
    ├── report{lecture_id}.pdf
    ├── Makefile
    ├── main.c
    ...
    '''
    
    # report{lecture_id}.pdfが存在するかチェックする
    if not (workspace_dir / f"report{lecture_id}.pdf").exists():
        # 一番最初の問題について、Submissionエントリ/SubmissionSummaryエントリを作成し、
        # 何もジャッジされていないことを表す
        problem = problem_list[0]
        submission_record = assignments.register_submission(
            db=db,
            batch_id=None,
            user_id=current_user.user_id,
            lecture_id=problem.lecture_id,
            assignment_id=problem.assignment_id,
            for_evaluation=problem.for_evaluation,
        )
        
        submission_record.progress = schemas.SubmissionProgressStatus.DONE
        assignments.modify_submission(db=db, submission_record=submission_record)
        # SubmissionSummaryエントリを作成する
        submission_summary_record = schemas.SubmissionSummaryRecord(
            submission_id=submission_record.id,
            batch_id=None,
            user_id=current_user.user_id,
            lecture_id=problem.lecture_id,
            assignment_id=problem.assignment_id,
            for_evaluation=problem.for_evaluation,
            result=schemas.SubmissionSummaryStatus.FN,
            message="フォーマットチェック: ZIPファイルにレポートが含まれていません",
            detail=f"report{lecture_id}.pdf",
            score=0,
            timeMS=0,
            memoryKB=0,
        )
        assignments.register_submission_summary(db=db, submission_summary_record=submission_summary_record)
        return [submission_record]

    submission_record_list = []
    
    # 各Problemエントリごとに、Submissionエントリを作成する
    for problem, required_file_list in zip(problem_list, required_files_for_problem):
        # ジャッジリクエストをSubmissionテーブルに登録する
        submission_record = assignments.register_submission(
            db=db,
            batch_id=None,
            user_id=current_user.user_id,
            lecture_id=problem.lecture_id,
            assignment_id=problem.assignment_id,
            for_evaluation=problem.for_evaluation,
        )

        # workspace_dirの中に、required_file_listに含まれるファイルがあるかチェックする
        for required_file in required_file_list:
            required_file_path = workspace_dir / required_file
            if not required_file_path.exists():
                continue
            
            # ファイルをUploadedFilesテーブルに登録する
            assignments.register_uploaded_file(
                db=db, submission_id=submission_record.id, path=required_file_path.relative_to(Path(constant.UPLOAD_DIR))
            )
            
        # report{lecture_id}.pdfもUploadedFilesテーブルに登録する
        report_path = workspace_dir / f"report{lecture_id}.pdf"
        if report_path.exists():
            assignments.register_uploaded_file(
                db=db, submission_id=submission_record.id, path=report_path.relative_to(Path(constant.UPLOAD_DIR))
            )

        # 提出エントリをキューに登録する
        submission_record.progress = schemas.SubmissionProgressStatus.QUEUED
        assignments.modify_submission(db=db, submission_record=submission_record)
        submission_record_list.append(submission_record)

    return submission_record_list


@router.post("/batch/{lecture_id}")
async def batch_judge(
    uploaded_zip_file: UploadFile,
    lecture_id: int,
    evaluation: bool,  # 評価問題かどうか
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
    ############################### Vital #####################################
    access_sanitize(evaluation=evaluation, role=current_user.role)
    ############################### Vital #####################################

    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )

    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        if not lecture_is_public(lecture_entry):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="授業エントリが公開期間内ではありません",
            )

    # lecture_idに紐づいたProblemRecordのリストを取得する
    problem_list = assignments.get_problem_list(
        db, lecture_id, for_evaluation=evaluation
    )

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
        lecture_id=lecture_id
    )

    batch_id = batch_submission_record.id
    total_judge = 0 # 採点対象の学生の数 (未提出でない学生の数)
    
    workspace_dir = tempfile.TemporaryDirectory()
    workspace_dir_path = Path(workspace_dir.name)

    # アップロードされたzipファイルをworkspace_dirに展開する
    with zipfile.ZipFile(uploaded_zip_file.file, "r") as zip_ref:
        zip_ref.extractall(workspace_dir_path)

    # 展開先のディレクトリで、フォルダが一個しかない
    current_dir = workspace_dir_path
    if len(list(current_dir.iterdir())) == 1 and list(current_dir.iterdir())[0].is_dir():
        current_dir = list(current_dir.iterdir())[0]

    '''
    この時点でのcurrent_dirの構成
    .
    ├── 202211479@001202214795
    │   └── class{lecture_id}.zip 
    ├── 202211479@001202214795
    │   └── class{lecture_id}.zip 
    ├── 202211479@001202214795
    │   └── class{lecture_id}.zip 
    ├── 202211479@001202214795
    │   └── class{lecture_id}.zip
    ...
    └── reportlist.xlsx
    ''' 

    # reportlist.xlsxを読み込み、未提出も含めて、採点対象の学生のリストを取得する
    # 取得する情報、学籍番号、提出状況(提出済/受付終了後提出/未提出)、提出日時(None | datetime)
    report_list_df = assignments_util.get_report_list(current_dir / "reportlist.xlsx")

    if report_list_df is None:
        # reportlist.xlsxが存在しない場合は、reportlist.xlsを試す
        report_list_df = assignments_util.get_report_list(current_dir / "reportlist.xls")

    if report_list_df is None:
        # reportlist.xlsxもreportlist.xlsも存在しない場合は、エラーを返す
        workspace_dir.cleanup()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reportlist.xlsxまたはreportlist.xlsが存在しません",
        )
        
    # "# ロール"の値が"履修生"である行のみ残す
    report_list_df = report_list_df[report_list_df["# ロール"] == "履修生"]

    # ユーザの学籍番号をキーとして、そのユーザの提出状況を格納する
    # 未提出のユーザはNoneとする。
    batch_submission_summary_list: list[schemas.BatchSubmissionSummaryRecord] = []

    error_message = ""

    # report_list_dfの"# 学籍番号"の値(9桁の学籍番号)と"# 提出"の値(提出済/受付終了後提出/未提出)を参照し、
    # "未提出"でないなら、{9桁の学籍番号}@{13桁のID}のフォルダを探す。
    # そのフォルダが存在するなら、user_id_to_batch_submission_summaryにそのユーザの提出状況を格納する。
    # そのフォルダが存在しないなら、error_messageにエラーメッセージを追加する。
    for index, row in report_list_df.iterrows():
        user_id = str(row["# 学籍番号"]) if not pd.isna(row["# 学籍番号"]) else None
        submission_status = str(row["# 提出"]) if not pd.isna(row["# 提出"]) else None
        submit_date = datetime.strptime(str(row["# 提出日時"]), "%Y-%m-%d %H:%M:%S") if not pd.isna(row["# 提出日時"]) else None
        # logging.info(f"user_id: {user_id}, submission_status: {submission_status}, submit_date: {submit_date}")

        if user_id is None:
            error_message += f"{index}行目の学籍番号が空です\n"
            continue
        
        if users.get_user(db, user_id) is None:
            error_message += f"{index}行目のユーザがDBに登録されていません: {user_id}\n"
            continue

        if (submission_status == "提出済" or submission_status == "受付終了後提出") and submit_date is None:
            error_message += f"{index}行目の提出日時が提出済みであるにも関わらず空です。遅延判定ができません\n"
            continue

        batch_submission_summary_record = schemas.BatchSubmissionSummaryRecord(
            batch_id=batch_id,
            user_id=user_id,
            status=(
                schemas.StudentSubmissionStatus.SUBMITTED
                if submission_status == "提出済"
                else (
                    schemas.StudentSubmissionStatus.DELAY
                    if submission_status == "受付終了後提出"
                    else schemas.StudentSubmissionStatus.NON_SUBMITTED
                )
            ),
        )
        
        if batch_submission_summary_record.status == schemas.StudentSubmissionStatus.NON_SUBMITTED:
            batch_submission_summary_list.append(batch_submission_summary_record)
            continue

        user_dir_pattern = re.compile(f"{user_id}@\\d{{3}}{user_id}\\d{{1}}")
        matching_dirs = [d for d in current_dir.iterdir() if d.is_dir() and user_dir_pattern.match(d.name)]
        user_dir_path = matching_dirs[0] if len(matching_dirs) > 0 else None

        if user_dir_path is None:
            error_message += f"{index}行目のユーザは提出済みであるにも関わらず、フォルダが存在しません\n"
            continue
        
        # user_dir_pathの内部にclass{lecture_id}.zipが存在するかチェックする
        user_zip_file_on_workspace = user_dir_path / f"class{lecture_id}.zip"
        if not user_zip_file_on_workspace.exists():
            error_message += f"{index}行目のユーザは提出済みであるにも関わらず、class{lecture_id}.zipを提出していません\n"
            continue
        
        # user_dir_path/"class{lecture_id}.zip"を、{UPLOAD_DIR}/{batch_submission_record.ts}-{batch_submission_record.id}/{user_id}/に解凍する。
        user_zip_file_extract_dest = Path(constant.UPLOAD_DIR) / f"{batch_submission_record.ts.strftime('%Y-%m-%d-%H-%M-%S')}-{batch_submission_record.id}" / user_id
        user_zip_file_extract_dest.mkdir(parents=True, exist_ok=True)
        message = unfold_zip(user_zip_file_on_workspace, user_zip_file_extract_dest)
        if message is not None:
            error_message += f"{index}行目のユーザのZipファイルの解凍中にエラーが発生しました: {message}\n"
            # エラーがあっても一応、ジャッジを行う
        
        # 提出日時を設定する
        # アップロード先のディレクトリパス
        batch_submission_summary_record.upload_dir = str(user_zip_file_extract_dest.relative_to(Path(constant.UPLOAD_DIR)))
        
        # レポートのパス(アップロード先にreport1.pdfがあるはず、なかったらNone)
        report_path = user_zip_file_extract_dest / "report1.pdf"
        if report_path.exists():
            batch_submission_summary_record.report_path = str(report_path.relative_to(Path(constant.UPLOAD_DIR)))
        
        # 提出日時を設定する
        batch_submission_summary_record.submit_date = submit_date
        
        batch_submission_summary_list.append(batch_submission_summary_record)
        
    for batch_submission_summary_record in batch_submission_summary_list:
        assignments.register_batch_submission_summary(db=db, batch_submission_summary_record=batch_submission_summary_record)
        
        # 未提出の場合は、ジャッジを行わない
        if batch_submission_summary_record.status == schemas.StudentSubmissionStatus.NON_SUBMITTED:
            # batch_submission_summary_record.result = None
            continue
        
        if batch_submission_summary_record.upload_dir is None:
            error_message += f"{batch_submission_summary_record.user_id}の提出フォルダが存在しません\n"
            # 提出フォルダが存在しない場合は、非提出とする
            batch_submission_summary_record.status = schemas.StudentSubmissionStatus.NON_SUBMITTED
            assignments.update_batch_submission_summary(db=db, batch_submission_summary_record=batch_submission_summary_record)
            continue
        
        # 提出済みの場合は、ジャッジを行う
        
        uploaded_filepath_list = [
            p for p in (Path(constant.UPLOAD_DIR) / batch_submission_summary_record.upload_dir).iterdir()
            if p.is_file()
        ]
        
        # 各課題ごとにジャッジリクエストを発行する
        for problem, required_file_list in zip(problem_list, required_files_for_problem):
            # ジャッジリクエストをSubmissionテーブルに登録する
            submission_record = assignments.register_submission(
                db=db,
                batch_id=batch_id,
                user_id=batch_submission_summary_record.user_id,
                lecture_id=problem.lecture_id,
                assignment_id=problem.assignment_id,
                for_evaluation=problem.for_evaluation,
            )
            
            total_judge += 1

            # uploaded_filepath_listの中から、required_file_listに含まれているファイルのみ、
            # UploadedFilesテーブルに登録する
            filtered_uploaded_filepath_list = [
                p for p in uploaded_filepath_list
                if p.name in required_file_list
            ]
            
            for p in filtered_uploaded_filepath_list:
                assignments.register_uploaded_file(
                    db=db,
                    submission_id=submission_record.id,
                    path=p.relative_to(Path(constant.UPLOAD_DIR))
                )
            
            # 提出エントリをキューに登録する
            submission_record.progress = schemas.SubmissionProgressStatus.QUEUED
            assignments.modify_submission(
                db=db, submission_record=submission_record
            )
    
    # エラーメッセージを設定する
    batch_submission_record.message = error_message
    # total_judgeの値を更新する
    batch_submission_record.complete_judge = 0
    batch_submission_record.total_judge = total_judge
    assignments.modify_batch_submission(db=db, batch_submission_record=batch_submission_record)
    
    workspace_dir.cleanup()
    return batch_submission_record


@router.get("/status/submissions/me")
async def read_all_submission_status_of_me(
    page: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[schemas.JudgeProgressAndStatus]:
    """
    自身に紐づいた提出の進捗状況を取得する
    
    学生が自身の提出の進捗状況を確認するために使うことを想定している
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ページは1以上である必要があります",
        )

    submission_record_list = assignments.get_submission_list_for_student(
        db, current_user.user_id, limit=20, offset=(page - 1) * 20
    )

    judge_progress_and_status_list = []
    for submission_record in submission_record_list:
        judge_progress_and_status = schemas.JudgeProgressAndStatus(
            **submission_record.model_dump(),
            result=None,
            message=None,
            score=None,
            timeMS=None,
            memoryKB=None,
        )
        if submission_record.progress == schemas.SubmissionProgressStatus.DONE:
            submission_summary = assignments.get_submission_summary(
                db, submission_record.id
            )
            if submission_summary is not None:
                judge_progress_and_status.result = submission_summary.result
                judge_progress_and_status.message = submission_summary.message
                judge_progress_and_status.score = submission_summary.score
                judge_progress_and_status.timeMS = submission_summary.timeMS
                judge_progress_and_status.memoryKB = submission_summary.memoryKB
        judge_progress_and_status_list.append(judge_progress_and_status)

    return judge_progress_and_status_list


@router.get("/status/submissions/all")
async def read_all_submission_status(
    page: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["view_users"]),
    ],
) -> List[schemas.JudgeProgressAndStatus]:
    """
    全ての提出の進捗状況を取得する

    管理者が全ての提出の進捗状況を確認するために使うことを想定している
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ページは1以上である必要があります",
        )

    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理者のみが全ての提出の進捗状況を取得できます",
        )

    submission_record_list = assignments.get_submission_list(
        db, limit=20, offset=(page - 1) * 20
    )
    judge_progress_and_status_list = []
    for submission_record in submission_record_list:
        judge_progress_and_status = schemas.JudgeProgressAndStatus(
            **submission_record.model_dump(),
            result=None,
            message=None,
            score=None,
            timeMS=None,
            memoryKB=None,
        )
        if submission_record.progress == schemas.SubmissionProgressStatus.DONE:
            submission_summary = assignments.get_submission_summary(
                db, submission_record.id
            )
            if submission_summary is not None:
                judge_progress_and_status.result = submission_summary.result
                judge_progress_and_status.message = submission_summary.message
                judge_progress_and_status.score = submission_summary.score
                judge_progress_and_status.timeMS = submission_summary.timeMS
                judge_progress_and_status.memoryKB = submission_summary.memoryKB
        judge_progress_and_status_list.append(judge_progress_and_status)

    return judge_progress_and_status_list


@router.get("/status/submissions/{submission_id}")
async def read_submission_status(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.JudgeProgressAndStatus:
    """
    特定の提出の進捗状況を取得する
    """
    submission_record = assignments.get_submission(db, submission_id)
    if submission_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="提出エントリが見つかりません",
        )

    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        # ユーザがAdmin, Managerでない場合は、ログインユーザの提出のみ取得できる
        if submission_record.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ログインユーザの提出ではありません",
            )

        # バッチ採点に紐づいた提出は取得できない
        if submission_record.batch_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="バッチ採点に紐づいた提出は取得できません",
            )

        # 評価問題の提出は取得できない
        if submission_record.for_evaluation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="評価問題の提出は取得できません",
            )

    judge_progress_and_status = schemas.JudgeProgressAndStatus(
        **submission_record.model_dump(),
        result=None,
        message=None,
        score=None,
        timeMS=None,
        memoryKB=None,
    )

    if submission_record.progress == schemas.SubmissionProgressStatus.DONE:
        submission_summary = assignments.get_submission_summary(
            db, submission_record.id
        )
        if submission_summary is not None:
            judge_progress_and_status.result = submission_summary.result
            judge_progress_and_status.message = submission_summary.message
            judge_progress_and_status.score = submission_summary.score
            judge_progress_and_status.timeMS = submission_summary.timeMS
            judge_progress_and_status.memoryKB = submission_summary.memoryKB

    return judge_progress_and_status


@router.get("/status/submissions/{submission_id}/files/zip", response_class=FileResponse)
async def read_uploaded_file_list(
    submission_id: int,
    type: Literal["uploaded", "arranged"],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> FileResponse:
    """
    特定の提出のファイルのアップロードされたファイルをZIPファイルとして取得する
    """
    submission_record = assignments.get_submission(db, submission_id)
    if submission_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="提出エントリが見つかりません",
        )
    
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        # ユーザがAdmin, Managerでない場合は、ログインユーザの提出のみ取得できる
        if submission_record.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ログインユーザの提出ではありません",
            )
        
        # バッチ採点に紐づいた提出は取得できない
        if submission_record.batch_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="バッチ採点に紐づいた提出は取得できません",
            )
        
        # 評価問題の提出は取得できない
        if submission_record.for_evaluation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="評価問題の提出は取得できません",
            )
    
    # アップロードされたファイルのリストを取得する
    if type == "uploaded":
        file_list = assignments.get_uploaded_files(db, submission_id)
    elif type == "arranged":
        file_list = assignments.get_arranged_files(db=db, lecture_id=submission_record.lecture_id, assignment_id=submission_record.assignment_id, for_evaluation=submission_record.for_evaluation)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="typeは'uploaded'か'arranged'のみ指定できます",
        )
        
    temp_dir = tempfile.TemporaryDirectory()
        
    temp_dir_path = Path(temp_dir.name)
    
    # アップロードされたファイルのリストをZIPファイルとして取得する
    zip_file_path = temp_dir_path / f"{type}_files.zip"
    with zipfile.ZipFile(zip_file_path, "w") as zipf:
        for file in file_list:
            file_path = Path(constant.UPLOAD_DIR) / file.path if type == "uploaded" else Path(constant.RESOURCE_DIR) / file.path
            zipf.write(file_path, arcname=file_path.name)
    
    return FileResponse(zip_file_path, filename=f"{type}_files.zip", media_type="application/zip", background=BackgroundTask(delete_temp_dir, temp_dir))


# バッチ採点に関しては、ManagerとAdminが全てのバッチ採点の進捗状況を見れるようにしている。


@router.get("/status/batch/all")
async def read_all_batch_status(
    page: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> List[schemas.BatchSubmissionRecord]:
    """
    全てのバッチ採点の進捗状況を取得する
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ページは1以上である必要があります",
        )

    batch_submission_record_list = assignments.get_batch_submission_list(db, limit=20, offset=(page - 1) * 20)

    return batch_submission_record_list


@router.get("/status/batch/{batch_id}")
async def read_batch_status(
    batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> schemas.BatchSubmissionRecord:
    """
    バッチ採点の進捗状況を取得する
    """
    batch_submission_progress = assignments.get_batch_submission_progress(db, batch_id)
    if batch_submission_progress is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリが見つかりません",
        )

    return batch_submission_progress


# ジャッジ結果を取得するエンドポイント
# schemas.SubmissionSummaryRecordを返す

@router.get("/result/submissions/{submission_id}")
async def read_submission_summary(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.SubmissionSummaryRecord:
    """
    特定の提出のジャッジ結果を取得する
    """
    submission_record = assignments.get_submission(db, submission_id)
    if submission_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="提出エントリが見つかりません",
        )
    
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        # ユーザがAdmin, Managerでない場合は、ログインユーザのジャッジ結果のみ取得できる
        if submission_record.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ログインユーザのジャッジ結果のみ取得できます",
            )
        
        # バッチ採点に紐づいた提出は取得できない
        if submission_record.batch_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="バッチ採点に紐づいた提出は取得できません",
            )
        
        # 評価問題の提出は取得できない
        if submission_record.for_evaluation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="評価問題の提出は取得できません",
            )

    submission_summary = assignments.get_submission_summary(db, submission_id)
    if submission_summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="提出エントリのジャッジ結果が見つかりません",
        )

    return submission_summary


@router.get("/result/submissions/{submission_id}/detail")
async def read_submission_summary_detail(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.SubmissionSummaryRecord:
    """
    特定の提出のジャッジ結果とその詳細を取得する
    """
    submission_record = assignments.get_submission(db, submission_id)
    if submission_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="提出エントリが見つかりません",
        )
    
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        # ユーザがAdmin, Managerでない場合は、ログインユーザのジャッジ結果のみ取得できる
        if submission_record.user_id != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ログインユーザのジャッジ結果のみ取得できます",
            )
        
        # バッチ提出に紐づいた提出は取得できない
        if submission_record.batch_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="バッチ提出に紐づいた提出は取得できません",
            )
        
        # 評価問題の提出は取得できない
        if submission_record.for_evaluation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="評価問題の提出は取得できません",
            )

    submission_summary = assignments.get_submission_summary_detail(db, submission_id)
    if submission_summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="提出エントリのジャッジ結果が見つかりません",
        )

    return submission_summary


@router.get("/result/batch/{batch_id}", response_model=schemas.BatchEvaluationDetail)
async def read_submission_summary_list_for_batch(
    batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> schemas.BatchEvaluationDetail:
    """
    特定のバッチ採点のジャッジ結果を取得する
    
    詳細は(テストケース毎にかかった時間、メモリ使用量など)取得しない、全体の結果のみ取得される
    """
    batch_submission_record = assignments.get_batch_submission(db, batch_id)
    if batch_submission_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリが見つかりません",
        )

    if batch_submission_record.complete_judge != batch_submission_record.total_judge:
        # 完了していない場合は、詳細は取得できない
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="バッチ採点が完了していません",
        )

    # バッチ提出に含まれた提出エントリを取得する
    submission_entry_list = assignments.get_submission_list_for_batch(db, batch_id)

    # user_id -> list[schemas.SubmissionSummaryRecord]の辞書を作成する
    submission_summary_dict: dict[str, list[schemas.SubmissionSummaryRecord]] = {}
    for submission_entry in submission_entry_list:
        submission_summary = assignments.get_submission_summary(db, submission_entry.id)
        if submission_summary is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="提出エントリのジャッジ結果が見つかりません",
            )
        if submission_entry.user_id not in submission_summary_dict:
            submission_summary_dict[submission_entry.user_id] = [submission_summary]
        else:
            submission_summary_dict[submission_entry.user_id].append(submission_summary)

    # 集計する
    batch_evaluation_detail = schemas.BatchEvaluationDetail(
        batch_id=batch_id,
        ts=batch_submission_record.ts,
        user_id=batch_submission_record.user_id,
        lecture_id=batch_submission_record.lecture_id,
        message=batch_submission_record.message,
        complete_judge=batch_submission_record.complete_judge,
        total_judge=batch_submission_record.total_judge
    )
    
    batch_submission_summary_list = assignments.get_batch_submission_summary_list(db, batch_id)
    evaluation_detail_list = []
    
    for batch_submission_summary in batch_submission_summary_list:
        evaluation_detail = schemas.EvaluationDetail(
            user_id=batch_submission_summary.user_id,
            status=batch_submission_summary.status,
            result=batch_submission_summary.result,
            # TODO: アップロードされたファイルをZIPで取得するAPIを作成する
            uploaded_file_url=f"/assignments/batch/{batch_id}/files/uploaded/{batch_submission_summary.user_id}",
            # TODO: レポートを取得するAPIを作成する
            report_url=f"/assignments/batch/{batch_id}/files/report/{batch_submission_summary.user_id}",
            submit_date=batch_submission_summary.submit_date,
            submission_summary_list=submission_summary_dict[batch_submission_summary.user_id] if batch_submission_summary.status != schemas.StudentSubmissionStatus.NON_SUBMITTED else []
        )
        # もし、statusがSUBMITTEDもしくはDELAYで、resultがNoneの場合は、resultを更新する
        if batch_submission_summary.status in [schemas.StudentSubmissionStatus.SUBMITTED, schemas.StudentSubmissionStatus.DELAY] and batch_submission_summary.result is None:
            # 全体のジャッジ結果を更新する
            result = schemas.SubmissionSummaryStatus.AC
            for submission_summary in submission_summary_dict[batch_submission_summary.user_id]:
                result = max(result, submission_summary.result)
            batch_submission_summary.result = result
            evaluation_detail.result = result
            assignments.update_batch_submission_summary(db, batch_submission_summary)
        evaluation_detail_list.append(evaluation_detail)

    batch_evaluation_detail.evaluation_detail_list = evaluation_detail_list
    return batch_evaluation_detail


@router.get("/result/batch/{batch_id}/user/{user_id}", response_model=schemas.EvaluationDetail)
async def read_submission_summary_list_for_batch_user(
    batch_id: int,
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> schemas.EvaluationDetail:
    """
    特定のバッチ採点のジャッジ結果を取得する
    """
    batch_user_detail = assignments.get_batch_user_detail(db, batch_id, user_id)
    if batch_user_detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリが見つかりません",
        )
    
    submission_summary_list = assignments.get_submission_summary_list_for_batch_user(db, batch_id, user_id)
    
    return schemas.EvaluationDetail(
        user_id=batch_user_detail.user_id,
        status=batch_user_detail.status,
        result=batch_user_detail.result,
        uploaded_file_url=f"/assignments/batch/{batch_id}/files/uploaded/{user_id}",
        report_url=f"/assignments/batch/{batch_id}/files/report/{user_id}",
        submit_date=batch_user_detail.submit_date,
        submission_summary_list=submission_summary_list
    )


@router.get("/result/batch/{batch_id}/files/uploaded/{user_id}", response_class=FileResponse)
async def fetch_uploaded_files_of_batch(
    batch_id: int,
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> FileResponse:
    """
    特定のバッチ採点のアップロードされたファイルを取得する
    """
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="バッチ採点のアップロードされたファイルは取得できません",
        )
    
    # BatchSubmissionSummaryのupload_dirを取得する
    batch_submission_summary = assignments.get_batch_submission_summary(db, batch_id, user_id)
    if batch_submission_summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリのアップロードされたファイルが見つかりません",
        )
    
    upload_dir = batch_submission_summary.upload_dir
    
    if upload_dir is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリのアップロードされたファイルが見つかりません",
        )
        
    upload_dir_path = Path(constant.UPLOAD_DIR) / upload_dir
    
    temp_dir = tempfile.TemporaryDirectory()
    temp_dir_path = Path(temp_dir.name)
    
    # upload_dirのファイルの内容をtemp_dirに置いたZIPファイルに書き込む
    zip_file_path = temp_dir_path / f"uploaded_files.zip"
    with zipfile.ZipFile(zip_file_path, "w") as zipf:
        for file_path in upload_dir_path.iterdir():
            if file_path.is_file():
                zipf.write(file_path, arcname=file_path.name)
    
    return FileResponse(zip_file_path, filename="uploaded_files.zip", media_type="application/zip", background=BackgroundTask(delete_temp_dir, temp_dir))


@router.get("/result/batch/{batch_id}/files/report/{user_id}", response_class=FileResponse)
async def fetch_report_of_batch(
    batch_id: int,
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> FileResponse:
    """
    特定のバッチ採点のレポートを取得する
    """
    if current_user.role not in [schemas.Role.admin, schemas.Role.manager]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="バッチ採点のレポートは取得できません",
        )
    
    batch_submission_summary = assignments.get_batch_submission_summary(db, batch_id, user_id)
    if batch_submission_summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリのレポートが見つかりません",
        )
    
    report_path = batch_submission_summary.report_path
    
    if report_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリのレポートが見つかりません",
        )
    
    report_path = Path(constant.UPLOAD_DIR) / report_path
    
    if not report_path.exists() or not report_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリのレポートが見つかりません",
        )

    return FileResponse(report_path, filename=report_path.name, media_type="application/pdf")
