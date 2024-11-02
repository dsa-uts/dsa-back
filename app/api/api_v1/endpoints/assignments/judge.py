from app.crud.db import assignments
from app.api.api_v1.endpoints.assignments import lecture_is_public, access_sanitize
from fastapi import APIRouter, Depends, Query, Security, HTTPException, status, UploadFile, File
from app.classes import schemas, response
import logging
from typing import Annotated, List
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.api.api_v1.endpoints import authenticate_util
from pathlib import Path
from app import constants as constant
import shutil
import tempfile
from datetime import datetime
from . import unfold_zip


logging.basicConfig(level=logging.DEBUG)

router = APIRouter()

"""
/api/v1/assignments/judge/...以下のエンドポイントの定義
"""

@router.post("/{lecture_id}/{assignment_id}", response_model=response.Submission)
async def single_judge(
    file_list: list[UploadFile],
    lecture_id: int,
    assignment_id: int,
    eval: Annotated[bool, Query(description="採点リソースにアクセスするかどうか")],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> response.Submission:
    """
    単体の採点リクエストを受け付ける
    """
    ############################### Vital #####################################
    access_sanitize(eval=eval, role=current_user.role)
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

    # 課題エントリ(lecture_id, assignment_id)を取得する
    problem_entry = assignments.get_problem(
        db=db,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        eval=eval,
        detail=False,
    )
    if problem_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="課題エントリが見つかりません",
        )

    # ジャッジリクエストをSubmissionテーブルに登録する
    submission_record = assignments.register_submission(
        db=db,
        evaluation_status_id=None,
        user_id=current_user.user_id,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        eval=eval,
    )

    # アップロードされたファイルを/upload/{current_user.user_id}/{submission_record.ts}-{submission_id}に配置する
    upload_dir = Path(constant.UPLOAD_DIR) / f"{current_user.user_id}" / f"{submission_record.ts.strftime('%Y-%m-%d-%H-%M-%S')}-{submission_record.id}"
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
    assignments.modify_submission(db=db, submission=submission_record)

    return response.Submission.model_validate(submission_record)


@router.post("/{lecture_id}", response_model=List[response.Submission])
async def judge_all_by_lecture(
    uploaded_zip_file: Annotated[UploadFile, File(description="学生が最終提出するzipファイル e.t.c. class1.zip")],
    lecture_id: int,
    eval: Annotated[bool, Query(description="採点リソースにアクセスするかどうか")],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[response.Submission]:
    """
    授業エントリに紐づく全ての練習問題を採点する
    
    学生がmanabaに提出する最終成果物が、ちゃんと自動採点されることを確認するために用意している。
    """
    ############################### Vital #####################################
    access_sanitize(eval=eval, role=current_user.role)
    ############################### Vital #####################################
    
    # 授業エントリを取得する
    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )

    # 授業エントリに紐づく全ての練習問題を採点する
    problem_detail_list = assignments.get_problem_detail_list(
        db=db,
        lecture_id=lecture_id,
        eval=eval,
    )
    
    if uploaded_zip_file.filename != f"class{lecture_id}.zip":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"zipファイル名が不正です。class{lecture_id}.zipを提出してください",
        )
        
    # zipファイルの内容を{UPLOAD_DIR}/{user_id}/format-check/{lecture_id}/{current_timestamp}に配置する
    upload_dir = Path(constant.UPLOAD_DIR) / current_user.user_id / "format-check" / str(lecture_id) / datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
    if upload_dir.exists():
        shutil.rmtree(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # アップロードされたzipファイルをtempフォルダにおき、それを展開しupload_dirに配置する
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
    report_path = workspace_dir / f"report{lecture_id}.pdf"
    if not report_path.exists():
        # 一番最初の問題について、Submissionエントリ/SubmissionSummaryエントリを作成し、
        # 何もジャッジされていないことを表す
        problem = problem_detail_list[0]
        submission_record = assignments.register_submission(
            db=db,
            evaluation_status_id=None,
            user_id=current_user.user_id,
            lecture_id=problem.lecture_id,
            assignment_id=problem.assignment_id,
            eval=eval,
        )
        
        submission_record.progress = schemas.SubmissionProgressStatus.DONE
        submission_record.result = schemas.SubmissionSummaryStatus.FN
        submission_record.message = "フォーマットチェック: ZIPファイルにレポートが含まれていません"
        submission_record.detail = f"report{lecture_id}.pdf"
        submission_record.score = 0
        submission_record.timeMS = 0
        submission_record.memoryKB = 0
        assignments.modify_submission(db=db, submission=submission_record)
        return [response.Submission.model_validate(submission_record)]

    submission_record_list = []
    
    # 各Problemエントリごとに、Submissionエントリを作成する
    for problem_detail in problem_detail_list:
        # ジャッジリクエストをSubmissionテーブルに登録する
        submission_record = assignments.register_submission(
            db=db,
            evaluation_status_id=None,
            user_id=current_user.user_id,
            lecture_id=problem_detail.lecture_id,
            assignment_id=problem_detail.assignment_id,
            eval=eval,
        )

        # workspace_dirの中に、required_file_listに含まれるファイルがあるかチェックする
        for required_file in problem_detail.required_files:
            required_file_path = workspace_dir / required_file.name
            if not required_file_path.exists():
                continue
            
            # ファイルをUploadedFilesテーブルに登録する
            assignments.register_uploaded_file(
                db=db, submission_id=submission_record.id, path=required_file_path.relative_to(Path(constant.UPLOAD_DIR))
            )
            
        # report{lecture_id}.pdfもUploadedFilesテーブルに登録す
        if report_path.exists():
            assignments.register_uploaded_file(
                db=db, submission_id=submission_record.id, path=report_path.relative_to(Path(constant.UPLOAD_DIR))
            )

        # 提出エントリをキューに登録する
        submission_record.progress = schemas.SubmissionProgressStatus.QUEUED
        assignments.modify_submission(db=db, submission=submission_record)
        submission_record_list.append(response.Submission.model_validate(submission_record))

    return submission_record_list

