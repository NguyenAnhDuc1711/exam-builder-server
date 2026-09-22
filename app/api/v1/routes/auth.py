from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from redis.asyncio import Redis
import redis.exceptions as redis_exceptions
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.rate_limit import (
    ip_rate_limit,
    login_rate_limit,
    refresh_rate_limit,
)
from app.auth.jwt_service import JwtTokenService
from app.auth.otp_service import InvalidOtpError, InvalidResetTokenError
from app.core.database import get_session
from app.core.redis import get_redis
from app.ports.token_service import RotationError
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    ResetPasswordRequest,
    TokenPairResponse,
    VerifyOtpRequest,
    VerifyOtpResponse,
)
from app.services import password_reset
from app.services.login import InvalidCredentialsError
from app.services.login import login as login_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/login",
    response_model=TokenPairResponse,
    dependencies=[Depends(login_rate_limit)],
)
async def login(
    body: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPairResponse:
    try:
        pair = await login_service(session, body.email, body.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return TokenPairResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
    dependencies=[Depends(refresh_rate_limit)],
)
async def refresh(
    body: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPairResponse:
    try:
        pair = await JwtTokenService(session).rotate(body.refresh_token)
    except RotationError:
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await session.commit()
    return TokenPairResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[Depends(ip_rate_limit("auth"))],
)
async def forgot_password_endpoint(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> MessageResponse:
    email = body.email.strip().lower()
    try:
        await password_reset.forgot_password(
            session=session,
            redis=redis,
            background_tasks=background_tasks,
            email=email,
        )
    except redis_exceptions.RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable",
        )

    return MessageResponse(
        message="If the email is registered, a password reset code has been sent."
    )


@router.post(
    "/verify-otp",
    response_model=VerifyOtpResponse,
    dependencies=[Depends(ip_rate_limit("auth"))],
)
async def verify_otp_endpoint(
    body: VerifyOtpRequest,
    redis: Redis = Depends(get_redis),
) -> VerifyOtpResponse:
    # AD-7: Normalize email at route boundary
    email = body.email.strip().lower()
    try:
        token = await password_reset.verify_otp_step(
            redis=redis,
            email=email,
            code=body.code,
        )
    except InvalidOtpError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired OTP",
        )
    except redis_exceptions.RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable",
        )

    return VerifyOtpResponse(reset_token=token)


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(ip_rate_limit("auth"))],
)
async def reset_password_endpoint(
    body: ResetPasswordRequest,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> MessageResponse:
    try:
        await password_reset.reset_password_step(
            session=session,
            redis=redis,
            reset_token=body.reset_token,
            new_password=body.new_password,
        )
    except InvalidResetTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired reset token",
        )
    except redis_exceptions.RedisError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service unavailable",
        )

    return MessageResponse(message="Password reset successfully.")

