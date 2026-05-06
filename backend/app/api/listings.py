from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthActor, get_current_actor, require_scopes
from app.core.config import get_settings
from app.db.session import get_session
from app.models import AIJob, Category, CreditWallet, Favorite, Listing, ListingDraft, ListingImage, Report, UsageLedger
from app.models.entities import AIJobStatus, AIJobType, ImageProvenance, ListingWorkflowStatus
from app.schemas.domain import (
    DraftCreateRequest,
    DraftImageGenerateRequest,
    DraftResponse,
    DraftUpdateRequest,
    FavoriteResponse,
    ListingAutofillOutput,
    ListingResponse,
    ReportRequest,
)
from app.services.ai import AIService
from app.services.bootstrap import slugify
from app.services.marketplace_ops import publish_draft_listing, validate_publishable_draft
from app.services.storage import StorageService


router = APIRouter(prefix="/draft-listings", tags=["draft-listings"])
listing_router = APIRouter(prefix="/listings", tags=["listings-actions"])


def _normalize_category_slug(category_path: list[str], available: set[str]) -> str:
    for candidate in category_path:
        normalized = slugify(candidate)
        if normalized in available:
            return normalized
        compact = normalized.replace("/", "-")
        if compact in available:
            return compact
    return "electronics"


async def _get_draft_for_seller(session: AsyncSession, seller_id: str, draft_id: str) -> ListingDraft:
    draft = await session.scalar(
        select(ListingDraft)
        .where(ListingDraft.id == draft_id, ListingDraft.seller_id == seller_id)
        .options(selectinload(ListingDraft.images))
        .execution_options(populate_existing=True)
    )
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")
    return draft


async def _get_listing(session: AsyncSession, listing_id_or_slug: str) -> Listing | None:
    return await session.scalar(
        select(Listing)
        .where(or_(Listing.id == listing_id_or_slug, Listing.slug == listing_id_or_slug))
        .options(selectinload(Listing.images))
        .execution_options(populate_existing=True)
    )


@router.get("", response_model=list[DraftResponse])
async def my_drafts(
    actor: AuthActor = Depends(require_scopes("listings:write")),
    session: AsyncSession = Depends(get_session),
) -> list[DraftResponse]:
    drafts = (
        await session.scalars(
            select(ListingDraft)
            .where(ListingDraft.seller_id == actor.user.id)
            .options(selectinload(ListingDraft.images))
            .order_by(ListingDraft.updated_at.desc())
        )
    ).all()
    return [DraftResponse.model_validate(draft) for draft in drafts]


@router.post("", response_model=DraftResponse)
async def create_draft(
    payload: DraftCreateRequest,
    actor: AuthActor = Depends(require_scopes("listings:write")),
    session: AsyncSession = Depends(get_session),
) -> DraftResponse:
    draft = ListingDraft(
        seller_id=actor.user.id,
        title=payload.title,
        product_name=payload.product_name,
        description=payload.description,
        category_slug=payload.category_slug,
        condition=payload.condition,
        condition_score=payload.condition_score,
        brand=payload.brand,
        color=payload.color,
        approx_dimensions_text=payload.approx_dimensions_text,
        intended_use=payload.intended_use,
        attributes=payload.attributes,
        asking_price_cents=payload.asking_price_cents,
        currency_code=payload.currency_code or get_settings().default_currency,
        city_slug=payload.city_slug or actor.user.city_slug,
    )
    session.add(draft)
    await session.commit()
    draft = await _get_draft_for_seller(session, actor.user.id, draft.id)
    return DraftResponse.model_validate(draft)


@router.get("/{draft_id}", response_model=DraftResponse)
async def get_draft(
    draft_id: str,
    actor: AuthActor = Depends(require_scopes("listings:write")),
    session: AsyncSession = Depends(get_session),
) -> DraftResponse:
    draft = await _get_draft_for_seller(session, actor.user.id, draft_id)
    return DraftResponse.model_validate(draft)


@router.post("/ai-autofill", response_model=DraftResponse)
async def ai_autofill_draft(
    city_slug: str | None = Form(default=None),
    currency_code: str = Form(default="USD"),
    files: list[UploadFile] = File(...),
    actor: AuthActor = Depends(require_scopes("listings:write", "ai:generate")),
    session: AsyncSession = Depends(get_session),
) -> DraftResponse:
    storage = StorageService()
    saved_paths: list[Path] = []
    saved_images: list[ListingImage] = []
    for index, upload in enumerate(files):
        stored = await storage.save_upload(upload)
        saved_paths.append(get_settings().media_root / stored.storage_path)
        saved_images.append(
            ListingImage(
                provenance=ImageProvenance.user_upload.value,
                storage_path=stored.storage_path,
                public_url=stored.public_url,
                width=stored.width,
                height=stored.height,
                position=index,
            )
        )

    ai = AIService()
    suggestion, model_id = await ai.autofill_listing(saved_paths, currency_code)
    available = set((await session.scalars(select(Category.slug))).all())
    draft = ListingDraft(
        seller_id=actor.user.id,
        title=suggestion.title,
        product_name=suggestion.product_name,
        description=suggestion.description,
        category_slug=_normalize_category_slug(suggestion.category_path, available),
        condition=suggestion.condition,
        condition_score=suggestion.condition_score,
        brand=suggestion.brand,
        color=suggestion.color,
        approx_dimensions_text=suggestion.approx_dimensions_text,
        intended_use=suggestion.intended_use,
        attributes=suggestion.attributes,
        suggested_price_cents=round(suggestion.suggested_price * 100),
        currency_code=suggestion.currency_code,
        city_slug=city_slug or actor.user.city_slug,
        status=ListingWorkflowStatus.pending_review.value,
        ai_confidence=suggestion.price_confidence,
        ai_missing_fields=suggestion.missing_fields,
        ai_safety_flags=suggestion.safety_flags,
        ai_source_model=model_id,
    )
    session.add(draft)
    await session.flush()
    for image in saved_images:
        image.draft_id = draft.id
        session.add(image)
    session.add(
        AIJob(
            draft_id=draft.id,
            job_type=AIJobType.autofill.value,
            status=AIJobStatus.completed.value,
            model_id=model_id,
            request_payload={"image_count": len(saved_images)},
            result_payload=ListingAutofillOutput.model_validate(suggestion).model_dump(),
        )
    )
    await session.commit()
    draft = await _get_draft_for_seller(session, actor.user.id, draft.id)
    return DraftResponse.model_validate(draft)


