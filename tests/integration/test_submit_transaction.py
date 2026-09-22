"""T020 — `POST /exams/{assignment_id}/submit` (FR-6).

Covers the happy path, **CRIT-1** (Submission + Answer inserts are one
transaction: a failure part-way through leaves *nothing* behind) and
**WARN-2** (a second submit is a clean 409, not a 500).

Unexecuted (no Python/Docker in the authoring environment). Requires the
test database described in `tests/conftest.py`. Same ASGI-through-httpx
pattern as `tests/integration/test_exam_assignment.py`.
"""

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.submissions import router as submissions_router
from app.core.security import hash_password
from app.models.exam import Exam, ExamAssignment, ExamQuestion
from app.models.question import Option, Question
from app.models.submission import Answer, Submission
from app.models.user import User
from app.core.database import get_session


@pytest_asyncio.fixture
async def client(session):
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(submissions_router)
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


async def _token(client, email: str, password: str) -> dict:
    response = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _seed(session):
    """3-question exam assigned to `learner@example.com`.

    Returns `(assignment_id, [(question_id, correct_option_id,
    wrong_option_id), ...])` in exam order.
    """
    learner = User(
        email="learner@example.com",
        password_hash=hash_password("userpw"),
        role="user",
    )
    session.add(learner)
    await session.commit()

    questions = []
    for i in range(3):
        question = Question(text=f"Q{i}")
        question.options = [
            Option(text="right", is_correct=True),
            Option(text="wrong", is_correct=False),
        ]
        session.add(question)
        questions.append(question)
    await session.commit()

    exam = Exam(title="Exam")
    exam.exam_questions = [
        ExamQuestion(question_id=q.id, order=i) for i, q in enumerate(questions)
    ]
    session.add(exam)
    await session.commit()

    assignment = ExamAssignment(exam_id=exam.id, user_id=learner.id)
    session.add(assignment)
    await session.commit()

    key = [
        (
            q.id,
            next(o.id for o in q.options if o.is_correct),
            next(o.id for o in q.options if not o.is_correct),
        )
        for q in questions
    ]
    return assignment.id, key


# ------------------------------------------------------------- happy path


