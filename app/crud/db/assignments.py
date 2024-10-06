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
    return [schemas.LectureRecord.model_validate(lecture) for lecture in lecture_list]


def get_lecture(db: Session, lecture_id: int) -> schemas.LectureRecord | None:
    """
    特定の回の授業エントリを取得する関数
    """
    lecture = db.query(models.Lecture).filter(models.Lecture.id == lecture_id).first()
    return (
        schemas.LectureRecord.model_validate(lecture) if lecture is not None else None
    )


def get_problem(
    db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool
) -> schemas.ProblemRecord | None:
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
    return (
        schemas.ProblemRecord.model_validate(problem) if problem is not None else None
    )


def get_problem_list(
    db: Session, lecture_id: int, for_evaluation: bool
) -> list[schemas.ProblemRecord]:
    """
    特定の授業に基づく問題のリストを取得する関数
    """
    problem_list = (
        db.query(models.Problem)
        .filter(
            models.Problem.lecture_id == lecture_id,
            models.Problem.for_evaluation == for_evaluation,
        )
        .all()
    )
    return [schemas.ProblemRecord.model_validate(problem) for problem in problem_list]


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
        schemas.EvaluationItemRecord.model_validate(evaluation_item)
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
        schemas.EvaluationItemRecord.model_validate(evaluation_item)
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
        schemas.TestCaseRecord.model_validate(test_case) for test_case in test_case_list
    ]


def get_problem_recursive(
    db: Session, lecture_id: int, assignment_id: int, for_evaluation: bool
) -> schemas.ProblemRecord | None:
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

    if problem is None:
        return None

    problem_record = schemas.ProblemRecord.model_validate(problem)
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


def get_arranged_files(
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
        schemas.ArrangedFileRecord.model_validate(arranged_file)
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
    return schemas.SubmissionRecord.model_validate(new_submission)


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
        schemas.SubmissionRecord.model_validate(submission)
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


def register_batch_submission(
    db: Session, user_id: str, lecture_id: int
) -> schemas.BatchSubmissionRecord:
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
