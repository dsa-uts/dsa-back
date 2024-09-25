from ....crud.db import assignments, users
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ....dependencies import get_db
from ....classes import schemas
from typing import List, Optional
from datetime import datetime
from pytz import timezone
from fastapi import UploadFile, File, HTTPException, Security, status
from fastapi.responses import JSONResponse
from app.api.api_v1.endpoints import authenticate_util
from typing import Annotated
import logging
from .... import constants as constant
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
async def lecture_is_public(lecture_entry: schemas.LectureRecord) -> bool:
    return authenticate_util.is_past(
        lecture_entry.start_date
    ) and authenticate_util.is_future(lecture_entry.end_date)


@router.get("/all", response_model=List[schemas.LectureRecord])
async def read_all_lectures(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(
            authenticate_util.get_current_active_user, scopes=["view_all_problems"]
        ),
    ],
) -> List[schemas.LectureRecord]:
    """
    全ての授業エントリを取得する
    """
    lecture_list = assignments.get_lecture_list(db)
    return lecture_list


@router.get("/all/{lecture_id}", response_model=List[schemas.ProblemRecord])
async def read_all_problems(
    db: Annotated[Session, Depends(get_db)],
    lecture_id: int,
    current_user: Annotated[
        schemas.UserRecord,
        Security(
            authenticate_util.get_current_active_user, scopes=["view_all_problems"]
        ),
    ],
) -> List[schemas.ProblemRecord]:
    problem_list = assignments.get_problem_list(db, lecture_id)
    return problem_list


@router.get(
    "/all/{lecture_id}/{assignment_id}/{for_evaluation}",
    response_model=schemas.ProblemRecord,
)
async def read_problem_entry(
    db: Annotated[Session, Depends(get_db)],
    lecture_id: int,
    assignment_id: int,
    for_evaluation: bool,
    current_user: Annotated[
        schemas.UserRecord,
        Security(
            authenticate_util.get_current_active_user, scopes=["view_all_problems"]
        ),
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


@router.get("/public/format-check", response_model=List[schemas.LectureRecord])
def read_lectures_for_format_check(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[schemas.LectureRecord]:
    """
    公開期間内の授業エントリを取得する
    """
    lecture_list = assignments.get_lecture_list(db)

    # 公開期間内の授業エントリのみを返す
    public_lecture_list = [
        lecture for lecture in lecture_list if lecture_is_public(lecture)
    ]
    return public_lecture_list


@router.get(
    "/public/format-check/{lecture_id}", response_model=List[schemas.ProblemRecord]
)
def read_problems_for_format_check(
    lecture_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[schemas.ProblemRecord]:
    """
    公開期間内の授業エントリに紐づく問題のリストを取得する
    """
    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )
    if not lecture_is_public(lecture_entry):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが公開期間内ではありません",
        )
    problem_list = assignments.get_problem_list(db, lecture_id)
    return [problem for problem in problem_list if not problem.for_evaluation]


@router.get(
    "/public/format-check/{lecture_id}/{assignment_id}",
    response_model=schemas.ProblemRecord,
)
async def read_problem_entry_for_format_check(
    lecture_id: int,
    assignment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.ProblemRecord:
    """
    公開期間内の授業エントリに紐づく問題のエントリを取得する
    """
    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )
    if not lecture_is_public(lecture_entry):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが公開期間内ではありません",
        )
    problem = assignments.get_problem_recursive(
        db, lecture_id, assignment_id, for_evaluation=False
    )
    if problem is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="課題エントリが見つかりません",
        )
    return problem


@router.post("/public/format-check/judge/{lecture_id}/{assignment_id}")
async def single_judge_for_format_check(
    file_list: list[UploadFile],
    lecture_id: int,
    assignment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.SubmissionRecord:
    """
    単体のフォーマットチェック用の採点リクエストを受け付ける
    """

    # 課題エントリ(lecture_id, assignment_id, for_evaluation=False)を取得する
    problem_entry = assignments.get_problem_recursive(
        db=db,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=False,
    )
    if problem_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="課題エントリが見つかりません",
        )

    # 授業エントリが公開期間内かどうかを確認す
    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )
    if not lecture_is_public(lecture_entry):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが公開期間内ではありません",
        )

    # ジャッジリクエストをSubmissionテーブルに登録する
    submission_record = assignments.register_submission(
        db=db,
        batch_id=None,
        user_id=current_user.user_id,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=False,
    )

    # アップロードされたファイルを/upload/{submission_id}に配置する
    # それと同時にUploadedFilesテーブルに登録する
    upload_dir = Path(constant.UPLOAD_DIR) / str(submission_record.id)
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


