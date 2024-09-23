from app.classes import schemas
from sqlalchemy.orm import Session
from ...classes import models
from typing import List
from datetime import datetime
import pytz
from pathlib import Path


def get_lecture_list(db: Session) -> List[schemas.LectureRecord]:
    """
    全ての授業エントリを取得する関数
    """
    lecture_list = db.query(models.Lecture).all()
    return [schemas.LectureRecord(**lecture.__dict__) for lecture in lecture_list]


def get_lecture(db: Session, lecture_id: int) -> schemas.LectureRecord | None:
    """
    特定の回の授業エントリを取得する関数
    """
    lecture = db.query(models.Lecture).filter(models.Lecture.id == lecture_id).first()
    return schemas.LectureRecord(**lecture.__dict__) if lecture is not None else None


def get_problem(
    db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool
) -> schemas.ProblemRecord:
    """
    特定の授業の特定の課題のエントリを取得する関数
    """
    problem = (
        db.query(models.Problem)
        .filter(
            models.Problem.lecture_id == lecture_id,
            models.Problem.assignment_id == assignment_id,
            models.Problem.for_evaluation == for_evaluation,
        )
        .first()
    )
    return schemas.ProblemRecord(**problem.__dict__)


def get_problem_list(db: Session, lecture_id: int) -> list[schemas.ProblemRecord]:
    """
    特定の授業に基づく問題のリストを取得する関数
    """
    problem_list = (
        db.query(models.Problem).filter(models.Problem.lecture_id == lecture_id).all()
    )
    return [schemas.ProblemRecord(**problem.__dict__) for problem in problem_list]


def get_evaluation_item_list(
    db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool
) -> list[schemas.EvaluationItemRecord]:
    """
    特定の課題に基づく評価項目のリストを取得する関数
    """
    evaluation_item_list = (
        db.query(models.EvaluationItems)
        .filter(
            models.EvaluationItems.lecture_id == lecture_id,
            models.EvaluationItems.assignment_id == assignment_id,
            models.EvaluationItems.for_evaluation == for_evaluation,
        )
        .all()
    )
    return [
        schemas.EvaluationItemRecord(**evaluation_item.__dict__)
        for evaluation_item in evaluation_item_list
    ]


def get_evaluation_item(
    db: Session, eval_id: str
) -> schemas.EvaluationItemRecord | None:
    """
    特定の評価項目のエントリを取得する関数
    """
    evaluation_item = (
        db.query(models.EvaluationItems)
        .filter(models.EvaluationItems.str_id == eval_id)
        .first()
    )
    return (
        schemas.EvaluationItemRecord(**evaluation_item.__dict__)
        if evaluation_item is not None
        else None
    )


def get_test_case_list(db: Session, eval_id: str) -> list[schemas.TestCaseRecord]:
    """
    特定の評価項目に基づくテストケースのリストを取得する関数
    """
    test_case_list = (
        db.query(models.TestCases).filter(models.TestCases.eval_id == eval_id).all()
    )
    return [
        schemas.TestCaseRecord(**test_case.__dict__) for test_case in test_case_list
    ]


def get_problem_recursive(
    db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool
) -> schemas.ProblemRecord:
    """
    特定の授業の特定の課題のエントリを取得する関数

    課題に紐づく評価項目リストと、評価項目に紐づくテストケースリストも合わせて取得する
    """
    problem = (
        db.query(models.Problem)
        .filter(
            models.Problem.lecture_id == lecture_id,
            models.Problem.assignment_id == assignment_id,
            models.Problem.for_evaluation == for_evaluation,
        )
        .first()
    )
    problem_record = schemas.ProblemRecord(**problem.__dict__)
    # problem_record.evaluation_item_listを取得する
    problem_record.evaluation_item_list = get_evaluation_item_list(
        db, lecture_id, assignment_id, for_evaluation
    )

    # evaluation_item_listの各eval_idに基づくtest_case_listを取得する
    for evaluation_item in problem_record.evaluation_item_list:
        evaluation_item.testcase_list = get_test_case_list(db, evaluation_item.str_id)
    return problem_record


def get_required_files(
    db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool
) -> list[str]:
    """
    特定の課題に基づく必要ファイルのリストを取得する関数
    """
    required_files = (
        db.query(models.RequiredFiles)
        .filter(
            models.RequiredFiles.lecture_id == lecture_id,
            models.RequiredFiles.assignment_id == assignment_id,
            models.RequiredFiles.for_evaluation == for_evaluation,
        )
        .all()
    )
    return [file.name for file in required_files]


def get_arranged_filepaths(
    db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool
) -> list[schemas.ArrangedFileRecord]:
    """
    特定の課題に基づく配置ファイルのリストを取得する関数
    """
    arranged_files = (
        db.query(models.ArrangedFiles)
        .filter(
            models.ArrangedFiles.lecture_id == lecture_id,
            models.ArrangedFiles.assignment_id == assignment_id,
            models.ArrangedFiles.for_evaluation == for_evaluation,
        )
        .all()
    )
    return [
        schemas.ArrangedFileRecord(**arranged_file.__dict__)
        for arranged_file in arranged_files
    ]


def register_submission(
    db: Session,
    batch_id: int | None,
    user_id: str,
    lecture_id: int,
    assignment_id: int,
    for_evaluation: bool,
) -> schemas.SubmissionRecord:
    """
    ジャッジリクエストをSubmissionテーブルに登録する関数
    """
    new_submission = models.Submission(
        batch_id=batch_id,
        user_id=user_id,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        for_evaluation=for_evaluation,
    )
    db.add(new_submission)
    db.commit()
    db.refresh(new_submission)
    return schemas.SubmissionRecord(**new_submission.__dict__)


def get_submission(db: Session, submission_id: int) -> schemas.SubmissionRecord | None:
    """
    特定の提出エントリを取得する関数
    """
    submission = (
        db.query(models.Submission)
        .filter(models.Submission.id == submission_id)
        .first()
    )
    return (
        schemas.SubmissionRecord(**submission.__dict__)
        if submission is not None
        else None
    )


def modify_submission(db: Session, submission_record: schemas.SubmissionRecord) -> None:
    """
    提出エントリを更新する関数
    """
    db.query(models.Submission).filter(
        models.Submission.id == submission_record.id
    ).update(submission_record.model_dump())
    db.commit()


def register_uploaded_file(db: Session, submission_id: int, path: Path) -> None:
    """
    アップロードされたファイルをUploadedFilesテーブルに登録する関数
    """
    new_uploadedfile = models.UploadedFiles(submission_id=submission_id, path=str(path))
    db.add(new_uploadedfile)
    db.commit()


def register_batch_submission(db: Session, user_id: str) -> schemas.BatchSubmissionRecord:
    """
    バッチ提出をBatchSubmissionテーブルに登録する関数
    """
    new_batch_submission = models.BatchSubmission(user_id=user_id)
    db.add(new_batch_submission)
    db.commit()
    db.refresh(new_batch_submission)
    return schemas.BatchSubmissionRecord(**new_batch_submission.__dict__)
