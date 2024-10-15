from app.crud.db import assignments, users
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.dependencies import get_db
from app.classes import schemas, response
from typing import List, Literal
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
import pandas as pd
from starlette.background import BackgroundTask

logging.basicConfig(level=logging.DEBUG)

router = APIRouter()

"""
/api/v1/assignments/...以下のエンドポイントの定義
"""


# 授業エントリに紐づくデータ(授業エントリ、課題エントリ、評価項目、テストケース)が公開期間内かどうかを確認する
def lecture_is_public(lecture_entry: schemas.Lecture) -> bool:
    return authenticate_util.is_past(
        lecture_entry.start_date
    ) and authenticate_util.is_future(lecture_entry.end_date)


def access_sanitize(
    all: bool | None = None,  # 全ての授業エントリを取得するかどうか
    eval: bool | None = None,  # 課題採点かどうか
    role: schemas.Role | None = None,  # ユーザのロール
) -> None:
    """
    アクセス権限のチェックを行う
    """
    if role not in [schemas.Role.manager, schemas.Role.admin]:
        # ユーザがManager, Adminでない場合は、全ての授業エントリを取得することはできない
        if all is not None and all is True:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="公開期間外の情報を取得する権限がありません",
            )
        # ユーザがManager, Adminでない場合は、課題採点のリソースにアクセスすることはできない
        if eval is not None and eval is True:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="課題採点を行う権限がありません",
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


