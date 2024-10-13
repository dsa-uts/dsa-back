from app.classes import schemas
from sqlalchemy.orm import Session
from ...classes import models
from typing import List
from datetime import datetime
import pytz
from pathlib import Path


def get_lecture_list(db: Session) -> List[schemas.Lecture]:
    """
    全ての授業エントリを取得する関数
    各授業に紐づく問題のリストまで取得する
    """
    lecture_list = db.query(models.Lecture).all()
    return [
        # lazy loadingを防ぐために、1-N関係にあるネスト情報をなるべくアクセスしないようにする
        schemas.Lecture(
            id=lecture.id,
            title=lecture.title,
            start_date=lecture.start_date,
            end_date=lecture.end_date,
            problems=[
                schemas.Problem(
                    lecture_id=problem.lecture_id,
                    assignment_id=problem.assignment_id,
                    title=problem.title,
                    description_path=problem.description_path,
                    timeMS=problem.timeMS,
                    memoryMB=problem.memoryMB,
                    # problem.test_cases, required_files, arranged_files, executables
                    # までは読み込まない
                )
                for problem in lecture.problems
            ]
        )
        for lecture in lecture_list
    ]


def get_lecture(db: Session, lecture_id: int) -> schemas.Lecture | None:
    lecture = db.query(models.Lecture).filter(models.Lecture.id == lecture_id).first()
    return schemas.Lecture(
        id=lecture.id,
        title=lecture.title,
        start_date=lecture.start_date,
        end_date=lecture.end_date,
    ) if lecture is not None else None


def get_problem_detail(
    db: Session, lecture_id: int, assignment_id: int, eval: bool, detail: bool = False
) -> schemas.Problem | None:
    """
    特定の授業の特定の課題のエントリを取得する関数
    
    detailがTrueの場合、ネスト情報も全て読み込む
    """
    problem = (
        db.query(models.Problem)
        .filter(
            models.Problem.lecture_id == lecture_id,
            models.Problem.assignment_id == assignment_id,
        )
        .first()
    )
    
    if problem is None:
        return None
    
    # ネスト情報も全て読み込む
    problem_record = None
    if detail:
        problem_record = schemas.Problem.model_validate(problem)
        if eval is False:
            # 採点用のリソースをフィルタリングする
            problem_record.executables = [
                executable for executable in problem_record.executables
                if executable.eval is False
            ]
            problem_record.arranged_files = [
                arranged_file for arranged_file in problem_record.arranged_files
                if arranged_file.eval is False
            ]
            problem_record.test_cases = [
                test_case for test_case in problem_record.test_cases
                if test_case.eval is False
            ]
    else:
        problem_record = schemas.Problem(
            lecture_id=problem.lecture_id,
            assignment_id=problem.assignment_id,
            title=problem.title,
            description_path=problem.description_path,
            timeMS=problem.timeMS,
            memoryMB=problem.memoryMB,
        )

    return problem_record


def register_submission(
    db: Session,
    batch_id: int | None,
    user_id: str,
    lecture_id: int,
    assignment_id: int,
    eval: bool,
) -> schemas.Submission:
    """
    ジャッジリクエストをSubmissionテーブルに登録する関数
    """
    new_submission = models.Submission(
        batch_id=batch_id,
        user_id=user_id,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        eval=eval,
    )
    db.add(new_submission)
    db.commit()
    db.refresh(new_submission)
    return schemas.Submission.model_validate(new_submission)


def get_submission(db: Session, submission_id: int) -> schemas.Submission | None:
    """
    特定の提出エントリを取得する関数
    """
    submission = (
        db.query(models.Submission)
        .filter(models.Submission.id == submission_id)
        .first()
    )
    return (
        schemas.Submission.model_validate(submission)
        if submission is not None
        else None
    )


def modify_submission(db: Session, submission: schemas.Submission) -> None:
    """
    提出エントリを更新する関数
    """
    db.query(models.Submission).filter(
        models.Submission.id == submission.id
    ).update(submission.model_dump(exclude={"uploaded_files"}))
    db.commit()


def register_uploaded_file(db: Session, submission_id: int, path: Path) -> None:
    """
    アップロードされたファイルをUploadedFilesテーブルに登録する関数
    """
    new_uploadedfile = models.UploadedFiles(submission_id=submission_id, path=str(path))
    db.add(new_uploadedfile)
    db.commit()


