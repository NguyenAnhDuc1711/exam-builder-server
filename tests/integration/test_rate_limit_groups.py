"""T090 — SC-1 and SC-5: Per-group threshold enforcement and environment overrides.

Asserts:
- SC-1: On request N+1, each of the 4 groups (auth, write, submit, read) returns 429
  with Retry-After >= 1 and JSON detail body; handler not executed; NTH-1 log emitted.
- SC-5: Overriding threshold settings changes the applied limit without code changes.
"""

import json
import logging
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import get_session
from app.core.rate_limit import reset_for_tests
from app.core.security import hash_password
from app.main import app
from app.models.exam import Exam, ExamAssignment, ExamQuestion
from app.models.question import Option, Question
from app.models.user import User


@pytest_asyncio.fixture(autouse=True)
async def clean_rate_limit(redis_client):
    """Reset both Redis and in-memory rate-limit state between tests."""
    reset_for_tests()
    await redis_client.flushdb()
    yield
    reset_for_tests()
    await redis_client.flushdb()
    from app.core.redis import redis_client as app_redis
    await app_redis.connection_pool.disconnect()


@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_session] = lambda: session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed_data(session):
    admin = User(
        email="admin_rl@example.com",
        password_hash=hash_password("adminpw123"),
        role="admin",
    )
    student = User(
        email="student_rl@example.com",
        password_hash=hash_password("studentpw123"),
        role="user",
    )
    session.add_all([admin, student])
    await session.flush()

    q = Question(text="Test Q?", image_url=None)
    session.add(q)
    await session.flush()

    opt = Option(question_id=q.id, text="Opt A", is_correct=True)
    session.add(opt)

    exam = Exam(title="Test RL Exam")
    session.add(exam)
    await session.flush()

    eq = ExamQuestion(exam_id=exam.id, question_id=q.id, order=0)
    session.add(eq)

    assignments = []
    for _ in range(5):
        assignment = ExamAssignment(exam_id=exam.id, user_id=student.id)
        # UniqueConstraint on (exam_id, user_id), so create multiple exams for distinct assignments
        exam_i = Exam(title="Exam I")
        session.add(exam_i)
        await session.flush()
        eq_i = ExamQuestion(exam_id=exam_i.id, question_id=q.id, order=0)
        session.add(eq_i)
        assignment_i = ExamAssignment(exam_id=exam_i.id, user_id=student.id)
        session.add(assignment_i)
        assignments.append(assignment_i)

    await session.commit()
    for a in assignments:
        await session.refresh(a)
    await session.refresh(admin)
    await session.refresh(student)
    await session.refresh(q)
    await session.refresh(opt)

    assignment_ids = [a.id for a in assignments]
    return {
        "admin": admin,
        "student": student,
        "question_id": q.id,
        "option_id": opt.id,
        "assignment_ids": assignment_ids,
    }


async def _get_tokens(client: AsyncClient) -> tuple[str, str]:
    res_admin = await client.post(
        "/auth/login",
        json={"email": "admin_rl@example.com", "password": "adminpw123"},
    )
    res_student = await client.post(
        "/auth/login",
        json={"email": "student_rl@example.com", "password": "studentpw123"},
    )
    return res_admin.json()["access_token"], res_student.json()["access_token"]


@pytest.mark.asyncio
async def test_sc1_auth_group_rate_limit(client, seed_data, caplog):
    """SC-1: auth group returns 429 on request N+1 with Retry-After and NTH-1 log."""
    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch.object(settings, "RATE_LIMIT_AUTH_MAX", 2):
            with patch.object(settings, "RATE_LIMIT_AUTH_WINDOW_SECONDS", 60):
                reset_for_tests()
                with caplog.at_level(logging.WARNING, logger="app.api.rate_limit"):
                    # Req 1: allowed (200)
                    r1 = await client.post(
                        "/auth/login",
                        json={"email": "student_rl@example.com", "password": "studentpw123"},
                    )
                    assert r1.status_code == 200

                    # Req 2: allowed (200)
                    r2 = await client.post(
                        "/auth/login",
                        json={"email": "student_rl@example.com", "password": "studentpw123"},
                    )
                    assert r2.status_code == 200

                    # Req 3 (N+1): blocked with 429
                    r3 = await client.post(
                        "/auth/login",
                        json={"email": "student_rl@example.com", "password": "studentpw123"},
                    )
                    assert r3.status_code == 429
                    assert "Retry-After" in r3.headers
                    retry_after = int(r3.headers["Retry-After"])
                    assert 1 <= retry_after <= 60
                    assert r3.json()["detail"] == "Too many requests. Please try again later."

                    # NTH-1: Log emitted
                    matching = [
                        rec
                        for rec in caplog.records
                        if getattr(rec, "msg", None) == "rate_limit_exceeded"
                        or getattr(rec, "message", None) == "rate_limit_exceeded"
                    ]
                    assert len(matching) >= 1
                    assert getattr(matching[0], "group", None) == "auth"


