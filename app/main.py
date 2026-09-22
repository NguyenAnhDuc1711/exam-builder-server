from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import settings

app = FastAPI(title="Exam Builder API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mounted at the root (no `/api/v1` prefix): the epic's task specs pin the
# paths as `/auth/login`, `/users`, `/questions`, `/exams`. Each sub-router's
# own prefix/tags/dependencies are assigned in `app/api/v1/router.py`.
app.include_router(v1_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
