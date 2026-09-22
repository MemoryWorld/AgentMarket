from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token, sha256_text, utcnow
from app.db.session import get_session
from app.models import AgentGrant, PersonalAccessToken, User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class AuthActor:
    user: User
    scopes: set[str]
    token_type: str
    pat: PersonalAccessToken | None = None
    agent_grant: AgentGrant | None = None


async def resolve_actor(token: str, session: AsyncSession) -> AuthActor:
    """Shared REST/MCP credential policy; grant scopes can only narrow a PAT."""
    if token.startswith("pat_"):
        pat = await session.scalar(select(PersonalAccessToken).where(PersonalAccessToken.token_hash == sha256_text(token)))
        if not pat or pat.revoked:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid personal access token.")
        pat.last_used_at = utcnow()
        user = await session.get(User, pat.user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token user no longer exists.")
        grant = await session.scalar(select(AgentGrant).where(AgentGrant.personal_access_token_id == pat.id))
        if grant and (grant.status != "active" or grant.user_id != pat.user_id):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Agent grant is invalid or revoked.")
        scopes = set(pat.scopes or [])
        if grant:
            scopes.intersection_update(grant.scopes or [])
        await session.commit()
        return AuthActor(user=user, scopes=scopes, token_type="pat", pat=pat, agent_grant=grant)

    try:
        payload = decode_access_token(token)
        if payload.get("type") != "access":
            raise ValueError("Wrong token type")
        if not isinstance(payload.get("sub"), str):
            raise ValueError("Missing subject")
    except (InvalidTokenError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="Invalid access token.") from exc
    user = await session.get(User, payload["sub"])
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")
    default_scopes = {
        "listings:read",
        "listings:write",
        "orders:write",
        "ai:generate",
        "messages:read",
        "messages:write",
        "offers:read",
        "offers:write",
        "approvals:read",
        "approvals:write",
        "grants:read",
        "grants:write",
        "receipts:read",
    }
    return AuthActor(user=user, scopes=default_scopes, token_type="access")


async def get_current_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> AuthActor:
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    return await resolve_actor(credentials.credentials, session)


def check_scopes(actor: AuthActor, *required_scopes: str) -> None:
    missing = sorted(set(required_scopes) - actor.scopes)
    if missing:
        raise HTTPException(status_code=403, detail=f"Missing required scopes: {', '.join(missing)}")


def check_human(actor: AuthActor) -> None:
    if actor.token_type != "access":
        raise HTTPException(status_code=403, detail="Human approval requires an interactive access token; agent/PAT credentials cannot decide or bypass approval.")


def require_human(*required_scopes: str) -> Callable[[AuthActor], AuthActor]:
    async def dependency(actor: AuthActor = Depends(get_current_actor)) -> AuthActor:
        check_human(actor)
        check_scopes(actor, *required_scopes)
        return actor
    return dependency


def require_scopes(*required_scopes: str) -> Callable[[AuthActor], AuthActor]:
    async def dependency(actor: AuthActor = Depends(get_current_actor)) -> AuthActor:
        check_scopes(actor, *required_scopes)
        return actor

    return dependency
