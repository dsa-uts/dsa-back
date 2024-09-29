from ....crud.db import assignments, users
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ....dependencies import get_db
from ....classes import schemas
from typing import List, Optional, Dict
from datetime import datetime
from pytz import timezone
from fastapi import UploadFile, File, HTTPException, Security, status
from fastapi.responses import JSONResponse
from app.api.api_v1.endpoints import authenticate_util
from typing import Annotated
import logging
from app import constants as constant
import shutil
from pathlib import Path
import tempfile
import zipfile

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


@router.get("/", response_model=List[schemas.LectureRecord])
async def read_(
    open: bool,  # 公開期間内かどうか
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


@router.get("/{lecture_id}", response_model=List[schemas.ProblemRecord])
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


@router.get("/{lecture_id}/{assignment_id}", response_model=schemas.ProblemRecord)
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
    "/{lecture_id}/{assignment_id}/description",
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
    return schemas.TextDataResponse(data=description)


@router.post("/{lecture_id}/{assignment_id}/judge")
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
                status_code=status.HTTP_404_NOT_FOUND,
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

    # アップロードされたファイルを/upload/{submission_id}に配置する
    upload_dir = Path(constant.UPLOAD_DIR) / str(submission_record.id)
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
                db=db, submission_id=submission_record.id, path=dest_path
            )

    # 提出エントリをキューに登録する
    submission_record.progress = schemas.SubmissionProgressStatus.QUEUED
    assignments.modify_submission(db=db, submission_record=submission_record)

    return submission_record


@router.post("/{lecture_id}/batch")
async def batch_judge(
    zip_file: UploadFile,
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
            file_list = [
                file_path for file_path in user_dir.iterdir() if file_path.is_file()
            ]

            # 各課題のジャッジリクエストを作成する
            for problem, required_file_list in zip(
                problem_list, required_files_for_problem
            ):

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
                upload_dir = Path(constant.UPLOAD_DIR) / str(submission_record.id)
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
                assignments.modify_submission(
                    db=db, submission_record=submission_record
                )

            # PDFファイルを探す
            report_path: Path | None = None
            for file in file_list:
                if file.name.endswith(".pdf"):
                    # "UPLOAD_DIR/report/{user_id}/{lecture_id}/"にアップロード
                    report_path = (
                        upload_dir
                        / "report"
                        / user_id
                        / str(problem.lecture_id)
                        / file.name
                    )
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
                ),
            )

    return batch_submission_record


@router.get("/status/submissions/{submission_id}")
async def read_submission_status(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.SubmissionRecord:
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

    return submission_record


@router.get("/status/submissions/me")
async def read_all_submission_status_of_me(
    page: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[schemas.SubmissionRecord]:
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

    return submission_record_list


# バッチ採点に関しては、ManagerとAdminが全てのバッチ採点の進捗状況を見れるようにしている。


@router.get("/status/batch/{batch_id}")
async def read_batch_status(
    batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> list[schemas.SubmissionRecord]:
    """
    バッチ採点の進捗状況を取得する
    """
    batch_submission_record = assignments.get_batch_submission(db, batch_id)
    if batch_submission_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリが見つかりません",
        )

    return assignments.get_submission_list_for_batch(db, batch_id)


@router.get("/status/batch")
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

    return assignments.get_batch_submission_list(db, limit=20, offset=(page - 1) * 20)


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


@router.get("/result/batch/{batch_id}", response_model=Dict[int, schemas.SubmissionSummaryRecord | None])
async def read_submission_summary_list_for_batch(
    batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> Dict[int, schemas.SubmissionSummaryRecord | None]:
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

    # バッチ提出に含まれた提出エントリを取得する
    submission_entry_list = assignments.get_submission_list_for_batch(db, batch_id)

    # 各提出エントリのジャッジ結果を取得する
    submission_summary_list = {
        submission_entry.id: assignments.get_submission_summary(db, submission_entry.id)
        for submission_entry in submission_entry_list
    }

    return submission_summary_list