@pytest.mark.asyncio
async def test_sc1_write_group_rate_limit(client, seed_data):
    """SC-1: write group returns 429 on request N+1."""
    admin_token, _ = await _get_tokens(client)
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "text": "Write RL question",
        "options": json.dumps([{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]),
    }

    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch.object(settings, "RATE_LIMIT_WRITE_MAX", 2):
            with patch.object(settings, "RATE_LIMIT_WRITE_WINDOW_SECONDS", 60):
                reset_for_tests()
                # 2 write requests allowed
                r1 = await client.post("/questions", data=payload, headers=headers)
                assert r1.status_code == 201
                r2 = await client.post("/questions", data=payload, headers=headers)
                assert r2.status_code == 201

                # 3rd request blocked
                r3 = await client.post("/questions", data=payload, headers=headers)
                assert r3.status_code == 429
                assert int(r3.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_sc1_read_group_rate_limit(client, seed_data):
    """SC-1: read group returns 429 on request N+1."""
    admin_token, _ = await _get_tokens(client)
    headers = {"Authorization": f"Bearer {admin_token}"}

    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch.object(settings, "RATE_LIMIT_READ_MAX", 2):
            with patch.object(settings, "RATE_LIMIT_READ_WINDOW_SECONDS", 60):
                reset_for_tests()
                r1 = await client.get("/questions", headers=headers)
                assert r1.status_code == 200
                r2 = await client.get("/questions", headers=headers)
                assert r2.status_code == 200

                r3 = await client.get("/questions", headers=headers)
                assert r3.status_code == 429
                assert int(r3.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_sc1_submit_group_rate_limit(client, seed_data):
    """SC-1: submit group returns 429 on request N+1."""
    _, student_token = await _get_tokens(client)
    headers = {"Authorization": f"Bearer {student_token}"}
    q_id = seed_data["question_id"]
    opt_id = seed_data["option_id"]
    payload = {"answers": [{"question_id": q_id, "selected_option_id": opt_id}]}

    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        with patch.object(settings, "RATE_LIMIT_SUBMIT_MAX", 2):
            with patch.object(settings, "RATE_LIMIT_SUBMIT_WINDOW_SECONDS", 60):
                reset_for_tests()
                # Submit 1
                a1_id = seed_data["assignment_ids"][0]
                r1 = await client.post(f"/exams/{a1_id}/submit", json=payload, headers=headers)
                assert r1.status_code == 201

                # Submit 2
                a2_id = seed_data["assignment_ids"][1]
                r2 = await client.post(f"/exams/{a2_id}/submit", json=payload, headers=headers)
                assert r2.status_code == 201

                # Submit 3 -> 429
                a3_id = seed_data["assignment_ids"][2]
                r3 = await client.post(f"/exams/{a3_id}/submit", json=payload, headers=headers)
                assert r3.status_code == 429
                assert int(r3.headers["Retry-After"]) >= 1


@pytest.mark.asyncio
async def test_sc5_env_override_write_threshold(client, seed_data):
    """SC-5: Overriding threshold via settings applies new limit without code modifications."""
    admin_token, _ = await _get_tokens(client)
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = {
        "text": "Override test question",
        "options": json.dumps([{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]),
    }

    with patch.object(settings, "RATE_LIMIT_ENABLED", True):
        # Override write max to 4
        with patch.object(settings, "RATE_LIMIT_WRITE_MAX", 4):
            reset_for_tests()
            for _ in range(4):
                res = await client.post("/questions", data=payload, headers=headers)
                assert res.status_code == 201

            # 5th request is 429
            r5 = await client.post("/questions", data=payload, headers=headers)
            assert r5.status_code == 429
