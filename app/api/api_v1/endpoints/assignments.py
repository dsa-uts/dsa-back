from ....crud.db import assignments, users
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from ....dependencies import get_db, get_temporary_directory
from ....classes import schemas
from typing import List, Optional, Dict
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
    workspace_dir: Annotated[Path, Depends(get_temporary_directory)],
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
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # アップロードされたzipファイルをtemp_dir下にコピーする
        temp_uploaded_zip_file_path = Path(temp_dir) / uploaded_zip_file.filename
        with open(temp_uploaded_zip_file_path, "wb") as temp_uploaded_zip_file:
            shutil.copyfileobj(uploaded_zip_file.file, temp_uploaded_zip_file)
        # アップロードされたzipファイルをtemp_dirに解凍する
        unzip_result = unfold_zip(temp_uploaded_zip_file_path, workspace_dir)
        if unzip_result is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=unzip_result,
            )
    
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

        # アップロードされたファイルを/upload/{submission_record.ts}-{current_user.user_id}-{submission_id}に配置する
        # 要求されているファイルのリストに含まれているファイルのみを配置する
        upload_dir = Path(constant.UPLOAD_DIR) / f"{submission_record.ts.strftime('%Y-%m-%d-%H-%M-%S')}-{current_user.user_id}-{submission_record.id}"
        if upload_dir.exists():
            shutil.rmtree(upload_dir)

        upload_dir.mkdir(parents=True, exist_ok=True)

        for file in workspace_dir.iterdir():
            if file.is_dir():
                # フォルダが無いはずだが、念のためにチェックしておく
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="zipファイル内にフォルダが含まれています",
                )
            
            if file.name not in required_file_list:
                continue

            with open(file, "rb") as source_file:
                dest_path = upload_dir / file.name
                with open(dest_path, "wb") as dest_file:
                    shutil.copyfileobj(source_file, dest_file)
                assignments.register_uploaded_file(
                    db=db, submission_id=submission_record.id, path=dest_path.relative_to(Path(constant.UPLOAD_DIR))
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
    workspace_dir: Annotated[Path, Depends(get_temporary_directory)],
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
    
    # アップロードされたzipファイルをworkspace_dirに展開する
    with zipfile.ZipFile(uploaded_zip_file.file, "r") as zip_ref:
        zip_ref.extractall(workspace_dir)
    
    # 展開先のディレクトリで、フォルダが一個しかない
    current_dir = workspace_dir
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
    # フォルダ名が"{9桁のID}@{13桁のID}"の形式であり、全ての{9桁のID}が、Userテーブルに存在することを確認する
    user_id_and_zip_file_list: list[tuple[str, Path]] = []
    
    for user_dir in current_dir.iterdir():
        if not user_dir.is_dir():
            continue
        
        if not re.match(r"^\d{9}@\d{13}$", user_dir.name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"フォルダ名が不正です: {user_dir.name}",
            )
        
        user_id = user_dir.name.split("@")[0]
        if users.get_user(db, user_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ユーザが見つかりません: {user_id}",
            )
        
        user_id_and_zip_file_list.append((user_id, user_dir / f"class{lecture_id}.zip"))

    # ユーザごとに各課題のジャッジリクエストを発行する
    for user_id, zip_file_path in user_id_and_zip_file_list:
        if not zip_file_path.exists():
            # 要件を満たしていないので、全ての課題を未回答とする
            for problem in problem_list:
                submission_record = assignments.register_submission(
                    db=db,
                    batch_id=batch_id,
                    user_id=user_id,
                    lecture_id=problem.lecture_id,
                    assignment_id=problem.assignment_id,
                    for_evaluation=problem.for_evaluation,
                )
                submission_record.progress = schemas.SubmissionProgressStatus.DONE
                assignments.modify_submission(db=db, submission_record=submission_record)
            continue
        
        # class{lecture_id}.zipをtemp_dirに解凍する
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            error_message = unfold_zip(zip_file_path, temp_dir_path)
            if error_message is not None:
                # エラーがある場合は、全ての課題を未回答とする
                for problem in problem_list:
                    submission_record = assignments.register_submission(
                        db=db,
                        batch_id=batch_id,
                        user_id=user_id,
                        lecture_id=problem.lecture_id,
                        assignment_id=problem.assignment_id,
                        for_evaluation=problem.for_evaluation,
                    )
                    submission_record.progress = schemas.SubmissionProgressStatus.DONE
                    assignments.modify_submission(db=db, submission_record=submission_record)
                continue
            
            # 解凍したファイルのリストを取得
            file_list = [
                file_path for file_path in temp_dir_path.iterdir() if file_path.is_file()
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

                # アップロード先のフォルダ"/upload/{submission_record.ts}-{user_id}-{submission_record.id}"を作成する
                upload_dir = Path(constant.UPLOAD_DIR) / f"{submission_record.ts.strftime('%Y-%m-%d-%H-%M-%S')}-{submission_record.id}"
                if upload_dir.exists():
                    shutil.rmtree(upload_dir)

                upload_dir.mkdir(parents=True, exist_ok=True)

                # アップロードされたファイルをupload_dirに配置する
                # 要求されているファイルのリストに含まれているファイルのみを配置する
                for file in file_list:
                    if file.name not in required_file_list:
                        continue
                    
                    # ファイルを開く
                    with open(file, "rb") as source_file:
                        # ファイルをアップロード先に配置する
                        dest_path = upload_dir / file.name
                        with open(dest_path, "wb") as dest_file:
                            shutil.copyfileobj(source_file, dest_file)
                        assignments.register_uploaded_file(
                            db=db, submission_id=submission_record.id, path=dest_path.relative_to(Path(constant.UPLOAD_DIR))
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
                        Path(constant.UPLOAD_DIR)
                        / "report"
                        / user_id
                        / str(lecture_id)
                        / f"report{lecture_id}-{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}.pdf"
                    )
                    report_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(file, report_path)

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


@router.get("/status/submissions/{submission_id}/files")
async def read_file_list(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[schemas.FileRecord]:
    """
    特定の提出のファイルのリストを取得する
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
    uploaded_files = assignments.get_uploaded_files(db, submission_id)
    
    file_record_list = []
    for uploaded_file in uploaded_files:
        file_path = Path(constant.UPLOAD_DIR) / uploaded_file.path
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="アップロードされたファイルが見つかりません",
            )
        
        # ファイルサイズが50KB以下の場合は、テキストデータとして取得し、レスポンスに含める
        if file_path.stat().st_size <= 50 * 1024:
            with open(file_path, "r") as f:
                text = f.read()
            file_record = schemas.FileRecord(
                name=Path(uploaded_file.path).name,
                type="uploaded",
                text=text
            )
            file_record_list.append(file_record)
        else:
            # ファイルサイズが50KB以上の場合は、ファイルのURLをレスポンスに含める
            file_record = schemas.FileRecord(
                name=Path(uploaded_file.path).name,
                type="uploaded",
                url=f"assignments/status/submissions/{submission_id}/files/uploaded/{uploaded_file.id}"
            )
            file_record_list.append(file_record)
        
    # アレンジされたファイルのリストを取得する
    arranged_files = assignments.get_arranged_files(
        db=db, 
        lecture_id=submission_record.lecture_id, 
        assignment_id=submission_record.assignment_id, 
        for_evaluation=submission_record.for_evaluation
    )
    
    for arranged_file in arranged_files:
        file_path = Path(constant.RESOURCE_DIR) / arranged_file.path
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="アレンジされたファイルが見つかりません",
            )
        
        # ファイルサイズが50KB以下の場合は、テキストデータとして取得し、レスポンスに含める
        if file_path.stat().st_size <= 50 * 1024:
            with open(file_path, "r") as f:
                text = f.read()
            file_record = schemas.FileRecord(
                name=Path(arranged_file.path).name,
                type="arranged",
                text=text
            )
            file_record_list.append(file_record)
        else:
            # ファイルサイズが50KB以上の場合は、ファイルのURLをレスポンスに含める
            file_record = schemas.FileRecord(
                name=Path(arranged_file.path).name,
                type="arranged",
                url=f"assignments/status/submissions/{submission_id}/files/arranged/{arranged_file.str_id}"
            )
            file_record_list.append(file_record)
    
    return file_record_list


@router.get("/status/submissions/{submission_id}/files/uploaded/{file_id}")
async def read_uploaded_file(
    submission_id: int,
    file_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> FileResponse:
    """
    特定の提出のアップロードされたファイルを取得する
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
    
    uploaded_file_record = assignments.get_uploaded_file(db, file_id)
    if uploaded_file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="アップロードファイルエントリが見つかりません",
        )
    
    if uploaded_file_record.submission_id != submission_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="提出IDが一致しません",
        )
    
    file_path = Path(constant.UPLOAD_DIR) / uploaded_file_record.path
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="アップロードされたファイルが見つかりません",
        )
    
    return FileResponse(file_path)
    

