from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.middleware import MaxBodySizeMiddleware
from app.core.redis import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await redis_client.aclose()


app = FastAPI(title="Exam Builder API", lifespan=lifespan)

app.add_middleware(MaxBodySizeMiddleware, max_body_size=settings.MAX_REQUEST_BODY_BYTES)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
