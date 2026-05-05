from datetime import UTC
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthActor, get_current_actor
from app.core.config import get_settings
from app.core.security import create_access_token, create_personal_access_token, generate_otp, sha256_text, utcnow
from app.db.session import get_session
from app.models import CreditWallet, EmailOTP, PersonalAccessToken, SellerProfile, UsageLedger, User
from app.schemas.domain import (
    AuthTokenResponse,
    OTPRequest,
    OTPRequestResponse,
    OTPVerifyRequest,
    PATCreateRequest,
    PATCreateResponse,
    PATResponse,
    TopUpRequest,
    TopUpResponse,
    UserResponse,
    WalletResponse,
)
from app.services.bootstrap import slugify


router = APIRouter(prefix="/auth", tags=["auth"])
wallet_router = APIRouter(prefix="/wallet", tags=["wallet"])
token_router = APIRouter(prefix="/personal-access-tokens", tags=["personal-access-tokens"])


@router.post("/email/request-code", response_model=OTPRequestResponse)
async def request_email_code(payload: OTPRequest, session: AsyncSession = Depends(get_session)) -> OTPRequestResponse:
    code = generate_otp()
    record = await session.get(EmailOTP, payload.email)
    expires_at = utcnow() + timedelta(minutes=15)
    if record:
        record.code_hash = sha256_text(code)
        record.expires_at = expires_at
        record.attempts = 0
    else:
        session.add(EmailOTP(email=payload.email, code_hash=sha256_text(code), expires_at=expires_at))
    await session.commit()
    return OTPRequestResponse(sent=True, debug_code=code if get_settings().expose_debug_otp else None)


@router.post("/email/verify", response_model=AuthTokenResponse)
async def verify_email_code(payload: OTPVerifyRequest, session: AsyncSession = Depends(get_session)) -> AuthTokenResponse:
    record = await session.get(EmailOTP, payload.email)
    expires_at = record.expires_at.replace(tzinfo=UTC) if record and record.expires_at.tzinfo is None else record.expires_at if record else None
    if not record or (expires_at and expires_at < utcnow()):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP is missing or expired.")
    if record.code_hash != sha256_text(payload.code):
        record.attempts += 1
        await session.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP code is incorrect.")

    user = await session.scalar(select(User).where(User.email == payload.email))
    if not user:
        display_name = payload.display_name or payload.email.split("@")[0].replace(".", " ").title()
        user = User(
            email=payload.email,
            display_name=display_name,
            city_slug=payload.city_slug,
            country_code=payload.country_code or get_settings().default_country_code,
        )
        session.add(user)
        await session.flush()
        session.add(SellerProfile(user_id=user.id, handle=slugify(display_name)))
        session.add(CreditWallet(user_id=user.id, balance_credits=20))
    else:
        user.city_slug = payload.city_slug or user.city_slug
        user.country_code = payload.country_code or user.country_code

    await session.delete(record)
    await session.commit()
    wallet = await session.scalar(select(CreditWallet).where(CreditWallet.user_id == user.id))
    access_token = create_access_token(user.id, {"email": user.email})
    return AuthTokenResponse(
        access_token=access_token,
        user=UserResponse.model_validate(user),
        wallet=WalletResponse(balance_credits=wallet.balance_credits if wallet else 0),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(actor: AuthActor = Depends(get_current_actor)) -> UserResponse:
    return UserResponse.model_validate(actor.user)


@wallet_router.get("", response_model=WalletResponse)
async def get_wallet(
    actor: AuthActor = Depends(get_current_actor),
    session: AsyncSession = Depends(get_session),
) -> WalletResponse:
    wallet = await session.scalar(select(CreditWallet).where(CreditWallet.user_id == actor.user.id))
    return WalletResponse(balance_credits=wallet.balance_credits if wallet else 0)


@wallet_router.post("/top-up", response_model=TopUpResponse)
async def top_up_wallet(
    payload: TopUpRequest,
    actor: AuthActor = Depends(get_current_actor),
    session: AsyncSession = Depends(get_session),
) -> TopUpResponse:
    wallet = await session.scalar(select(CreditWallet).where(CreditWallet.user_id == actor.user.id))
    if not wallet:
        wallet = CreditWallet(user_id=actor.user.id, balance_credits=0)
        session.add(wallet)
    wallet.balance_credits += payload.credits
    session.add(
        UsageLedger(
            user_id=actor.user.id,
            kind="credit_purchase",
            delta_credits=payload.credits,
            description="Mock top-up for prepaid image generation credits.",
        )
    )
    await session.commit()
    return TopUpResponse(balance_credits=wallet.balance_credits)


@token_router.get("", response_model=list[PATResponse])
async def list_tokens(
    actor: AuthActor = Depends(get_current_actor),
    session: AsyncSession = Depends(get_session),
) -> list[PATResponse]:
    tokens = (await session.scalars(select(PersonalAccessToken).where(PersonalAccessToken.user_id == actor.user.id))).all()
    return [PATResponse.model_validate(token) for token in tokens]


@token_router.post("", response_model=PATCreateResponse)
async def create_pat(
    payload: PATCreateRequest,
    actor: AuthActor = Depends(get_current_actor),
    session: AsyncSession = Depends(get_session),
) -> PATCreateResponse:
    token, prefix, token_hash = create_personal_access_token()
    record = PersonalAccessToken(
        user_id=actor.user.id,
        name=payload.name,
        token_prefix=prefix,
        token_hash=token_hash,
        scopes=payload.scopes,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    pat_payload = PATResponse.model_validate(record).model_dump()
    return PATCreateResponse(**pat_payload, token=token)


@token_router.post("/{token_id}/revoke", response_model=PATResponse)
async def revoke_pat(
    token_id: str,
    actor: AuthActor = Depends(get_current_actor),
    session: AsyncSession = Depends(get_session),
) -> PATResponse:
    record = await session.scalar(
        select(PersonalAccessToken).where(
            PersonalAccessToken.id == token_id,
            PersonalAccessToken.user_id == actor.user.id,
        )
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found.")
    record.revoked = True
    await session.commit()
    await session.refresh(record)
    return PATResponse.model_validate(record)