@router.get("/status/submissions/{submission_id}/files/arranged/{file_id}")
async def read_arranged_file(
    submission_id: int,
    file_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> schemas.TextDataResponse:
    """
    特定の提出のアレンジされたファイルを取得する
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
    
    arranged_file_record = assignments.get_arranged_file(db, file_id)
    if arranged_file_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="アレンジされたファイルエントリが見つかりません",
        )
    
    if arranged_file_record.lecture_id != submission_record.lecture_id or \
        arranged_file_record.assignment_id != submission_record.assignment_id or \
        arranged_file_record.for_evaluation != submission_record.for_evaluation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="提出IDが一致しません",
        )

    file_path = Path(constant.RESOURCE_DIR) / arranged_file_record.path
    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="アレンジされたファイルが見つかりません",
        )

    return FileResponse(file_path)


# バッチ採点に関しては、ManagerとAdminが全てのバッチ採点の進捗状況を見れるようにしている。


@router.get("/status/batch/all")
async def read_all_batch_status(
    page: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> List[schemas.BatchSubmissionProgress]:
    """
    全てのバッチ採点の進捗状況を取得する
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ページは1以上である必要があります",
        )

    batch_submission_record_list = assignments.get_batch_submission_list(db, limit=20, offset=(page - 1) * 20)
    
    batch_submission_progress_list: list[schemas.BatchSubmissionProgress] = [
        assignments.get_batch_submission_progress(db, batch_submission_record.id)
        for batch_submission_record in batch_submission_record_list
    ]

    return batch_submission_progress_list


@router.get("/status/batch/{batch_id}")
async def read_batch_status(
    batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> schemas.BatchSubmissionProgress:
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
