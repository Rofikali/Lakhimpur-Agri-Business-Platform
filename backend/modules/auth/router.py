from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_db_session, require_owner
from core.security import clear_auth_cookie, set_auth_cookie
from modules.auth.repository import AuthRepository
from modules.auth.schemas import LoginRequest, TokenResponse
from modules.auth.service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _svc(db: AsyncSession = Depends(get_db_session)) -> AuthService:
    return AuthService(repo=AuthRepository(db))


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    response: Response,
    service: AuthService = Depends(_svc),
):
    """Owner login. Sets httpOnly JWT cookie."""
    token, jti, data = await service.login(body)
    set_auth_cookie(response, token)
    return data


@router.post("/logout", status_code=200)
async def logout(
    response: Response,
    owner: dict = Depends(require_owner),
    service: AuthService = Depends(_svc),
):
    """Invalidate JWT and clear cookie."""
    jti = owner.get("jti", "")
    if jti:
        await service.logout(jti)
    clear_auth_cookie(response)
    return {"message": "logged out"}


@router.post("/refresh")
async def refresh(
    response: Response,
    owner: dict = Depends(require_owner),
    service: AuthService = Depends(_svc),
):
    """Silent token refresh. Called automatically 15 min before expiry."""
    token, jti, expires_at = await service.refresh(owner)
    set_auth_cookie(response, token)
    return {"expires_at": expires_at}
