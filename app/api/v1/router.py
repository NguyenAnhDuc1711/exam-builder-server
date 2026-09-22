from fastapi import APIRouter

from app.api.v1.routes import auth, exams, questions, submissions, users

router = APIRouter()

router.include_router(auth.router)
router.include_router(users.router)
router.include_router(questions.router)
router.include_router(exams.router)
router.include_router(submissions.router)
