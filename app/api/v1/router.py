"""Mount config for every `/v1` router — prefix, tags, and router-level
auth gates all live here, in one place, instead of scattered across each
router module. Each router module itself only builds a bare
`router = APIRouter()` and defines routes with paths relative to the
prefix assigned below.
"""

from fastapi import APIRouter, Depends

from app.api.deps import require_role
from app.api.v1.routes import auth, exams, questions, submissions, users

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(
    questions.router,
    prefix="/questions",
    tags=["questions"],
    dependencies=[Depends(require_role("admin"))],
)
router.include_router(
    exams.router,
    prefix="/exams",
    tags=["exams"],
    dependencies=[Depends(require_role("admin"))],
)
# No prefix: its routes mix `/exams/{assignment_id}/submit` and
# `/submissions/{submission_id}`, and auth differs per route (see
# `submissions.py`), so there is no single router-level gate to add here.
router.include_router(submissions.router, tags=["submissions"])
