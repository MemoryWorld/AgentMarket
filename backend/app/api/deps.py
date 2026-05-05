from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, sha256_text, utcnow
from app.db.session import get_session
from app.models import PersonalAccessToken, User


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthActor:
    user: User
    scopes: set[str]
    token_type: str


async def get_current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> AuthActor:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token.")

    token = credentials.credentials
    if token.startswith("pat_"):
        pat = await session.scalar(select(PersonalAccessToken).where(PersonalAccessToken.token_hash == sha256_text(token)))
        if not pat or pat.revoked:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid personal access token.")
        pat.last_used_at = utcnow()
        user = await session.get(User, pat.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token user no longer exists.")
        await session.commit()
        return AuthActor(user=user, scopes=set(pat.scopes or []), token_type="pat")

    payload = decode_access_token(token)
    user = await session.get(User, payload["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    default_scopes = {"listings:write", "orders:write", "ai:generate"}
    return AuthActor(user=user, scopes=default_scopes, token_type="access")


def require_scopes(*required_scopes: str) -> Callable[[AuthActor], AuthActor]:
    async def dependency(actor: AuthActor = Depends(get_current_actor)) -> AuthActor:
        missing = [scope for scope in required_scopes if scope not in actor.scopes]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required scopes: {', '.join(missing)}",
            )
        return actor

    return dependency
