"""T090 — end-to-end happy path across the whole epic (SC-1).

Drives the **real** app (`app.main.app`, all 5 routers wired exactly as in
production) through the full business flow, each step consuming the
previous step's response the way a real client would:

    seed first admin (direct DB insert — there is no public sign-up and no
    seed script anywhere in the repo; see the verification report)
      -> admin login                                   (FR-1)
      -> admin creates a user                           (FR-2)
      -> admin creates questions, one with an image      (FR-3, NFR-2)
      -> admin assembles an exam from those questions    (FR-4)
      -> admin assigns the exam to the user               (FR-5)
      -> user logs in                                    (FR-1)
      -> user submits answers                            (FR-6)
      -> user reads their own result                     (FR-7)
      -> admin reads the same result via the exam listing (FR-7)

Unexecuted (no Python/Docker in the authoring environment) — see
`.sdd/epics/exam-builder-base/verification-report.md`. Same
ASGI-through-httpx pattern as every other integration test in this suite
(`tests/integration/test_auth_rotation.py` in particular, which is also the
only other file driving `app.main.app` directly instead of a throwaway
per-feature router subset).
"""

import json
from unittest.mock import AsyncMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.api.v1.routes.questions import get_image_storage
from app.ports.image_storage import ImageStoragePort
from app.core.security import hash_password
from app.models.user import User
from app.core.database import get_session
from app.main import app as main_app

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"


@pytest_asyncio.fixture
async def image_storage_mock():
    mock = AsyncMock(spec=ImageStoragePort)
    mock.upload.return_value = "https://cloudinary.example/e2e.png"
    return mock