async def test_submit_grades_and_returns_breakdown(session, client):
    assignment_id, key = await _seed(session)
    auth = await _token(client, "learner@example.com", "userpw")

    # Two right, one wrong.
    response = await client.post(
        f"/exams/{assignment_id}/submit",
        json={
            "answers": [
                {"question_id": key[0][0], "selected_option_id": key[0][1]},
                {"question_id": key[1][0], "selected_option_id": key[1][2]},
                {"question_id": key[2][0], "selected_option_id": key[2][1]},
            ]
        },
        headers=auth,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["score"] == 2
    assert body["total_questions"] == 3
    assert [(b["question_id"], b["is_correct"]) for b in body["breakdown"]] == [
        (key[0][0], True),
        (key[1][0], False),
        (key[2][0], True),
    ]

    # ...and it was actually persisted, score included.
    submission = (
        await session.execute(select(Submission).where(Submission.id == body["submission_id"]))
    ).scalar_one()
    assert submission.score == 2
    answer_count = (
        await session.execute(
            select(func.count())
            .select_from(Answer)
            .where(Answer.submission_id == submission.id)
        )
    ).scalar_one()
    assert answer_count == 3


async def test_submitting_someone_elses_assignment_returns_403(session, client):
    assignment_id, key = await _seed(session)
    session.add(
        User(
            email="other@example.com",
            password_hash=hash_password("otherpw"),
            role="user",
        )
    )
    await session.commit()
    auth = await _token(client, "other@example.com", "otherpw")

    response = await client.post(
        f"/exams/{assignment_id}/submit",
        json={"answers": [{"question_id": key[0][0], "selected_option_id": key[0][1]}]},
        headers=auth,
    )

    assert response.status_code == 403
    # Nothing was written on a rejected submit.
    assert (
        await session.execute(select(func.count()).select_from(Submission))
    ).scalar_one() == 0


async def test_option_from_another_question_is_400_not_409(session, client):
    """A bogus `selected_option_id` must not masquerade as a duplicate submit.

    It is an FK to `option.id`, so without the up-front check it would blow
    up as an `IntegrityError` inside the write transaction and be reported
    as WARN-2's 409 "Exam already submitted" — for an exam that was never
    submitted.
    """
    assignment_id, key = await _seed(session)
    auth = await _token(client, "learner@example.com", "userpw")

    response = await client.post(
        f"/exams/{assignment_id}/submit",
        json={
            "answers": [
                # Question 0 answered with question 1's option.
                {"question_id": key[0][0], "selected_option_id": key[1][1]}
            ]
        },
        headers=auth,
    )

    assert response.status_code == 400
    assert (
        await session.execute(select(func.count()).select_from(Submission))
    ).scalar_one() == 0


# ------------------------------------------------------------------ CRIT-1


async def test_failure_between_answer_inserts_rolls_back_everything(
    session, client, db_engine, monkeypatch
):
    """CRIT-1: no orphan `Submission` may survive a mid-write failure.

    Injection technique: `submit_exam` writes by calling `session.add`
    exactly once for the `Submission` and once per `Answer`, in that order.
    We replace `session.add` on the *instance* with a counting wrapper that
    raises on the **3rd** call — i.e. after the `Submission` has been added
    *and flushed* (its INSERT has really been sent to Postgres, and
    `submission.id` allocated) and after the first `Answer` has been added,
    but before the remaining answers. That is precisely the "half-written"
    moment CRIT-1 is about.

    The `async with session.begin():` block must then roll the whole
    transaction back, so a *separate* connection must see zero submissions
    and zero answers afterwards.
    """
    assignment_id, key = await _seed(session)
    auth = await _token(client, "learner@example.com", "userpw")

    original_add = session.add
    calls = {"n": 0}

    def failing_add(instance, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:  # Submission, Answer#1, -> boom on Answer#2
            raise RuntimeError("injected failure mid-Answer-insert")
        return original_add(instance, *args, **kwargs)

    monkeypatch.setattr(session, "add", failing_add)

    # Starlette's ServerErrorMiddleware re-raises unhandled exceptions, so
    # the injected error surfaces here rather than as a 500 body.
    with pytest.raises(RuntimeError, match="injected failure"):
        await client.post(
            f"/exams/{assignment_id}/submit",
            json={
                "answers": [
                    {"question_id": q_id, "selected_option_id": right}
                    for q_id, right, _wrong in key
                ]
            },
            headers=auth,
        )

    assert calls["n"] == 3, "the failure must land mid-write, not before it"

    monkeypatch.undo()

    # Verify from a brand-new session/connection: nothing the request wrote
    # may have survived — not the Submission, not the one Answer that made
    # it in before the failure.
    verifier = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with verifier() as check:
        submissions = (
            await check.execute(select(func.count()).select_from(Submission))
        ).scalar_one()
        answers = (
            await check.execute(select(func.count()).select_from(Answer))
        ).scalar_one()

    assert submissions == 0, "orphan Submission survived a rolled-back write"
    assert answers == 0

    # And the rollback must be complete enough that the assignment is still
    # submittable: a leftover row would make this retry collide with the
    # unique constraint and come back 409 instead of 201.
    retry = await client.post(
        f"/exams/{assignment_id}/submit",
        json={
            "answers": [
                {"question_id": q_id, "selected_option_id": right}
                for q_id, right, _wrong in key
            ]
        },
        headers=auth,
    )
    assert retry.status_code == 201
    assert retry.json()["score"] == 3


# ------------------------------------------------------------------ WARN-2


async def test_double_submit_returns_409_not_500(session, client):
    assignment_id, key = await _seed(session)
    auth = await _token(client, "learner@example.com", "userpw")
    payload = {
        "answers": [
            {"question_id": q_id, "selected_option_id": right}
            for q_id, right, _wrong in key
        ]
    }

    first = await client.post(
        f"/exams/{assignment_id}/submit", json=payload, headers=auth
    )
    assert first.status_code == 201

    second = await client.post(
        f"/exams/{assignment_id}/submit", json=payload, headers=auth
    )

    assert second.status_code == 409, "a repeat submit must not be a raw 500"
    assert second.json()["detail"] == "Exam already submitted"

    # The first submission is intact and there is still exactly one.
    assert (
        await session.execute(select(func.count()).select_from(Submission))
    ).scalar_one() == 1