@router.patch("/{draft_id}", response_model=DraftResponse)
async def update_draft(
    draft_id: str,
    payload: DraftUpdateRequest,
    actor: AuthActor = Depends(require_scopes("listings:write")),
    session: AsyncSession = Depends(get_session),
) -> DraftResponse:
    draft = await _get_draft_for_seller(session, actor.user.id, draft_id)
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(draft, field, value)
    await session.commit()
    await session.refresh(draft)
    draft = await _get_draft_for_seller(session, actor.user.id, draft.id)
    return DraftResponse.model_validate(draft)


@router.post("/ai-image", response_model=DraftResponse)
async def generate_draft_image(
    payload: DraftImageGenerateRequest,
    actor: AuthActor = Depends(require_scopes("listings:write", "ai:generate")),
    session: AsyncSession = Depends(get_session),
) -> DraftResponse:
    draft = await _get_draft_for_seller(session, actor.user.id, payload.draft_id)
    wallet = await session.scalar(select(CreditWallet).where(CreditWallet.user_id == actor.user.id))
    ai = AIService()
    credits_required = {"low": 4, "medium": 8, "high": 12, "auto": 8}.get(payload.quality, 8)
    if not wallet or wallet.balance_credits < credits_required:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Insufficient prepaid credits.")

    job = AIJob(
        draft_id=draft.id,
        job_type=AIJobType.sale_image.value,
        status=AIJobStatus.running.value,
        model_id=get_settings().openai_image_model,
        request_payload=payload.model_dump(),
    )
    session.add(job)
    await session.flush()

    image_bytes, metadata, credits_spent = await ai.generate_sale_image(
        title=draft.title or "Used item",
        description=draft.description or "",
        attributes=draft.attributes,
        request=payload,
    )
    storage = StorageService()
    stored = storage.save_generated_image(image_bytes, draft.title or "generated")
    image = ListingImage(
        draft_id=draft.id,
        provenance=ImageProvenance.ai_generated.value,
        storage_path=stored.storage_path,
        public_url=stored.public_url,
        width=stored.width,
        height=stored.height,
        position=len(draft.images),
    )
    wallet.balance_credits -= credits_spent
    session.add(image)
    session.add(
        UsageLedger(
            user_id=actor.user.id,
            kind="image_generation",
            delta_credits=-credits_spent,
            description="AI sale image generation",
            reference_type="ai_job",
            reference_id=job.id,
        )
    )
    job.status = AIJobStatus.completed.value
    job.credits_spent = credits_spent
    job.result_payload = metadata
    await session.commit()
    draft = await _get_draft_for_seller(session, actor.user.id, draft.id)
    return DraftResponse.model_validate(draft)


@router.post("/{draft_id}/publish", response_model=ListingResponse)
async def publish_draft(
    draft_id: str,
    actor: AuthActor = Depends(require_scopes("listings:write")),
    session: AsyncSession = Depends(get_session),
) -> ListingResponse:
    draft = await _get_draft_for_seller(session, actor.user.id, draft_id)
    try:
        validate_publishable_draft(draft)
        listing = await publish_draft_listing(session, actor.user.id, draft)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await session.commit()
    listing = await _get_listing(session, listing.id)
    return ListingResponse.model_validate(listing)


@listing_router.post("/{listing_id}/favorite", response_model=FavoriteResponse)
async def favorite_listing(
    listing_id: str,
    actor: AuthActor = Depends(get_current_actor),
    session: AsyncSession = Depends(get_session),
) -> FavoriteResponse:
    listing = await _get_listing(session, listing_id)
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")
    existing = await session.scalar(select(Favorite).where(Favorite.user_id == actor.user.id, Favorite.listing_id == listing.id))
    if not existing:
        existing = Favorite(user_id=actor.user.id, listing_id=listing.id)
        session.add(existing)
        await session.commit()
        await session.refresh(existing)
    return FavoriteResponse.model_validate(existing)


@listing_router.delete("/{listing_id}/favorite")
async def unfavorite_listing(
    listing_id: str,
    actor: AuthActor = Depends(get_current_actor),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    listing = await _get_listing(session, listing_id)
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")
    await session.execute(delete(Favorite).where(Favorite.user_id == actor.user.id, Favorite.listing_id == listing.id))
    await session.commit()
    return {"removed": True}


@listing_router.post("/{listing_id}/report")
async def report_listing(
    listing_id: str,
    payload: ReportRequest,
    actor: AuthActor = Depends(get_current_actor),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    listing = await _get_listing(session, listing_id)
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")
    session.add(Report(user_id=actor.user.id, listing_id=listing.id, reason=payload.reason))
    await session.commit()
    return {"reported": True}