@router.post("/private/evaluate/judge/{lecture_id}/{assignment_id}")
async def single_judge(
    file_list: list[UploadFile],
    lecture_id: int,
    assignment_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> schemas.SubmissionRecord:
    """
    単体の採点リクエストを受け付ける

    注) 採点用のエンドポイントで、学生が使うことを想定していない。
    """
    # 課題エントリが無い場合は、404エラーを返す
    problem_entry = assignments.get_problem_recursive(
        db=db,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=True,
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
        for_evaluation=True,
    )

    # アップロードされたファイルを/upload/{submission_id}に配置する
    # それと同時にUploadedFilesテーブルに登録する
    upload_dir = Path(constant.UPLOAD_DIR) / str(submission_record.id)
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


@router.post("/private/evaluate/judge/{lecture_id}")
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
    # 授業エントリが無い場合は、404エラーを返す
    lecture_entry = assignments.get_lecture(db, lecture_id)
    if lecture_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="授業エントリが見つかりません",
        )

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


@router.get("/public/format-check/status/me/submissions/{submission_id}")
async def read_format_check_status_for_student(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.SubmissionRecord:
    """
    ログインユーザの、特定のシングルジャッジの進捗状況を取得する
    """
    submission_record = assignments.get_submission(db, submission_id)
    if submission_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="提出エントリが見つかりません",
        )

    #
    if (
        submission_record.batch_id is not None
        or submission_record.user_id != current_user.user_id
        or submission_record.for_evaluation
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="アクセスできません",
        )

    return submission_record


@router.get("/public/format-check/status/me/submissions")
async def read_all_format_check_status_for_student(
    page: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[schemas.SubmissionRecord]:
    """
    学生が提出した全てのシングルジャッジの進捗状況を取得する
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


@router.get("/private/evaluate/status/batch/{batch_id}")
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


@router.get("/private/evaluate/status/batch")
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


# 学生用
@router.get("/public/format-check/result/me/submissions/{submission_id}")
async def read_submission_summary_for_format_check(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.SubmissionSummaryRecord:
    """
    ログインユーザの、特定のシングルジャッジのジャッジ結果を取得する
    """
    submission_record = assignments.get_submission(db, submission_id)
    if submission_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="提出エントリが見つかりません",
        )

    if (
        submission_record.batch_id is not None
        or submission_record.user_id != current_user.user_id
        or submission_record.for_evaluation
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="アクセスできません",
        )

    return assignments.get_submission_summary(db, submission_id)


# 採点者用(全員で共有する)
@router.get("/private/evaluate/result/submissions/{submission_id}")
async def read_submission_summary_for_judge(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> schemas.SubmissionSummaryRecord:
    """
    採点用の提出エントリのジャッジ結果を取得する
    """
    submission_summary = assignments.get_submission_summary(db, submission_id)
    if submission_summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="提出エントリが見つかりません",
        )

    return submission_summary


@router.get("/private/evaluate/result/submissions")
async def read_all_submission_summary_for_judge(
    page: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> List[schemas.SubmissionSummaryRecord]:
    """
    全ての採点用の提出エントリのジャッジ結果を取得する
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ページは1以上である必要があります",
        )

    return assignments.get_all_submission_summary(db, limit=20, offset=(page - 1) * 20)


@router.get("/private/evaluate/result/batch/{batch_id   }")
async def read_batch_submission_summary_for_judge(
    batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> List[schemas.SubmissionSummaryRecord]:
    """
    特定のバッチ採点のジャッジ結果を取得する
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
    submission_summary_list = [
        assignments.get_submission_summary(db, submission_entry.id)
        for submission_entry in submission_entry_list
    ]

    return submission_summary_list
