from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables (and `.env`
    for local development). Required fields have no defaults on purpose:
    a missing variable should fail fast at startup, not surface as an
    obscure error later at request time.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ACCESS_EXPIRE_MINUTES: int = 1440
    JWT_REFRESH_EXPIRE_DAYS: int = 7
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str
    CORS_ORIGINS: str

    # Redis (forgot-password-otp — T001)
    REDIS_URL: str

    # SMTP (forgot-password-otp — T001)
    SMTP_HOST: str
    SMTP_PORT: int
    SMTP_USERNAME: str
    SMTP_PASSWORD: str
    SMTP_FROM_ADDRESS: str

    # Rate limiting (api-rate-limiting epic)
    RATE_LIMIT_ENABLED: bool = True

    # Per-group thresholds & windows (defaults from FR-1)
    RATE_LIMIT_AUTH_MAX: int = 5
    RATE_LIMIT_AUTH_WINDOW_SECONDS: int = 60

    RATE_LIMIT_WRITE_MAX: int = 30
    RATE_LIMIT_WRITE_WINDOW_SECONDS: int = 60

    RATE_LIMIT_SUBMIT_MAX: int = 10
    RATE_LIMIT_SUBMIT_WINDOW_SECONDS: int = 60

    RATE_LIMIT_READ_MAX: int = 100
    RATE_LIMIT_READ_WINDOW_SECONDS: int = 60

    # Degraded mode & circuit breaker (AD-4, AD-5)
    RATE_LIMIT_REDIS_TIMEOUT_MS: int = 50
    RATE_LIMIT_BREAKER_COOLDOWN_SECONDS: int = 5

    # Hard cap on request body size (defense against oversized uploads).
    # 6MB = the 5MB image cap (`create_question.MAX_IMAGE_SIZE_BYTES`) plus
    # headroom for multipart framing and the other form fields.
    MAX_REQUEST_BODY_BYTES: int = 6 * 1024 * 1024



settings = Settings()
