import hashlib
import json

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Listing, ListingDraft
from app.models.entities import ListingWorkflowStatus
from app.services.bootstrap import slugify


async def get_listing_by_id_or_slug(session: AsyncSession, listing_id_or_slug: str) -> Listing | None:
    return await session.scalar(
        select(Listing)
        .where(or_(Listing.id == listing_id_or_slug, Listing.slug == listing_id_or_slug))
        .options(selectinload(Listing.images))
        .execution_options(populate_existing=True)
    )


def validate_publishable_draft(draft: ListingDraft) -> None:
    required_fields = [
        draft.title,
        draft.product_name,
        draft.description,
        draft.category_slug,
        draft.condition_score,
        draft.asking_price_cents,
        draft.city_slug,
    ]
    if any(value in (None, "") for value in required_fields):
        raise ValueError("Draft is missing required publish fields.")
    if not draft.images:
        raise ValueError("Draft needs at least one image before publishing.")


async def publish_draft_listing(session: AsyncSession, seller_id: str, draft: ListingDraft) -> Listing:
    if draft.seller_id != seller_id:
        raise ValueError("Draft not found.")
    if draft.status == ListingWorkflowStatus.published.value:
        raise ValueError("Draft has already been published.")
    validate_publishable_draft(draft)

    base_slug = slugify(draft.title or "listing")
    slug = base_slug
    counter = 1
    while await get_listing_by_id_or_slug(session, slug):
        counter += 1
        slug = f"{base_slug}-{counter}"

    listing = Listing(
        seller_id=seller_id,
        draft_id=draft.id,
        slug=slug,
        title=draft.title or "Untitled",
        product_name=draft.product_name,
        description=draft.description or "",
        category_slug=draft.category_slug or "electronics",
        condition=draft.condition,
        condition_score=draft.condition_score,
        brand=draft.brand,
        color=draft.color,
        approx_dimensions_text=draft.approx_dimensions_text,
        intended_use=draft.intended_use,
        attributes=draft.attributes,
        asking_price_cents=draft.asking_price_cents or draft.suggested_price_cents or 0,
        currency_code=draft.currency_code,
        city_slug=draft.city_slug or "sydney-au",
        ai_confidence=draft.ai_confidence,
        ai_source_model=draft.ai_source_model,
    )
    session.add(listing)
    await session.flush()
    for image in draft.images:
        image.listing_id = listing.id
    draft.status = ListingWorkflowStatus.published.value
    return listing


def draft_snapshot(draft: ListingDraft) -> str:
    """Bind confirmation to every publishable field and image, not mutable IDs."""
    values = {column.name: getattr(draft, column.name) for column in draft.__table__.columns
              if column.name not in {"created_at", "updated_at"}}
    values["images"] = [
        {column.name: getattr(image, column.name) for column in image.__table__.columns if column.name != "created_at"}
        for image in sorted(draft.images, key=lambda image: image.id)
    ]
    return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_fulfillment_transition(current: str, target: str) -> None:
    allowed = {"paid": {"confirmed", "shipped"}, "confirmed": {"shipped"}, "shipped": {"delivered"}}
    if target not in allowed.get(current, set()):
        raise ValueError("Invalid fulfillment transition.")