@router.get("/info", response_model=List[response.Lecture])
async def read_lectures(
    all: Annotated[bool, Query(description="公開期間外含めた全ての授業エントリを取得する場合はTrue、そうでない場合はFalse")],  # 全ての授業エントリを取得するかどうか
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[response.Lecture]:
    """
    授業エントリを取得する
    授業(課題1, 課題2, ...)と、それぞれの授業に対応する課題リスト(課題1-1, 課題1-2, ...)も
    合わせて取得する
    """
    ############################### Vital #####################################
    access_sanitize(all=all, role=current_user.role)
    ############################### Vital #####################################

    lecture_list = assignments.get_lecture_list(db)
    if all is True:
        return lecture_list
    else:
        return [response.Lecture.model_validate(lecture) for lecture in lecture_list if lecture_is_public(lecture)]


@router.get("/info/{lecture_id}/{assignment_id}/detail", response_model=response.Problem)
async def read_problem_detail(
    lecture_id: int,
    assignment_id: int,
    eval: Annotated[bool, Query(description="採点リソースにアクセスするかどうか")],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> response.Problem:
    """
    授業エントリに紐づく練習問題のエントリの詳細(評価項目、テストケース)を取得する
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
        if not lecture_is_public():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="授業エントリが公開期間内ではありません",
            )

    problem_detail = assignments.get_problem(
        db=db,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        eval=eval,
        detail=True,
    )
    
    if problem_detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="課題エントリが見つかりません",
        )
    
    res = response.Problem.model_validate(problem_detail)
    
    res.detail = response.ProblemDetail()
    
    # description_pathのファイルの内容を読み込む
    description_path = Path(constant.RESOURCE_DIR) / problem_detail.description_path
    if description_path.exists():
        with open(description_path, "r") as f:
            res.detail.description = f.read()
    
    # RequiredFilesを読み込む
    for required_file in problem_detail.required_files:
        res.detail.required_files.append(
            response.RequiredFiles(
                name=required_file.name
            )
        )
    
    # Executablesを読み込む
    for executable in problem_detail.executables:
        res.detail.executables.append(
            response.Executables(
                eval=executable.eval,
                name=executable.name
            )
        )
    
    # 各TestCasesのstdin, stdout, stderrを読み込む
    for test_case in problem_detail.test_cases:
        test_case_record = response.TestCases(
            id=test_case.id,
            eval=test_case.eval,
            type=test_case.type,
            score=test_case.score,
            title=test_case.title,
            description=test_case.description,
            command=test_case.command,
            args=test_case.args,
            # stdin, stdout, stderrは後でファイルから読み込む
            exit_code=test_case.exit_code,
        )
        
        # stdin, stdout, stderrを読み込む
        if test_case.stdin_path is not None:
            with open(Path(constant.RESOURCE_DIR) / test_case.stdin_path, "r") as f:
                test_case_record.stdin = f.read()
        if test_case.stdout_path is not None:
            with open(Path(constant.RESOURCE_DIR) / test_case.stdout_path, "r") as f:
                test_case_record.stdout = f.read()
        if test_case.stderr_path is not None:
            with open(Path(constant.RESOURCE_DIR) / test_case.stderr_path, "r") as f:
                test_case_record.stderr = f.read()
        res.detail.test_cases.append(test_case_record)

    return res


@router.post("/judge/{lecture_id}/{assignment_id}", response_model=response.Submission)
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


@router.post("/judge/{lecture_id}", response_model=List[response.Submission])
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


@router.post("/batch/{lecture_id}", response_model=response.BatchSubmission)
async def batch_judge(
    uploaded_zip_file: Annotated[UploadFile, File(description="採点者がmanabaから取得するzipファイル")],
    lecture_id: int,
    eval: Annotated[bool, Query(description="採点リソースにアクセスするかどうか")],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> response.BatchSubmission:
    """
    バッチ採点リクエストを受け付ける

    注) 採点用のエンドポイントで、学生が使うことを想定していない。
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
                status_code=status.HTTP_404_NOT_FOUND,
                detail="授業エントリが公開期間内ではありません",
            )

    problem_detail_list = assignments.get_problem_detail_list(
        db=db,
        lecture_id=lecture_id,
        eval=eval,
    )

    # バッチ採点のリクエストをBatchSubmissionテーブルに登録する
    batch_submission_record = assignments.register_batch_submission(
        db=db,
        user_id=current_user.user_id,
        lecture_id=lecture_id
    )

    batch_id = batch_submission_record.id
    total_judge = 0 # 採点対象のジャッジリクエストの数
    
    error_message = ""
    
    batch_dir = Path(constant.UPLOAD_DIR) / "batch" / f"{batch_submission_record.ts.strftime('%Y-%m-%d-%H-%M-%S')}-{batch_submission_record.id}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    
    with tempfile.TemporaryDirectory() as workspace_dir:
        workspace_dir_path = Path(workspace_dir)

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
    
        '''
        current_dirにあるフォルダを読み込み、
        {UPLOAD_DIR}/batch/{batch_submission_record.ts}-{batch_submission_record.id}/
        に以下のような構成で配置する
        .
        ├── 202211479
        │   ├── report1.pdf
        |   ├── Makefile
        |   ├── main.c
        |   └── func.c
        ├── 202211479
        │   ├── report1.pdf
        |   ├── Makefile
        |   ├── main.c
        |   └── func.c
        ├── 202211479
        │   ├── report1.pdf
        |   ├── Makefile
        |   ├── main.c
        |   └── func.c
        ...
        └── reportlist.xlsx
        '''
        
        # reportlist.xlsxもしくはreportlist.xlsをbatch_dirにコピーする
        reportlist_file_on_workspace = current_dir / "reportlist.xlsx"
        if not reportlist_file_on_workspace.exists():
            reportlist_file_on_workspace = current_dir / "reportlist.xls"
            if not reportlist_file_on_workspace.exists():
                # batch_dirを削除して、エラーメッセージを返す
                shutil.rmtree(batch_dir)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="reportlist.xlsxまたはreportlist.xlsが存在しません",
                )
        
        # reportlist.xlsxもしくはreportlist.xlsをbatch_dirにコピーする
        reportlist_file_on_batch = batch_dir / reportlist_file_on_workspace.name
        reportlist_file_on_batch.write_bytes(reportlist_file_on_workspace.read_bytes())
    
        # 各ユーザのフォルダをbatch_dirにコピーする
        for user_dir in current_dir.iterdir():
            if not user_dir.is_dir() or '@' not in user_dir.name:
                continue
            
            # {9桁の学籍番号}@{13桁のID}の{9桁の学籍番号}の部分を取得する
            user_id = user_dir.name.split('@')[0]
                
            # ユーザがDBに登録されているかチェックする
            if users.get_user(db, user_id) is None:
                error_message += f"{user_id}はユーザDBに登録されていません\n"
                continue
            
            # ユーザのclass{lecture_id}.zipの内容を展開し、
            # {batch_dir}/{user_id}/に配置する
            user_zip_file_on_workspace = user_dir / f"class{lecture_id}.zip"
            if not user_zip_file_on_workspace.exists():
                error_message += f"{user_id}は提出済みであるにも関わらず、class{lecture_id}.zipを提出していません\n"
                continue
            
            user_zip_file_extract_dest = batch_dir / user_id
            user_zip_file_extract_dest.mkdir(parents=True, exist_ok=True)
            message = unfold_zip(user_zip_file_on_workspace, user_zip_file_extract_dest)
            if message is not None:
                error_message += f"{user_id}のZipファイルの解凍中にエラーが発生しました: {message}\n"
                continue

    # reportlist.xlsxを読み込み、未提出も含めて、採点対象の学生のリストを取得する
    # 取得する情報、学籍番号、提出状況(提出済/受付終了後提出/未提出)、提出日時(None | datetime)
    report_list_df = assignments_util.get_report_list(batch_dir / "reportlist.xlsx")

    if report_list_df is None:
        # reportlist.xlsxが存在しない場合は、reportlist.xlsを試す
        report_list_df = assignments_util.get_report_list(batch_dir / "reportlist.xls")

    if report_list_df is None:
        # reportlist.xlsxもreportlist.xlsも存在しない場合は、エラーを返す
        shutil.rmtree(batch_dir)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reportlist.xlsxまたはreportlist.xlsが存在しません",
        )
        
    # "# ロール"の値が"履修生"である行のみ残す
    report_list_df = report_list_df[report_list_df["# ロール"] == "履修生"]

    # ユーザの学籍番号をキーとして、そのユーザの提出状況を格納する
    # 未提出のユーザはNoneとする。
    evaluation_status_list: list[schemas.EvaluationStatus] = []

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

        evaluation_status_record = schemas.EvaluationStatus(
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
        
        if evaluation_status_record.status == schemas.StudentSubmissionStatus.NON_SUBMITTED:
            evaluation_status_list.append(evaluation_status_record)
            continue
        
        user_upload_dir = batch_dir / user_id
        
        if not user_upload_dir.exists():
            error_message += f"{index}行目のユーザは提出済みであるにも関わらず、フォルダが存在しません\n"
            continue
        
        # アップロード先ディレクトリを設定する
        evaluation_status_record.upload_dir = str(user_upload_dir.relative_to(Path(constant.UPLOAD_DIR)))
        
        # レポートのパス(アップロード先にreport1.pdfがあるはず、なかったらNone)
        report_path = user_upload_dir / "report1.pdf"
        if report_path.exists():
            evaluation_status_record.report_path = str(report_path.relative_to(Path(constant.UPLOAD_DIR)))
        
        # 提出日時を設定する
        evaluation_status_record.submit_date = submit_date
        
        evaluation_status_list.append(evaluation_status_record)
        
    for evaluation_status_record in evaluation_status_list:
        evaluation_status_record = assignments.register_evaluation_status(db=db, evaluation_status_record=evaluation_status_record)
        
        # 未提出の場合は、ジャッジを行わない
        if evaluation_status_record.status == schemas.StudentSubmissionStatus.NON_SUBMITTED:
            # batch_submission_summary_record.result = None
            continue
        
        if evaluation_status_record.upload_dir is None:
            error_message += f"{evaluation_status_record.user_id}の提出フォルダが存在しません\n"
            # 提出フォルダが存在しない場合は、非提出とする
            evaluation_status_record.status = schemas.StudentSubmissionStatus.NON_SUBMITTED
            assignments.update_evaluation_status(db=db, evaluation_status_record=evaluation_status_record)
            continue
        
        # 提出済みの場合は、ジャッジを行う
        
        # 各課題ごとにジャッジリクエストを発行する
        for problem_detail in problem_detail_list:
            # ジャッジリクエストをSubmissionテーブルに登録する
            submission_record = assignments.register_submission(
                db=db,
                evaluation_status_id=evaluation_status_record.id,
                user_id=evaluation_status_record.user_id,
                lecture_id=problem_detail.lecture_id,
                assignment_id=problem_detail.assignment_id,
                eval=eval,
            )
            
            total_judge += 1

            # uploaded_filepath_listの中から、required_filesに含まれているファイルのみ、
            # UploadedFilesテーブルに登録する
            for required_file in problem_detail.required_files:
                fp = Path(constant.UPLOAD_DIR) / evaluation_status_record.upload_dir / required_file.name
                if fp.exists():
                    assignments.register_uploaded_file(
                        db=db,
                        submission_id=submission_record.id,
                        path=fp.relative_to(Path(constant.UPLOAD_DIR))
                    )
            
            # 提出エントリをキューに登録する
            submission_record.progress = schemas.SubmissionProgressStatus.QUEUED
            assignments.modify_submission(
                db=db, submission=submission_record
            )
    
    # エラーメッセージを設定する
    batch_submission_record.message = error_message
    # total_judgeの値を更新する
    batch_submission_record.complete_judge = 0
    batch_submission_record.total_judge = total_judge
    assignments.modify_batch_submission(db=db, batch_submission_record=batch_submission_record)

    return response.BatchSubmission.model_validate(batch_submission_record)


@router.get("/status/submissions/view", response_model=List[response.Submission])
async def read_all_submission_status_of_me(
    page: int,
    include_eval: Annotated[bool, Query(description="評価用の提出も含めるかどうか")],
    all: Annotated[bool, Query(description="全てのユーザの提出を含めるかどうか")],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> List[response.Submission]:
    """
    自身に紐づいた提出の進捗状況を取得する
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ページは1以上である必要があります",
        )

    if current_user.role not in [
        schemas.Role.student,
        schemas.Role.admin,
        schemas.Role.manager,
    ]:
        if include_eval:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="管理者のみが評価用の提出の進捗状況を取得できます",
            )

        if all:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="管理者のみが全てのユーザの提出の進捗状況を取得できます",
            )

    submission_record_list = assignments.get_submission_list(
        db=db,
        limit=10,
        offset=(page - 1) * 10,
        user_id=None if all else current_user.user_id,
        include_eval=include_eval,
    )

    return [
        response.Submission.model_validate(submission_record)
        for submission_record in submission_record_list
    ]


@router.get("/status/submissions/id/{submission_id}", response_model=response.Submission)
async def read_submission_status(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> response.Submission:
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
        if submission_record.evaluation_status_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="バッチ採点に紐づいた提出は取得できません",
            )

        # 評価問題の提出は取得できない
        if submission_record.eval:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="評価問題の提出は取得できません",
            )

    return response.Submission.model_validate(submission_record)


@router.get("/status/submissions/id/{submission_id}/files/zip", response_class=FileResponse)
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
        if submission_record.evaluation_status_id is not None:
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
        file_list = assignments.get_arranged_files(db=db, lecture_id=submission_record.lecture_id, assignment_id=submission_record.assignment_id, eval=submission_record.eval)
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


@router.get("/status/batch/all", response_model=List[response.BatchSubmission])
async def read_all_batch_status(
    page: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> List[response.BatchSubmission]:
    """
    全てのバッチ採点の進捗状況を取得する
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ページは1以上である必要があります",
        )

    batch_submission_record_list = assignments.get_batch_submission_list(db, limit=20, offset=(page - 1) * 20)

    return [response.BatchSubmission.model_validate(batch_submission_record) for batch_submission_record in batch_submission_record_list]


@router.get("/status/batch/id/{batch_id}", response_model=response.BatchSubmission)
async def read_batch_status(
    batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> response.BatchSubmission:
    """
    バッチ採点の進捗状況を取得する
    """
    batch_submission_status = assignments.get_batch_submission_status(db, batch_id)
    if batch_submission_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリが見つかりません",
        )

    return response.BatchSubmission.model_validate(batch_submission_status)


# ジャッジ結果を取得するエンドポイント
# response.SubmissionSummaryを返す

@router.get("/result/submissions/id/{submission_id}", response_model=response.Submission)
async def read_submission_summary(
    submission_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["me"]),
    ],
) -> response.Submission:
    """
    特定の提出のジャッジ結果を取得する
    
    全体の結果だけでなく、個々のテストケースの結果も取得する。
    """
    submission_record = assignments.get_submission(db, submission_id, detail=True)
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
        if submission_record.evaluation_status_id is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="バッチ採点に紐づいた提出は取得できません",
            )
        
        # 評価問題の提出は取得できない
        if submission_record.eval:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="評価問題の提出は取得できません",
            )
    
    if submission_record.progress != schemas.SubmissionProgressStatus.DONE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ジャッジが完了していません",
        )
    
    res = response.Submission.model_validate(submission_record)

    return res


