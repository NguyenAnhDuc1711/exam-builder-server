from fastapi import FastAPI

from app.api.v1.routers import auth, questions, users

app = FastAPI(title="Exam Builder API")

# Routers are mounted at the root (no `/api/v1` prefix): the epic's task
# specs pin the paths as `/auth/login`, `/users`, `/questions`, `/exams`.
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(questions.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
