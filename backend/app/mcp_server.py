import tempfile
from pathlib import Path

import httpx
from fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.listings import _normalize_category_slug
from app.api.public import build_listing_summary
from app.core.config import get_settings
from app.core.security import decode_access_token, sha256_text
from app.db.session import SessionLocal
from app.models import Category, CreditWallet, Listing, ListingDraft, ListingImage, Order, PersonalAccessToken, UsageLedger, User
from app.models.entities import ImageProvenance, OrderStatus
from app.schemas.domain import DraftImageGenerateRequest, OrderAddressRequest, SearchResponse
from app.services.ai import AIService
from app.services.bootstrap import slugify
from app.services.storage import StorageService


mcp = FastMCP("Agent Marketplace")


async def _resolve_actor(token: str) -> User:
    async with SessionLocal() as session:
        if token.startswith("pat_"):
            pat = await session.scalar(select(PersonalAccessToken).where(PersonalAccessToken.token_hash == sha256_text(token)))
            if not pat or pat.revoked:
                raise ValueError("Invalid personal access token.")
            user = await session.get(User, pat.user_id)
            if not user:
                raise ValueError("Token user does not exist.")
            return user
        payload = decode_access_token(token)
        user = await session.get(User, payload["sub"])
        if not user:
            raise ValueError("User not found.")
        return user


@mcp.tool
async def search_listings(query: str | None = None, city_slug: str | None = None, category_slug: str | None = None) -> dict:
    async with SessionLocal() as session:
        stmt = select(Listing).where(Listing.visibility == "public", Listing.status == "published").options(selectinload(Listing.images))
        if query:
            wildcard = f"%{query}%"
            stmt = stmt.where(Listing.title.ilike(wildcard) | Listing.description.ilike(wildcard))
        if city_slug:
            stmt = stmt.where(Listing.city_slug == city_slug)
        if category_slug:
            stmt = stmt.where(Listing.category_slug == category_slug)
        listings = (await session.scalars(stmt.order_by(Listing.created_at.desc()).limit(25))).all()
        result = SearchResponse(items=[build_listing_summary(item) for item in listings], total=len(listings))
        return result.model_dump()


@mcp.tool
async def get_listing(listing_id_or_slug: str) -> dict:
    async with SessionLocal() as session:
        listing = await session.scalar(
            select(Listing).where((Listing.id == listing_id_or_slug) | (Listing.slug == listing_id_or_slug)).options(selectinload(Listing.images))
        )
        if not listing:
            raise ValueError("Listing not found.")
        return {
            "id": listing.id,
            "slug": listing.slug,
            "title": listing.title,
            "description": listing.description,
            "price_cents": listing.asking_price_cents,
            "currency_code": listing.currency_code,
            "city_slug": listing.city_slug,
            "images": [image.public_url for image in listing.images],
        }


@mcp.tool
async def get_category_tree() -> list[dict]:
    async with SessionLocal() as session:
        rows = (await session.scalars(select(Category).order_by(Category.display_order, Category.slug))).all()
        return [{"slug": row.slug, "name": row.name, "parent_slug": row.parent_slug} for row in rows]


@mcp.tool
async def create_listing_draft(access_token: str, title: str, description: str, city_slug: str, asking_price_cents: int) -> dict:
    user = await _resolve_actor(access_token)
    async with SessionLocal() as session:
        draft = ListingDraft(
            seller_id=user.id,
            title=title,
            description=description,
            city_slug=city_slug,
            asking_price_cents=asking_price_cents,
            currency_code=get_settings().default_currency,
        )
        session.add(draft)
        await session.commit()
        return {"draft_id": draft.id, "status": draft.status}


@mcp.tool
async def autofill_listing_from_photos(access_token: str, photo_urls: list[str], currency_code: str = "USD") -> dict:
    user = await _resolve_actor(access_token)
    storage = StorageService()
    ai = AIService()
    async with httpx.AsyncClient(timeout=30) as client:
        local_paths: list[Path] = []
        stored_images: list[ListingImage] = []
        async with SessionLocal() as session:
            for index, photo_url in enumerate(photo_urls):
                response = await client.get(photo_url)
                response.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as handle:
                    handle.write(response.content)
                    temp_path = Path(handle.name)
                local_paths.append(temp_path)
            suggestion, model_id = await ai.autofill_listing(local_paths, currency_code)
            available = set((await session.scalars(select(Category.slug))).all())
            draft = ListingDraft(
                seller_id=user.id,
                title=suggestion.title,
                description=suggestion.description,
                category_slug=_normalize_category_slug(suggestion.category_path, available),
                condition=suggestion.condition,
                brand=suggestion.brand,
                color=suggestion.color,
                attributes=suggestion.attributes,
                suggested_price_cents=round(suggestion.suggested_price * 100),
                currency_code=suggestion.currency_code,
                city_slug=user.city_slug,
                ai_confidence=suggestion.price_confidence,
                ai_missing_fields=suggestion.missing_fields,
                ai_safety_flags=suggestion.safety_flags,
                ai_source_model=model_id,
            )
            session.add(draft)
            await session.flush()
            for index, local_path in enumerate(local_paths):
                class TempUpload:
                    filename = local_path.name

                    async def read(self) -> bytes:
                        return local_path.read_bytes()

                stored = await storage.save_upload(TempUpload())
                stored_images.append(
                    ListingImage(
                        draft_id=draft.id,
                        provenance=ImageProvenance.user_upload.value,
                        storage_path=stored.storage_path,
                        public_url=stored.public_url,
                        width=stored.width,
                        height=stored.height,
                        position=index,
                    )
                )
            session.add_all(stored_images)
            await session.commit()
            return {"draft_id": draft.id, "title": draft.title, "model_id": model_id}