@router.get("/result/batch/id/{batch_id}", response_model=response.BatchSubmission)
async def read_submission_summary_list_for_batch(
    batch_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> response.BatchSubmission:
    """
    特定のバッチ採点のジャッジ結果を取得する
    
    詳細は(テストケース毎にかかった時間、メモリ使用量など)取得しない、全体の結果のみ取得される
    BatchSubmission -{ EvaluationStatus -{ Submission の粒度まで取得する
    """
    batch_submission_record = assignments.get_batch_submission_status(db, batch_id)
    if batch_submission_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリが見つかりません",
        )

    if (batch_submission_record.complete_judge is None 
        or batch_submission_record.total_judge is None) or batch_submission_record.complete_judge != batch_submission_record.total_judge:
        # 完了していない場合は、詳細は取得できない
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="バッチ採点が完了していません",
        )
    
    batch_submission_detail = assignments.get_batch_submission_detail(db, batch_id)
    if batch_submission_detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリが見つかりません",
        )
    
    # 完了していて、かつEvaluationStatusのresultが更新されていない場合は、更新する
    if len(batch_submission_detail.evaluation_statuses) > 0 and batch_submission_detail.evaluation_statuses[0].result is None:
        for evaluation_status in batch_submission_detail.evaluation_statuses:
            # 全Submissionのresultをaggregationする
            submission_results = [
                submission.result for submission in evaluation_status.submissions
            ]
            
            if len(submission_results) == 0:
                # 課題が未提出の場合は、"None"とする
                evaluation_status.result = None
                assignments.update_evaluation_status(db, evaluation_status)
                continue
            
            aggregation_result = schemas.SubmissionSummaryStatus.AC
            for submission_result in submission_results:
                aggregation_result = max(aggregation_result, submission_result)
            
            evaluation_status.result = aggregation_result
            
            assignments.update_evaluation_status(db, evaluation_status)

    ret = response.BatchSubmission.model_validate(batch_submission_detail)
    
    for dest, src in zip(ret.evaluation_statuses, batch_submission_detail.evaluation_statuses):
        dest.upload_file_exists = src.upload_dir is not None
        dest.report_exists = src.report_path is not None
    
    return ret


@router.get("/result/batch/id/{batch_id}/user/{user_id}", response_model=response.EvaluationStatus)
async def read_submission_summary_list_for_batch_user(
    batch_id: int,
    user_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[
        schemas.UserRecord,
        Security(authenticate_util.get_current_active_user, scopes=["batch"]),
    ],
) -> response.EvaluationStatus:
    """
    特定のバッチ採点の特定のユーザの採点結果を取得する
    
    EvaluationStatus -{ Submission -{ JudgeResultの粒度まで取得する
    """
    evaluation_status = assignments.get_evaluation_status(db, batch_id, user_id)
    if evaluation_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="バッチ採点エントリが見つかりません",
        )
    
    evaluation_status_detail = assignments.get_evaluation_status_detail(db, batch_id, user_id)
    
    ret = response.EvaluationStatus.model_validate(evaluation_status_detail)
    ret.upload_file_exists = evaluation_status_detail.upload_dir is not None
    ret.report_exists = evaluation_status_detail.report_path is not None

    return ret


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
    batch_submission_summary = assignments.get_evaluation_status(db, batch_id, user_id)
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
    
    batch_submission_summary = assignments.get_evaluation_status(db, batch_id, user_id)
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
