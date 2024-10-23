from app.classes import schemas
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, asc, desc
from ...classes import models
from typing import List, Literal, Tuple
from datetime import datetime
import pytz
from pathlib import Path
import logging


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
        problems=[
            schemas.Problem(
                lecture_id=problem.lecture_id,
                assignment_id=problem.assignment_id,
                title=problem.title,
                description_path=problem.description_path,
                timeMS=problem.timeMS,
                memoryMB=problem.memoryMB,
            )
            for problem in lecture.problems
        ]
    ) if lecture is not None else None


def get_problem(
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


def get_problem_detail_list(
    db: Session, lecture_id: int, eval: bool
) -> List[schemas.Problem]:
    """
    特定の授業の全ての課題のエントリを取得する関数
    
    採点リソースにアクセスするかどうかによって、フィルタリングする
    """
    problem_list = db.query(models.Problem).filter(models.Problem.lecture_id == lecture_id)
    
    problem_detail_list = []
    
    for problem in problem_list:
        problem_detail_list.append(get_problem(db=db, lecture_id=problem.lecture_id, assignment_id=problem.assignment_id, eval=eval, detail=True))

    return problem_detail_list


def register_submission(
    db: Session,
    evaluation_status_id: int,
    user_id: str,
    lecture_id: int,
    assignment_id: int,
    eval: bool,
) -> schemas.Submission:
    """
    ジャッジリクエストをSubmissionテーブルに登録する関数
    """
    new_submission = models.Submission(
        evaluation_status_id=evaluation_status_id,
        user_id=user_id,
        lecture_id=lecture_id,
        assignment_id=assignment_id,
        eval=eval,
    )
    db.add(new_submission)
    db.commit()
    db.refresh(new_submission)
    return schemas.Submission.model_validate(new_submission)


def get_submission(db: Session, submission_id: int, detail: bool = False) -> schemas.Submission | None:
    """
    特定の提出エントリを取得する関数
    
    detailがTrueの場合、ネスト情報も全て読み込む
    """
    submission = db.query(models.Submission).filter(models.Submission.id == submission_id).first()
    
    if submission is None:
        return None
    
    if detail:
        submission_record = schemas.Submission.model_validate(submission)
    else:
        submission_record = schemas.Submission(
            id=submission.id,
            ts=submission.ts,
            evaluation_status_id=submission.evaluation_status_id,
            user_id=submission.user_id,
            lecture_id=submission.lecture_id,
            assignment_id=submission.assignment_id,
            eval=submission.eval,
            progress=schemas.SubmissionProgressStatus(submission.progress),
            total_task=submission.total_task,
            completed_task=submission.completed_task,
            result=schemas.SubmissionSummaryStatus(submission.result) if submission.result is not None else None,
            message=submission.message,
            detail=submission.detail,
            score=submission.score,
            timeMS=submission.timeMS,
            memoryKB=submission.memoryKB,
        )
    
    return submission_record


def modify_submission(db: Session, submission: schemas.Submission) -> None:
    """
    提出エントリを更新する関数
    """
    db.query(models.Submission).filter(
        models.Submission.id == submission.id
    ).update(submission.model_dump(exclude={"uploaded_files", "judge_results", "problem"}))
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
    return schemas.BatchSubmission.model_validate(new_batch_submission)


def get_submission_list(
    db: Session, limit: int = 10, offset: int = 0, user_id: str | None = None, include_eval: bool = False
) -> List[schemas.Submission]:
    """
    全ての提出の進捗状況を取得する関数
    
    include_evalがTrueの場合、評価用の提出も含める
    include_evalがFalseの場合、評価用の提出は含めない(eval == Falseでフィルタリング)
    """
    # Submission
    submission_list = (
        db.query(models.Submission)
        .filter(
            or_(models.Submission.eval == False, include_eval == True),
            or_(user_id is None, models.Submission.user_id == user_id)
        )
        .order_by(models.Submission.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    
    submission_record_list = [
        schemas.Submission.model_validate(
            {
                **{key: getattr(submission, key) for key in submission.__table__.columns.keys()
                   if key not in {"problem", "uploaded_files", "judge_results"}
                }
            }
        )
        for submission in submission_list
    ]
    
    return submission_record_list


def get_batch_submission_status(
    db: Session, batch_id: int
) -> schemas.BatchSubmission | None:
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
    
    batch_submission_record = schemas.BatchSubmission.model_validate(
        {
            **{key: getattr(batch_submission, key) for key in batch_submission.__table__.columns.keys()
               if key not in {"evaluation_statuses"}
            }
        }
    )
    
    # 完了している場合、進捗状況の更新は不要
    if (batch_submission_record.complete_judge is not None 
        and batch_submission_record.total_judge is not None) and batch_submission_record.complete_judge == batch_submission_record.total_judge:
        return batch_submission_record
    
    # 進行中の場合、complete_judgeとtotal_judgeを更新する
    complete_judge = (
        db.query(models.BatchSubmission, models.EvaluationStatus, models.Submission)
        .join(
            models.EvaluationStatus,
            models.BatchSubmission.id == models.EvaluationStatus.batch_id
        )
        .join(
            models.Submission,
            models.EvaluationStatus.id == models.Submission.evaluation_status_id
        )
        .filter(
            models.BatchSubmission.id == batch_id,
            models.Submission.progress == schemas.SubmissionProgressStatus.DONE.value
        )
        .count()
    )
    
    total_judge = (
        db.query(models.BatchSubmission, models.EvaluationStatus, models.Submission)
        .join(
            models.EvaluationStatus,
            models.BatchSubmission.id == models.EvaluationStatus.batch_id
        )
        .join(
            models.Submission,
            models.EvaluationStatus.id == models.Submission.evaluation_status_id
        )
        .filter(
            models.BatchSubmission.id == batch_id
        )
        .count()
    )
    
    batch_submission_record.complete_judge = complete_judge
    batch_submission_record.total_judge = total_judge
    
    modify_batch_submission(db=db, batch_submission_record=batch_submission_record)
    return batch_submission_record


def get_batch_submission_detail(
    db: Session, batch_id: int
) -> schemas.BatchSubmission | None:
    """
    特定のバッチ採点の詳細を取得する関数
    
    詳細は、BatchSubmissionテーブルのレコードと、その中に紐づくEvaluationStatusテーブルのレコードと、その中に紐づくSubmissionテーブルのレコードを取得する
    Submissionレコードに紐づくJudgeResultテーブルのレコードは取得しない
    """
    batch_submission = (
        db.query(models.BatchSubmission)
        .filter(models.BatchSubmission.id == batch_id)
        .first()
    )
    
    if batch_submission is None:
        return None
    
    ret = schemas.BatchSubmission.model_validate(
        {
            **{key: getattr(batch_submission, key) for key in batch_submission.__table__.columns.keys()
               if key not in {"evaluation_statuses"}
            }
        }
    )
    
    for evaluation_status in batch_submission.evaluation_statuses:
        evaluation_status_record = schemas.EvaluationStatus.model_validate(
            {
                **{key: getattr(evaluation_status, key) for key in evaluation_status.__table__.columns.keys()
                   if key not in {"submissions", "batch_submission"}
                    }
            }
        )
        
        for submission in evaluation_status.submissions:
            submission_record = schemas.Submission.model_validate(
                {
                    **{key: getattr(submission, key) for key in submission.__table__.columns.keys()
                       if key not in {"problem", "uploaded_files", "judge_results"}
                    }
                }
            )
            evaluation_status_record.submissions.append(submission_record)
        
        ret.evaluation_statuses.append(evaluation_status_record)
    
    return ret


def get_batch_submission_list(
    db: Session,
    limit: int = 20,
    offset: int = 0,
    lecture_title: str | None = None,
    user: str | None = None,
    sort_by: Literal["ts", "user_id", "lecture_id"] = "ts",
    sort_order: Literal["asc", "desc"] = "desc"
) -> Tuple[List[schemas.BatchSubmission], int]:
    """
    全てのバッチ採点の進捗状況を取得する関数
    """
    query = db.query(models.BatchSubmission)
    # lecture_titleからlecture_idを取得
    if lecture_title:
        # lecture_titleの部分一致検索
        lecture_ids = db.query(models.Lecture.id).filter(models.Lecture.title.ilike(f"%{lecture_title}%")).all()
        if lecture_ids:
            query = query.filter(models.BatchSubmission.lecture_id.in_([id for (id,) in lecture_ids]))
        else:
            # 指定されているものの該当するlecture_titleが存在しない場合は空のリストを返す
            return [], 0

    if user:
        # userの部分一致検索（user_idまたはusername）
        user_ids = db.query(models.Users.user_id).filter(
            or_(
                models.Users.user_id.ilike(f"%{user}%"),
                models.Users.username.ilike(f"%{user}%")
            )
        ).all()
        if user_ids:
            query = query.filter(models.BatchSubmission.user_id.in_([id for (id,) in user_ids]))
        else:
            # 指定されているものの該当するuserが存在しない場合は空のリストを返す
            return [], 0

    
    # 総データ数を取得
    total_count = query.count()

    # ソート順を設定
    sort_column = getattr(models.BatchSubmission, sort_by)
    if sort_order == "desc":
        sort_column = desc(sort_column)
    else:
        sort_column = asc(sort_column)

    # ソートとページネーションを適用
    batch_submission_list = (
        query
        .order_by(sort_column)
        .limit(limit)
        .offset(offset)
        .all()
    )
    
    for batch_submission in batch_submission_list:
        if (batch_submission.complete_judge is None or batch_submission.total_judge is None) or batch_submission.complete_judge != batch_submission.total_judge:
            # complete_judgeとtotal_judgeを更新する
            complete_judge = (
                db.query(models.BatchSubmission, models.EvaluationStatus, models.Submission)
                .join(
                    models.EvaluationStatus,
                    models.BatchSubmission.id == models.EvaluationStatus.batch_id
                )
                .join(
                    models.Submission,
                    models.EvaluationStatus.id == models.Submission.evaluation_status_id
                )
                .filter(
                    models.BatchSubmission.id == batch_submission.id,
                    models.Submission.progress == schemas.SubmissionProgressStatus.DONE.value
                )
                .count()
            )
            
            total_judge = (
                db.query(models.BatchSubmission, models.EvaluationStatus, models.Submission)
                .join(
                    models.EvaluationStatus,
                    models.BatchSubmission.id == models.EvaluationStatus.batch_id
                )
                .join(
                    models.Submission,
                    models.EvaluationStatus.id == models.Submission.evaluation_status_id
                )
                .filter(
                    models.BatchSubmission.id == batch_submission.id
                )
                .count()
            )
            
            batch_submission_record = schemas.BatchSubmission.model_validate(
                {
                    **{key: getattr(batch_submission, key) for key in batch_submission.__table__.columns.keys()
                        if key not in {"evaluation_statuses"}
                    }
                }
            )
            
            batch_submission_record.complete_judge = complete_judge
            batch_submission_record.total_judge = total_judge
            modify_batch_submission(db=db, batch_submission_record=batch_submission_record)
        
    result = [
        schemas.BatchSubmission.model_validate(
            {
                **{key: getattr(batch_submission, key) for key in batch_submission.__table__.columns.keys()
                    if key not in {"evaluation_statuses"}
                }
            }
        )
        for batch_submission in batch_submission_list
    ]
    return result, total_count


def get_uploaded_files(
    db: Session, submission_id: int
) -> List[schemas.UploadedFiles]:
    """
    特定の提出エントリに紐づいたアップロードファイルのリストを取得する関数
    """
    uploaded_files = (
        db.query(models.UploadedFiles).filter(models.UploadedFiles.submission_id == submission_id).all()
    )
    return [schemas.UploadedFiles.model_validate(uploaded_file) for uploaded_file in uploaded_files]


def get_arranged_files(
    db: Session, lecture_id: int, assignment_id: int, eval: bool
) -> List[schemas.ArrangedFiles]:
    """
    特定の提出エントリに紐づいたアレンジされたファイルのリストを取得する関数
    """
    query = db.query(models.ArrangedFiles).filter(
        models.ArrangedFiles.lecture_id == lecture_id,
        models.ArrangedFiles.assignment_id == assignment_id
    )
    
    if eval:
        # eval=Trueの場合、evalがFalseまたはTrueのものを取得
        query = query.filter(or_(models.ArrangedFiles.eval == False, models.ArrangedFiles.eval == True))
    else:
        # eval=Falseの場合、evalがFalseのもののみ取得
        query = query.filter(models.ArrangedFiles.eval == False)
    
    arranged_files = query.all()
    return [schemas.ArrangedFiles.model_validate(arranged_file) for arranged_file in arranged_files]


def register_evaluation_status(
    db: Session, evaluation_status_record: schemas.EvaluationStatus
) -> schemas.EvaluationStatus:
    """
    バッチ採点のジャッジ結果をBatchSubmissionSummaryテーブルに登録する関数
    """
    # idは自動採番されるので、モデルに渡さない
    new_evaluation_status = models.EvaluationStatus(**evaluation_status_record.model_dump(exclude={"id", "batch_submission", "submissions"}))
    db.add(new_evaluation_status)
    db.commit()
    db.refresh(new_evaluation_status)
    return schemas.EvaluationStatus.model_validate(new_evaluation_status)


def update_evaluation_status(
    db: Session, evaluation_status_record: schemas.EvaluationStatus
) -> None:
    """
    バッチ採点のジャッジ結果をEvaluationStatusテーブルに更新する関数
    """
    db.query(models.EvaluationStatus).filter(
        models.EvaluationStatus.batch_id
        == evaluation_status_record.batch_id,
        models.EvaluationStatus.user_id
        == evaluation_status_record.user_id,
    ).update(evaluation_status_record.model_dump(exclude={"batch_submission", "submissions"}))
    db.commit()


def modify_batch_submission(
    db: Session, batch_submission_record: schemas.BatchSubmission
) -> None:
    """
    バッチ採点のジャッジ結果をBatchSubmissionテーブルに更新する関数
    """
    db.query(models.BatchSubmission).filter(
        models.BatchSubmission.id == batch_submission_record.id
    ).update(batch_submission_record.model_dump(exclude={"evaluation_statuses"}))
    db.commit()


def get_evaluation_status(
    db: Session, batch_id: int, user_id: str
) -> schemas.EvaluationStatus | None:
    """
    特定のバッチ採点の特定のユーザのジャッジ結果をBatchSubmissionSummaryテーブルに取得する関数
    """
    evaluation_status = (
        db.query(models.EvaluationStatus).filter(models.EvaluationStatus.batch_id == batch_id, models.EvaluationStatus.user_id == user_id).first()
    )
    return (
        schemas.EvaluationStatus.model_validate(
            {
                **{key: getattr(evaluation_status, key) for key in evaluation_status.__table__.columns.keys()
                   if key not in {"batch_submission", "submissions"}
                }
            }
        )
        if evaluation_status is not None
        else None
    )


def get_evaluation_status_detail(
    db: Session, batch_id: int, user_id: str
) -> schemas.EvaluationStatus | None:
    """
    特定のバッチ採点の特定のユーザのジャッジ結果をEvaluationStatusテーブルに取得する関数
    """
    evaluation_status = (
        db.query(models.EvaluationStatus)
        .filter(models.EvaluationStatus.batch_id == batch_id, models.EvaluationStatus.user_id == user_id)
        .first()
    )
    return schemas.EvaluationStatus.model_validate(evaluation_status) if evaluation_status is not None else None