@mcp.tool
async def generate_listing_image(access_token: str, draft_id: str, style_preset: str = "clean studio") -> dict:
    user = await _resolve_actor(access_token)
    async with SessionLocal() as session:
        draft = await session.scalar(select(ListingDraft).where(ListingDraft.id == draft_id, ListingDraft.seller_id == user.id))
        if not draft:
            raise ValueError("Draft not found.")
        wallet = await session.scalar(select(CreditWallet).where(CreditWallet.user_id == user.id))
        if not wallet or wallet.balance_credits < 8:
            raise ValueError("Insufficient credits.")
        ai = AIService()
        storage = StorageService()
        image_bytes, metadata, credits_spent = await ai.generate_sale_image(
            title=draft.title or "Used item",
            description=draft.description or "",
            attributes=draft.attributes,
            request=DraftImageGenerateRequest(draft_id=draft.id, style_preset=style_preset),
        )
        stored = storage.save_generated_image(image_bytes, draft.title or "generated")
        session.add(
            ListingImage(
                draft_id=draft.id,
                provenance=ImageProvenance.ai_generated.value,
                storage_path=stored.storage_path,
                public_url=stored.public_url,
                width=stored.width,
                height=stored.height,
                position=99,
            )
        )
        wallet.balance_credits -= credits_spent
        session.add(
            UsageLedger(
                user_id=user.id,
                kind="image_generation",
                delta_credits=-credits_spent,
                description="MCP image generation",
                reference_type="draft",
                reference_id=draft.id,
            )
        )
        await session.commit()
        return {"draft_id": draft.id, "image_url": stored.public_url, "metadata": metadata}


@mcp.tool
async def publish_listing_draft(access_token: str, draft_id: str) -> dict:
    user = await _resolve_actor(access_token)
    async with SessionLocal() as session:
        draft = await session.scalar(select(ListingDraft).where(ListingDraft.id == draft_id, ListingDraft.seller_id == user.id))
        if not draft:
            raise ValueError("Draft not found.")
        slug_base = draft.title or "listing"
        slug = slugify(slug_base)
        existing = await session.scalar(select(Listing).where(Listing.slug == slug))
        if existing:
            slug = f"{slug}-{draft.id[:6]}"
        listing = Listing(
            seller_id=user.id,
            draft_id=draft.id,
            slug=slug,
            title=draft.title or "Untitled",
            description=draft.description or "",
            category_slug=draft.category_slug or "electronics",
            condition=draft.condition,
            brand=draft.brand,
            color=draft.color,
            attributes=draft.attributes,
            asking_price_cents=draft.asking_price_cents or draft.suggested_price_cents or 0,
            currency_code=draft.currency_code,
            city_slug=draft.city_slug or user.city_slug or "sydney-au",
            ai_confidence=draft.ai_confidence,
            ai_source_model=draft.ai_source_model,
        )
        session.add(listing)
        await session.flush()
        images = (await session.scalars(select(ListingImage).where(ListingImage.draft_id == draft.id))).all()
        for image in images:
            image.listing_id = listing.id
        await session.commit()
        return {"listing_id": listing.id, "slug": listing.slug}


@mcp.tool
async def create_order(access_token: str, listing_id_or_slug: str) -> dict:
    user = await _resolve_actor(access_token)
    async with SessionLocal() as session:
        listing = await session.scalar(select(Listing).where((Listing.id == listing_id_or_slug) | (Listing.slug == listing_id_or_slug)))
        if not listing:
            raise ValueError("Listing not found.")
        order = Order(
            listing_id=listing.id,
            buyer_id=user.id,
            seller_id=listing.seller_id,
            status=OrderStatus.address_pending.value,
        )
        session.add(order)
        await session.commit()
        return {"order_id": order.id, "status": order.status}


@mcp.tool
async def submit_shipping_address(access_token: str, order_id: str, address: dict) -> dict:
    user = await _resolve_actor(access_token)
    payload = OrderAddressRequest.model_validate({"address": address})
    async with SessionLocal() as session:
        order = await session.get(Order, order_id)
        if not order or order.buyer_id != user.id:
            raise ValueError("Order not found.")
        order.address_payload = payload.address.model_dump()
        order.status = OrderStatus.payment_pending.value
        await session.commit()
        return {"order_id": order.id, "status": order.status}


@mcp.tool
async def confirm_mock_payment(access_token: str, order_id: str) -> dict:
    user = await _resolve_actor(access_token)
    async with SessionLocal() as session:
        order = await session.get(Order, order_id)
        if not order or order.buyer_id != user.id:
            raise ValueError("Order not found.")
        order.status = OrderStatus.paid.value
        await session.commit()
        return {"order_id": order.id, "status": order.status}


@mcp.tool
async def get_order(access_token: str, order_id: str) -> dict:
    user = await _resolve_actor(access_token)
    async with SessionLocal() as session:
        order = await session.get(Order, order_id)
        if not order or user.id not in {order.buyer_id, order.seller_id}:
            raise ValueError("Order not found.")
        return {
            "order_id": order.id,
            "status": order.status,
            "listing_id": order.listing_id,
            "address": order.address_payload,
            "tracking_number": order.tracking_number,
            "carrier": order.carrier,
        }