@pytest_asyncio.fixture
async def client(session, image_storage_mock):
    main_app.dependency_overrides[get_session] = lambda: session
    main_app.dependency_overrides[get_image_storage] = lambda: image_storage_mock
    async with AsyncClient(
        transport=ASGITransport(app=main_app), base_url="http://test"
    ) as c:
        yield c
    main_app.dependency_overrides.clear()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _login(client, email: str, password: str) -> str:
    response = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def test_full_happy_path_create_to_result(session, client):
    # ---- 0. bootstrap the first admin directly (no public sign-up exists;
    # this mirrors how every other integration test in the suite seeds its
    # first admin, and stands in for a real deploy's manual first-admin step).
    session.add(
        User(
            email="admin@example.com",
            password_hash=hash_password("adminpw"),
            role="admin",
        )
    )
    await session.commit()

    # ---- 1. admin login (FR-1)
    admin_token = await _login(client, "admin@example.com", "adminpw")

    # ---- 2. admin creates a user (FR-2)
    create_user_resp = await client.post(
        "/users",
        json={"email": "learner@example.com", "password": "learnerpw"},
        headers=_auth(admin_token),
    )
    assert create_user_resp.status_code == 201, create_user_resp.text
    user_id = create_user_resp.json()["id"]

    # ---- 3. admin creates questions, one carrying an image (FR-3, NFR-2)
    q1_resp = await client.post(
        "/questions",
        data={
            "text": "2 + 2 = ?",
            "options": json.dumps(
                [
                    {"text": "3", "is_correct": False},
                    {"text": "4", "is_correct": True},
                ]
            ),
        },
        files={"image": ("q1.png", _PNG_BYTES, "image/png")},
        headers=_auth(admin_token),
    )
    assert q1_resp.status_code == 201, q1_resp.text
    assert q1_resp.json()["image_url"] == "https://cloudinary.example/e2e.png"
    assert q1_resp.json()["image_upload_warning"] is None
    q1_id = q1_resp.json()["id"]
    q1_correct_option_id = next(
        o["id"] for o in q1_resp.json()["options"] if o["is_correct"]
    )
    q1_wrong_option_id = next(
        o["id"] for o in q1_resp.json()["options"] if not o["is_correct"]
    )

    q2_resp = await client.post(
        "/questions",
        data={
            "text": "The sky is blue.",
            "options": json.dumps(
                [
                    {"text": "True", "is_correct": True},
                    {"text": "False", "is_correct": False},
                ]
            ),
        },
        headers=_auth(admin_token),
    )
    assert q2_resp.status_code == 201, q2_resp.text
    q2_id = q2_resp.json()["id"]
    q2_correct_option_id = next(
        o["id"] for o in q2_resp.json()["options"] if o["is_correct"]
    )

    # ---- 4. admin assembles an exam from those questions, in order (FR-4)
    create_exam_resp = await client.post(
        "/exams",
        json={"title": "Sample Exam", "question_ids": [q1_id, q2_id]},
        headers=_auth(admin_token),
    )
    assert create_exam_resp.status_code == 201, create_exam_resp.text
    exam_id = create_exam_resp.json()["id"]
    assert [
        eq["question_id"] for eq in create_exam_resp.json()["exam_questions"]
    ] == [q1_id, q2_id]

    # ---- 5. admin assigns the exam to the user (FR-5)
    assign_resp = await client.post(
        f"/exams/{exam_id}/assign",
        json={"user_id": user_id},
        headers=_auth(admin_token),
    )
    assert assign_resp.status_code == 201, assign_resp.text
    assignment_id = assign_resp.json()["id"]

    # ---- 6. the user logs in (FR-1)
    user_token = await _login(client, "learner@example.com", "learnerpw")

    # ---- 7. the user submits answers: one right, one wrong (FR-6)
    submit_resp = await client.post(
        f"/exams/{assignment_id}/submit",
        json={
            "answers": [
                {"question_id": q1_id, "selected_option_id": q1_wrong_option_id},
                {"question_id": q2_id, "selected_option_id": q2_correct_option_id},
            ]
        },
        headers=_auth(user_token),
    )
    assert submit_resp.status_code == 201, submit_resp.text
    submit_body = submit_resp.json()
    submission_id = submit_body["submission_id"]
    assert submit_body["score"] == 1
    assert submit_body["total_questions"] == 2
    assert [
        (b["question_id"], b["is_correct"]) for b in submit_body["breakdown"]
    ] == [(q1_id, False), (q2_id, True)]

    # A repeat submission of the same assignment must not silently re-score
    # (single-attempt, FR-6) — it is a 409, not a second Submission row.
    duplicate_resp = await client.post(
        f"/exams/{assignment_id}/submit",
        json={
            "answers": [
                {"question_id": q1_id, "selected_option_id": q1_correct_option_id},
                {"question_id": q2_id, "selected_option_id": q2_correct_option_id},
            ]
        },
        headers=_auth(user_token),
    )
    assert duplicate_resp.status_code == 409

    # ---- 8. the user reads their own result (FR-7)
    own_result_resp = await client.get(
        f"/submissions/{submission_id}", headers=_auth(user_token)
    )
    assert own_result_resp.status_code == 200, own_result_resp.text
    own_body = own_result_resp.json()
    assert own_body["score"] == 1
    assert own_body["total_questions"] == 2
    assert [(a["question_id"], a["is_correct"]) for a in own_body["answers"]] == [
        (q1_id, False),
        (q2_id, True),
    ]

    # ---- 9. the admin reads the same result via the exam's submission list
    # (FR-7), and it must agree exactly with what the user saw.
    admin_list_resp = await client.get(
        f"/exams/{exam_id}/submissions", headers=_auth(admin_token)
    )
    assert admin_list_resp.status_code == 200, admin_list_resp.text
    admin_rows = admin_list_resp.json()
    assert len(admin_rows) == 1
    admin_row = admin_rows[0]
    assert admin_row["id"] == submission_id
    assert admin_row["user_id"] == user_id
    assert admin_row["score"] == own_body["score"] == 1
    assert [
        (a["question_id"], a["is_correct"]) for a in admin_row["answers"]
    ] == [(q1_id, False), (q2_id, True)]

    # ---- 10. cross-check: a non-owning, non-admin caller must not see it
    # (CRIT-2) — reuses the account created in step 2's sibling: create one
    # more plain user and confirm they are locked out of both the direct
    # read and the admin-only listing.
    session.add(
        User(
            email="other@example.com",
            password_hash=hash_password("otherpw"),
            role="user",
        )
    )
    await session.commit()
    other_token = await _login(client, "other@example.com", "otherpw")

    forbidden_resp = await client.get(
        f"/submissions/{submission_id}", headers=_auth(other_token)
    )
    assert forbidden_resp.status_code == 403
    assert forbidden_resp.json() == {"detail": "Forbidden"}

    forbidden_list_resp = await client.get(
        f"/exams/{exam_id}/submissions", headers=_auth(other_token)
    )
    assert forbidden_list_resp.status_code == 403
