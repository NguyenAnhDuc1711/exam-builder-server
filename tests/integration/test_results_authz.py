"""T020 / CRIT-2 — `GET /submissions/{id}` ownership enforcement (FR-7).

The single most important test file in this epic. A submission holds a
user's score and their per-question answers; the *only* thing standing
between that and another logged-in user is the "owner or admin" check in
`app.application.use_cases.get_results.get_submission`. These tests pin
down all four cases:

  owner        -> 200 + full breakdown
  other user   -> 403 and **zero** result data in the response body
  admin        -> 200 (the check must not lock admins out)
  unknown id   -> 404

Unexecuted (no Python/Docker in the authoring environment). Requires the
test database described in `tests/conftest.py`.
"""

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.submissions import router as submissions_router
from app.core.security import hash_password
from app.infrastructure.db.models.exam import Exam, ExamAssignment, ExamQuestion
from app.infrastructure.db.models.question import Option, Question
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import get_session


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


@pytest_asyncio.fixture
async def scenario(session, client):
    """User A owns a submission (2 of 2 correct). User B and an admin exist.

    Returns `(submission_id, answer_key)`.
    """
    user_a = User(
        email="a@example.com", password_hash=hash_password("apw"), role="user"
    )
    user_b = User(
        email="b@example.com", password_hash=hash_password("bpw"), role="user"
    )
    admin = User(
        email="admin@example.com",
        password_hash=hash_password("adminpw"),
        role="admin",
    )
    session.add_all([user_a, user_b, admin])
    await session.commit()

    questions = []
    for i in range(2):
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

    assignment = ExamAssignment(exam_id=exam.id, user_id=user_a.id)
    session.add(assignment)
    await session.commit()

    key = [(q.id, next(o.id for o in q.options if o.is_correct)) for q in questions]

    auth_a = await _token(client, "a@example.com", "apw")
    submitted = await client.post(
        f"/exams/{assignment.id}/submit",
        json={
            "answers": [
                {"question_id": q_id, "selected_option_id": right} for q_id, right in key
            ]
        },
        headers=auth_a,
    )
    assert submitted.status_code == 201
    assert submitted.json()["score"] == 2
    return submitted.json()["submission_id"], key


# --------------------------------------------------------------- the owner


async def test_owner_gets_their_own_score_and_breakdown(client, scenario):
    submission_id, key = scenario
    auth_a = await _token(client, "a@example.com", "apw")

    response = await client.get(f"/submissions/{submission_id}", headers=auth_a)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == submission_id
    assert body["score"] == 2
    assert body["total_questions"] == 2
    assert [(a["question_id"], a["is_correct"]) for a in body["answers"]] == [
        (key[0][0], True),
        (key[1][0], True),
    ]


# ----------------------------------------------------- CRIT-2: another user


async def test_user_b_cannot_read_user_a_submission(client, scenario):
    """CRIT-2. User B is authenticated, and not an admin, and not the owner.

    The response must be 403 **and must carry no result data at all** — not
    the score, not the answers, not even the question ids. We assert on the
    raw response text rather than on parsed fields, so a leak hidden
    anywhere in the payload (including inside `detail`) still fails the
    test.
    """
    submission_id, key = scenario
    auth_b = await _token(client, "b@example.com", "bpw")

    response = await client.get(f"/submissions/{submission_id}", headers=auth_b)

    assert response.status_code == 403

    raw = response.text
    assert "score" not in raw
    assert "is_correct" not in raw
    assert "answers" not in raw
    assert "breakdown" not in raw
    for question_id, correct_option_id in key:
        assert str(question_id) not in raw
        assert str(correct_option_id) not in raw

    # The parsed body is nothing but the error.
    assert response.json() == {"detail": "Forbidden"}


async def test_unauthenticated_request_is_401(client, scenario):
    submission_id, _key = scenario

    response = await client.get(f"/submissions/{submission_id}")

    assert response.status_code == 401
    assert "score" not in response.text


# ------------------------------------------------- CRIT-2 must not block admin


async def test_admin_can_read_any_users_submission(client, scenario):
    submission_id, key = scenario
    auth_admin = await _token(client, "admin@example.com", "adminpw")

    response = await client.get(f"/submissions/{submission_id}", headers=auth_admin)

    assert response.status_code == 200, "the ownership check must exempt admins"
    body = response.json()
    assert body["id"] == submission_id
    assert body["score"] == 2
    assert [a["question_id"] for a in body["answers"]] == [key[0][0], key[1][0]]


# --------------------------------------------------------------- unknown id


async def test_unknown_submission_id_is_404(client, scenario):
    auth_a = await _token(client, "a@example.com", "apw")

    response = await client.get("/submissions/999999", headers=auth_a)

    assert response.status_code == 404
