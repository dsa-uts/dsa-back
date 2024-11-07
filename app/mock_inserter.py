# mock_data.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta
from app.classes.models import (
    Base, Lecture, Problem, Users, BatchSubmission, EvaluationStatus,
    Submission, JudgeResult, TestCases
)
from app.api.api_v1.endpoints import authenticate_util
from sqlalchemy.orm import Session

# データベースへの接続設定（必要に応じて修正してください）
DATABASE_URL = "mysql+pymysql://user:password@localhost:3306/dsa"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

# モックデータの追加
def add_mock_data(db: Session):
    print("start to insert mock data")
    try:
        # 1. ユーザーの追加
        users_data = [
            {
                "user_id": "manager1",
                "username": "Manager User",
                "email": "manager@example.com",
                "hashed_password": authenticate_util.get_password_hash("password123"),
                "role": "manager",
            },
            {
                "user_id": "student1",
                "username": "Student One",
                "email": "student1@example.com",
                "hashed_password": authenticate_util.get_password_hash("password123"),
                "role": "student",
            },
            {
                "user_id": "student2",
                "username": "Student Two",
                "email": "student2@example.com",
                "hashed_password": authenticate_util.get_password_hash("password123"),
                "role": "student",
            },
            {
                "user_id": "student3",
                "username": "Student Three",
                "email": "student3@example.com",
                "hashed_password": authenticate_util.get_password_hash("password123"),
                "role": "student",
            }
        ]

        for user_data in users_data:
            user = Users(
                **user_data,
                active_start_date=datetime.now() - timedelta(days=365),
                active_end_date=datetime.now() + timedelta(days=365)
            )
            db.add(user)
        db.commit()

        # 2. バッチ採点の追加
        batch_submission = BatchSubmission(
            user_id="manager1",
            lecture_id=1,  # init.sqlで追加された課題1を使用
            message="課題1のバッチ採点",
            complete_judge=6,  
            total_judge=6     
        )
        db.add(batch_submission)
        db.commit()

        # 3. EvaluationStatusの追加
        status_data = [
            {
                "user_id": "student1",
                "status": "submitted",
                "result": "AC",
                "submit_date": datetime.now() - timedelta(days=1)
            },
            {
                "user_id": "student2",
                "status": "delay",
                "result": "WA",
                "submit_date": datetime.now() - timedelta(hours=12)
            },
            {
                "user_id": "student3",
                "status": "non-submitted",
                "result": "TLE",
                "submit_date": None
            }
        ]

        for status in status_data:
            evaluation_status = EvaluationStatus(
                batch_id=batch_submission.id,
                user_id=status["user_id"],
                status=status["status"],
                result=status["result"],
                upload_dir=f"sample_submission/{status['user_id']}" if status["status"] != "non-submitted" else None,
                report_path=f"sample_submission/{status['user_id']}/report1.pdf" if status["status"] != "non-submitted" else None,
                submit_date=status["submit_date"]
            )
            db.add(evaluation_status)
            db.commit()
            
            if status["status"] != "non-submitted":
                # 基本課題と発展課題のSubmissionを追加
                for assignment_id in [1, 2]:
                    submission = Submission(
                        evaluation_status_id=evaluation_status.id,
                        user_id=status["user_id"],
                        lecture_id=1,
                        assignment_id=assignment_id,
                        eval=False,
                        upload_dir=f"sample_submission/{status['user_id']}",
                        progress="done",
                        total_task=7,
                        completed_task=7,
                        result=status["result"],
                        message="ジャッジが完了しました",
                        score=100 if status["result"] == "AC" else 60,
                        timeMS=500,
                        memoryKB=25600
                    )
                    db.add(submission)
                    db.commit()  # submissionのidを生成するためにcommit

                    # TestCasesのIDを取得
                    test_cases = db.query(TestCases).filter(
                        TestCases.lecture_id == 1,
                        TestCases.assignment_id == assignment_id
                    ).all()

                    # 各テストケースに対するJudgeResultを追加
                    for test_case in test_cases:
                        judge_result = JudgeResult(
                            submission_id=submission.id,
                            testcase_id=test_case.id,
                            result=status["result"],  # ACまたはWA
                            command=test_case.command,
                            timeMS=100,  # テストケースごとの実行時間
                            memoryKB=5120,  # テストケースごとの消費メモリ
                            exit_code=0 if status["result"] == "AC" else 1,
                            stdout="1\n" if status["result"] == "AC" else "0\n",
                            stderr="" if status["result"] == "AC" else "Error: wrong answer\n"
                        )
                        db.add(judge_result)                    

                db.commit()
        print("finish to insert mock data")

    except Exception as e:
        db.rollback()
        print(f"error occurred while inserting mock data: {e}")
        raise e

if __name__ == "__main__":
    add_mock_data(session)
