from sqlalchemy.ext.asyncio import AsyncSession

from app.ports.token_service import TokenPair
from app.core.security import verify_password
from app.auth.jwt_service import JwtTokenService
from app.crud.user_repository import UserRepository


class InvalidCredentialsError(Exception):
    """Raised for an unknown email or a wrong password.

    The router maps this to a single 401 message regardless of which case
    it was — do not let the distinction leak past this point.
    """


async def login(session: AsyncSession, email: str, password: str) -> TokenPair:
    user = await UserRepository(session).get_by_email(email)
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()

    pair = await JwtTokenService(session).create_token_pair(user.id, user.role)
    await session.commit()
    return pair
