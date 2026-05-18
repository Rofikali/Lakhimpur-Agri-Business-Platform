from datetime import datetime, timezone, timedelta
from modules.auth.repository import AuthRepository
from modules.auth.schemas import LoginRequest, TokenResponse
from core.security import verify_password, create_access_token
from core.redis import blocklist_token
from core.config import settings
from shared.exceptions import InvalidCredentialsError


class AuthService:
    def __init__(self, repo: AuthRepository):
        self.repo = repo

    async def login(self, data: LoginRequest) -> tuple[str, str, TokenResponse]:
        """Verify credentials → issue JWT. Returns (token, jti, response)."""
        owner = await self.repo.find_by_username(data.username)

        # Use same error for wrong username AND wrong password
        # Prevents username enumeration
        if not owner or not verify_password(data.password, owner.password_hash):
            raise InvalidCredentialsError()

        token, jti = create_access_token(str(owner.id))
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS)

        return (
            token,
            jti,
            TokenResponse(
                owner_id=str(owner.id),
                username=owner.username,
                expires_at=expires_at,
            ),
        )

    async def logout(self, jti: str) -> None:
        """Add token jti to Redis blocklist so it can't be reused."""
        ttl = settings.JWT_EXPIRY_HOURS * 3600
        await blocklist_token(jti, ttl_secs=ttl)

    async def refresh(self, current_payload: dict) -> tuple[str, str, datetime]:
        """Issue a fresh token for the same owner."""
        token, jti = create_access_token(current_payload["sub"])
        expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS)
        return token, jti, expires_at
