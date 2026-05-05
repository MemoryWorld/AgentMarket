from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models import Category, City, Listing, SellerProfile
from app.schemas.domain import CategoryResponse, CityResponse, ListingResponse, ListingSummaryResponse, SearchResponse, SellerProfileResponse


router = APIRouter(tags=["public"])


def build_listing_summary(listing: Listing) -> ListingSummaryResponse:
    primary_image = None
    if listing.images:
        sorted_images = sorted(listing.images, key=lambda image: image.position)
        primary_image = sorted_images[0].public_url
    return ListingSummaryResponse(
        id=listing.id,
        slug=listing.slug,
        title=listing.title,
        asking_price_cents=listing.asking_price_cents,
        currency_code=listing.currency_code,
        city_slug=listing.city_slug,
        category_slug=listing.category_slug,
        condition=listing.condition,
        primary_image_url=primary_image,
        created_at=listing.created_at,
    )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(session: AsyncSession = Depends(get_session)) -> list[CategoryResponse]:
    rows = (await session.scalars(select(Category).order_by(Category.display_order, Category.slug))).all()
    return [CategoryResponse.model_validate(row) for row in rows]


@router.get("/cities", response_model=list[CityResponse])
async def list_cities(session: AsyncSession = Depends(get_session)) -> list[CityResponse]:
    rows = (await session.scalars(select(City).order_by(City.display_name))).all()
    return [CityResponse.model_validate(row) for row in rows]


@router.get("/listings", response_model=SearchResponse)
async def list_listings(
    q: str | None = None,
    category_slug: str | None = None,
    city_slug: str | None = None,
    seller_id: str | None = None,
    condition: str | None = None,
    min_price_cents: int | None = Query(default=None, ge=0),
    max_price_cents: int | None = Query(default=None, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    filters = [Listing.visibility == "public", Listing.status == "published"]
    if q:
        wildcard = f"%{q.strip()}%"
        filters.append(or_(Listing.title.ilike(wildcard), Listing.description.ilike(wildcard), Listing.brand.ilike(wildcard)))
    if category_slug:
        filters.append(Listing.category_slug == category_slug)
    if city_slug:
        filters.append(Listing.city_slug == city_slug)
    if seller_id:
        filters.append(Listing.seller_id == seller_id)
    if condition:
        filters.append(Listing.condition == condition)
    if min_price_cents is not None:
        filters.append(Listing.asking_price_cents >= min_price_cents)
    if max_price_cents is not None:
        filters.append(Listing.asking_price_cents <= max_price_cents)

    total = await session.scalar(select(func.count(Listing.id)).where(*filters))
    query = (
        select(Listing)
        .where(*filters)
        .options(selectinload(Listing.images))
        .order_by(Listing.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    listings = (await session.scalars(query)).all()
    return SearchResponse(items=[build_listing_summary(listing) for listing in listings], total=total or 0)


@router.get("/search", response_model=SearchResponse)
async def search_listings(
    q: str | None = None,
    category_slug: str | None = None,
    city_slug: str | None = None,
    seller_id: str | None = None,
    condition: str | None = None,
    min_price_cents: int | None = Query(default=None, ge=0),
    max_price_cents: int | None = Query(default=None, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> SearchResponse:
    return await list_listings(q, category_slug, city_slug, seller_id, condition, min_price_cents, max_price_cents, limit, offset, session)


@router.get("/listings/{listing_id_or_slug}", response_model=ListingResponse)
async def get_listing(listing_id_or_slug: str, session: AsyncSession = Depends(get_session)) -> ListingResponse:
    listing = await session.scalar(
        select(Listing)
        .where(or_(Listing.id == listing_id_or_slug, Listing.slug == listing_id_or_slug))
        .options(selectinload(Listing.images))
    )
    if not listing or listing.visibility != "public":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")
    return ListingResponse.model_validate(listing)


@router.get("/sellers/{seller_id}", response_model=SellerProfileResponse)
async def get_seller(seller_id: str, session: AsyncSession = Depends(get_session)) -> SellerProfileResponse:
    seller = await session.scalar(
        select(SellerProfile).where(SellerProfile.user_id == seller_id).options(selectinload(SellerProfile.user))
    )
    if not seller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Seller not found.")
    return SellerProfileResponse.model_validate(seller)