def register_batch_submission(
    db: Session, user_id: str, lecture_id: int
) -> schemas.BatchSubmission:
    """
    バッチ提出をBatchSubmissionテーブルに登録する関数
    """
    new_batch_submission = models.BatchSubmission(user_id=user_id, lecture_id=lecture_id)
    db.add(new_batch_submission)
    db.commit()
    db.refresh(new_batch_submission)
    return schemas.BatchSubmissionRecord.model_validate(new_batch_submission)


def get_submission_list(
    db: Session, limit: int = 10, offset: int = 0
) -> List[schemas.SubmissionRecord]:
    """
    全ての提出の進捗状況を取得する関数
    """
    submission_list = (
        db.query(models.Submission)
        .order_by(models.Submission.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [
        schemas.SubmissionRecord.model_validate(submission)
        for submission in submission_list
    ]


def get_submission_list_for_student(
    db: Session, user_id: str, limit: int = 10, offset: int = 0
) -> List[schemas.SubmissionRecord]:
    """
    学生が提出したシングルジャッジの進捗状況を取得する関数
    """
    submission_list = (
        db.query(models.Submission)
        .filter(
            models.Submission.user_id == user_id,
            models.Submission.for_evaluation == False,
            models.Submission.batch_id == None,
        )
        .order_by(models.Submission.id.desc())  # idの降順に並び替え
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [
        schemas.SubmissionRecord.model_validate(submission)
        for submission in submission_list
    ]


def get_batch_submission(
    db: Session, batch_id: int
) -> schemas.BatchSubmissionRecord | None:
    """
    特定のバッチ採点の進捗状況を取得する関数
    """
    batch_submission = (
        db.query(models.BatchSubmission)
        .filter(models.BatchSubmission.id == batch_id)
        .first()
    )
    
    if batch_submission is None:
        return None
    
    batch_submission_record = schemas.BatchSubmissionRecord.model_validate(batch_submission)
    
    # 完了している場合、進捗状況の更新は不要
    if batch_submission_record.complete_judge == batch_submission_record.total_judge:
        return batch_submission_record
    
    # 進行中の場合、complete_judgeとtotal_judgeを更新する
    complete_judge = (
        db.query(models.Submission)
        .filter(models.Submission.batch_id == batch_id,
                models.Submission.progress == schemas.SubmissionProgressStatus.DONE.value
        ).count()
    )
    
    total_judge = (
        db.query(models.Submission)
        .filter(models.Submission.batch_id == batch_id)
        .count()
    )
    
    batch_submission_record.complete_judge = complete_judge
    batch_submission_record.total_judge = total_judge
    
    modify_batch_submission(db=db, batch_submission_record=batch_submission_record)
    return batch_submission_record


def get_batch_submission_list(
    db: Session, limit: int = 10, offset: int = 0
) -> List[schemas.BatchSubmissionRecord]:
    """
    バッチ採点の進捗状況を取得する関数
    """
    batch_submission_list = (
        db.query(models.BatchSubmission)
        .order_by(models.BatchSubmission.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    
    batch_submission_record_list = [
        schemas.BatchSubmissionRecord.model_validate(batch_submission)
        for batch_submission in batch_submission_list
    ]
    
    for batch_submission in batch_submission_record_list:
        # 完了している場合、進捗状況の更新は不要
        if batch_submission.complete_judge == batch_submission.total_judge:
            continue
        
        # 進行中の場合、complete_judgeとtotal_judgeを更新する
        complete_judge = (
            db.query(models.Submission)
            .filter(models.Submission.batch_id == batch_submission.id,
                    models.Submission.progress == schemas.SubmissionProgressStatus.DONE.value
            ).count()
        )
        
        total_judge = (
            db.query(models.Submission)
            .filter(models.Submission.batch_id == batch_submission.id)
            .count()
        )
        
        batch_submission.complete_judge = complete_judge
        batch_submission.total_judge = total_judge
        modify_batch_submission(db=db, batch_submission_record=batch_submission)

    return batch_submission_record_list


def get_submission_list_for_batch(
    db: Session, batch_id: int
) -> List[schemas.SubmissionRecord]:
    """
    特定のバッチ採点リクエストに紐づいた全ての提出エントリの進捗状況を取得する関数
    """

    submission_list = (
        db.query(models.Submission).filter(models.Submission.batch_id == batch_id).all()
    )
    return [
        schemas.SubmissionRecord.model_validate(submission)
        for submission in submission_list
    ]


def get_submission_summary(
    db: Session, submission_id: int
) -> schemas.SubmissionSummaryRecord | None:
    """
    特定の提出エントリのジャッジ結果を取得する関数
    """
    submission_summary = (
        db.query(models.SubmissionSummary)
        .filter(models.SubmissionSummary.submission_id == submission_id)
        .first()
    )
    return (
        schemas.SubmissionSummaryRecord.model_validate(submission_summary)
        if submission_summary is not None
        else None
    )


def get_submission_summary_detail(
    db: Session, submission_id: int
) -> schemas.SubmissionSummaryRecord | None:
    """
    特定の提出エントリのジャッジ結果を取得する関数

    SubmissionSummaryの中のevaluation_summary_list,
    evaluation_summary_listの中のjudge_result_listといったネスト構造も含めて取得する。
    """
    submission_summary = (
        db.query(models.SubmissionSummary)
        .filter(models.SubmissionSummary.submission_id == submission_id)
        .first()
    )

    if submission_summary is None:
        return None

    submission_summary_record = schemas.SubmissionSummaryRecord.model_validate(
        submission_summary
    )

    # evaluation_summary_listを取得する
    evaluation_summary_list = (
        db.query(models.EvaluationSummary)
        .filter(models.EvaluationSummary.parent_id == submission_summary.submission_id)
        .all()
    )
    submission_summary_record.evaluation_summary_list = [
        schemas.EvaluationSummaryRecord.model_validate(evaluation_summary)
        for evaluation_summary in evaluation_summary_list
    ]

    # evaluation_summary_listの中のjudge_result_listを取得する
    for evaluation_summary in submission_summary_record.evaluation_summary_list:
        judge_result_list = (
            db.query(models.JudgeResult)
            .filter(models.JudgeResult.parent_id == evaluation_summary.id)
            .all()
        )
        evaluation_summary.judge_result_list = [
            schemas.JudgeResultRecord.model_validate(judge_result)
            for judge_result in judge_result_list
        ]

    return submission_summary_record


def get_uploaded_file(
    db: Session, file_id: int
) -> schemas.UploadedFileRecord | None:
    """
    特定のアップロードファイルエントリを取得する関数
    """
    uploaded_file = (
        db.query(models.UploadedFiles).filter(models.UploadedFiles.id == file_id).first()
    )
    return schemas.UploadedFileRecord.model_validate(uploaded_file) if uploaded_file is not None else None


def get_uploaded_files(
    db: Session, submission_id: int
) -> List[schemas.UploadedFileRecord]:
    """
    特定の提出エントリに紐づいたアップロードファイルのリストを取得する関数
    """
    uploaded_files = (
        db.query(models.UploadedFiles).filter(models.UploadedFiles.submission_id == submission_id).all()
    )
    return [schemas.UploadedFileRecord.model_validate(uploaded_file) for uploaded_file in uploaded_files]


def get_arranged_file(
    db: Session, file_id: str
) -> schemas.ArrangedFileRecord | None:
    """
    特定のアレンジされたファイルエントリを取得する関数
    """
    arranged_file = (
        db.query(models.ArrangedFiles).filter(models.ArrangedFiles.str_id == file_id).first()
    )
    return (
        schemas.ArrangedFileRecord.model_validate(arranged_file)
        if arranged_file is not None
        else None
    )


def get_batch_submission_progress(
    db: Session, batch_id: int
) -> schemas.BatchSubmissionRecord | None:
    """
    特定のバッチ採点リクエストについて、
    ID, 提出時間, ユーザIDのほかに、全体のシングルジャッジの数 / 完了したシングルジャッジの数、
    採点ステータス(Queued, Running, Completed)を取得する
    """
    batch_submission = get_batch_submission(db=db, batch_id=batch_id)
    if batch_submission is None:
        return None
    
    # もし、complete_judge=total_judgeであるなら、進捗状況の更新はせず、そのまま返す
    if batch_submission.complete_judge == batch_submission.total_judge:
        return batch_submission
    
    total_judge = (
        db.query(models.Submission)
        .filter(models.Submission.batch_id == batch_id)
        .count()
    )
    
    # そうでないなら、進捗状況を更新する
    complete_judge = (
        db.query(models.Submission)
        .filter(models.Submission.batch_id == batch_id,
                models.Submission.progress == schemas.SubmissionProgressStatus.DONE.value
        ).count()
    )
    
    batch_submission.complete_judge = complete_judge
    batch_submission.total_judge = total_judge
    modify_batch_submission(db=db, batch_submission_record=batch_submission)

    return batch_submission


def register_submission_summary(
    db: Session, submission_summary_record: schemas.SubmissionSummaryRecord
) -> None:
    """
    提出エントリのジャッジ結果をSubmissionSummaryテーブルに登録する関数
    """
    new_submission_summary = models.SubmissionSummary(**submission_summary_record.model_dump(exclude={"evaluation_summary_list"}))
    db.add(new_submission_summary)
    db.commit()


def register_batch_submission_summary(
    db: Session, batch_submission_summary_record: schemas.BatchSubmissionSummaryRecord
) -> None:
    """
    バッチ採点のジャッジ結果をBatchSubmissionSummaryテーブルに登録する関数
    """
    # idは自動採番されるので、モデルに渡さない
    new_batch_submission_summary = models.BatchSubmissionSummary(**batch_submission_summary_record.model_dump())
    db.add(new_batch_submission_summary)
    db.commit()


def update_batch_submission_summary(
    db: Session, batch_submission_summary_record: schemas.BatchSubmissionSummaryRecord
) -> None:
    """
    バッチ採点のジャッジ結果をBatchSubmissionSummaryテーブルに更新する関数
    """
    db.query(models.BatchSubmissionSummary).filter(
        models.BatchSubmissionSummary.batch_id
        == batch_submission_summary_record.batch_id,
        models.BatchSubmissionSummary.user_id
        == batch_submission_summary_record.user_id,
    ).update(batch_submission_summary_record.model_dump())
    db.commit()


def modify_batch_submission(
    db: Session, batch_submission_record: schemas.BatchSubmissionRecord
) -> None:
    """
    バッチ採点のジャッジ結果をBatchSubmissionテーブルに更新する関数
    """
    db.query(models.BatchSubmission).filter(
        models.BatchSubmission.id == batch_submission_record.id
    ).update(batch_submission_record.model_dump())
    db.commit()


def get_batch_submission_summary_list(
    db: Session, batch_id: int
) -> List[schemas.BatchSubmissionSummaryRecord]:
    """
    バッチ採点のジャッジ結果をBatchSubmissionSummaryテーブルに取得する関数
    """
    batch_submission_summary_list = (
        db.query(models.BatchSubmissionSummary).filter(models.BatchSubmissionSummary.batch_id == batch_id).all()
    )
    return [
        schemas.BatchSubmissionSummaryRecord.model_validate(batch_submission_summary)
        for batch_submission_summary in batch_submission_summary_list
    ]


def get_batch_submission_summary(
    db: Session, batch_id: int, user_id: str
) -> schemas.BatchSubmissionSummaryRecord | None:
    """
    特定のバッチ採点のジャッジ結果をBatchSubmissionSummaryテーブルに取得する関数
    """
    batch_submission_summary = (
        db.query(models.BatchSubmissionSummary).filter(models.BatchSubmissionSummary.batch_id == batch_id, models.BatchSubmissionSummary.user_id == user_id).first()
    )
    return (
        schemas.BatchSubmissionSummaryRecord.model_validate(batch_submission_summary)
        if batch_submission_summary is not None
        else None
    )


def get_batch_user_detail(
    db: Session, batch_id: int, user_id: str
) -> schemas.BatchSubmissionSummaryRecord | None:
    """
    特定のバッチ採点のジャッジ結果をBatchSubmissionSummaryテーブルに取得する関数
    """
    batch_submission_summary = (
        db.query(models.BatchSubmissionSummary).filter(models.BatchSubmissionSummary.batch_id == batch_id, models.BatchSubmissionSummary.user_id == user_id).first()
    )
    return schemas.BatchSubmissionSummaryRecord.model_validate(batch_submission_summary) if batch_submission_summary is not None else None


def get_submission_summary_list_for_batch_user(
    db: Session, batch_id: int, user_id: str
) -> List[schemas.SubmissionSummaryRecord]:
    """
    特定のバッチ採点のジャッジ結果をSubmissionSummaryテーブルに取得する関数
    """
    submission_summary_list = (
        db.query(models.SubmissionSummary).filter(models.SubmissionSummary.batch_id == batch_id, models.SubmissionSummary.user_id == user_id).all()
    )
    return [schemas.SubmissionSummaryRecord.model_validate(submission_summary) for submission_summary in submission_summary_list]
