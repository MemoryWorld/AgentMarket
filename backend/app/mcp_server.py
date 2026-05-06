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
from app.models import (
    ActionReceipt,
    AgentGrant,
    ApprovalRequest,
    Category,
    CreditWallet,
    Listing,
    ListingDraft,
    ListingImage,
    MessageEvent,
    MessageThread,
    Offer,
    Order,
    PersonalAccessToken,
    UsageLedger,
    User,
)
from app.models.entities import ImageProvenance, MessageEventKind, MessageEventStatus, OfferStatus, OrderStatus
from app.schemas.domain import (
    ApprovalActionPrepareRequest,
    DraftImageGenerateRequest,
    MessageThreadCreateRequest,
    OfferCounterRequest,
    OfferCreateRequest,
    OfferDecisionRequest,
    OrderAddressRequest,
    SearchResponse,
)
from app.services.approval_ops import create_approval_request
from app.services.ai import AIService
from app.services.marketplace_ops import publish_draft_listing
from app.services.bootstrap import slugify
from app.services.storage import StorageService


mcp = FastMCP("Agent Marketplace")


async def _resolve_actor_context(token: str) -> tuple[User, AgentGrant | None]:
    async with SessionLocal() as session:
        if token.startswith("pat_"):
            pat = await session.scalar(select(PersonalAccessToken).where(PersonalAccessToken.token_hash == sha256_text(token)))
            if not pat or pat.revoked:
                raise ValueError("Invalid personal access token.")
            user = await session.get(User, pat.user_id)
            if not user:
                raise ValueError("Token user does not exist.")
            grant = await session.scalar(select(AgentGrant).where(AgentGrant.personal_access_token_id == pat.id))
            if grant and grant.status == "revoked":
                raise ValueError("Agent grant has been revoked.")
            return user, grant
        payload = decode_access_token(token)
        user = await session.get(User, payload["sub"])
        if not user:
            raise ValueError("User not found.")
        return user, None


async def _resolve_actor(token: str) -> User:
    user, _ = await _resolve_actor_context(token)
    return user


@mcp.tool
async def search_listings(query: str | None = None, city_slug: str | None = None, category_slug: str | None = None) -> dict:
    async with SessionLocal() as session:
        stmt = select(Listing).where(Listing.visibility == "public", Listing.status == "published").options(selectinload(Listing.images))
        if query:
            wildcard = f"%{query}%"
            stmt = stmt.where(
                Listing.title.ilike(wildcard)
                | Listing.product_name.ilike(wildcard)
                | Listing.description.ilike(wildcard)
                | Listing.brand.ilike(wildcard)
            )
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
            "product_name": listing.product_name,
            "description": listing.description,
            "price_cents": listing.asking_price_cents,
            "currency_code": listing.currency_code,
            "city_slug": listing.city_slug,
            "condition": listing.condition,
            "condition_score": listing.condition_score,
            "brand": listing.brand,
            "approx_dimensions_text": listing.approx_dimensions_text,
            "intended_use": listing.intended_use,
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
            product_name=title,
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
                city_slug=user.city_slug,
                status="pending_review",
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
        draft = await session.scalar(
            select(ListingDraft)
            .where(ListingDraft.id == draft_id, ListingDraft.seller_id == user.id)
            .options(selectinload(ListingDraft.images))
        )
        if not draft:
            raise ValueError("Draft not found.")
        listing = await publish_draft_listing(session, user.id, draft)
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


@mcp.tool
async def list_threads(access_token: str) -> list[dict]:
    user = await _resolve_actor(access_token)
    async with SessionLocal() as session:
        threads = (
            await session.scalars(
                select(MessageThread)
                .where((MessageThread.buyer_id == user.id) | (MessageThread.seller_id == user.id))
                .order_by(MessageThread.updated_at.desc())
            )
        ).all()
        return [
            {
                "id": thread.id,
                "listing_id": thread.listing_id,
                "seller_id": thread.seller_id,
                "buyer_id": thread.buyer_id,
                "subject": thread.subject,
                "status": thread.status,
                "last_message_at": thread.last_message_at.isoformat() if thread.last_message_at else None,
            }
            for thread in threads
        ]


@mcp.tool
async def create_message_thread(access_token: str, listing_id: str, participant_user_id: str | None = None, subject: str | None = None) -> dict:
    user = await _resolve_actor(access_token)
    async with SessionLocal() as session:
        listing = await session.get(Listing, listing_id)
        if not listing:
            raise ValueError("Listing not found.")
        payload = MessageThreadCreateRequest(listing_id=listing_id, participant_user_id=participant_user_id, subject=subject)
        if user.id == listing.seller_id:
            if not payload.participant_user_id:
                raise ValueError("participant_user_id is required for seller-created threads.")
            seller_id = user.id
            buyer_id = payload.participant_user_id
        else:
            seller_id = listing.seller_id
            buyer_id = user.id
        existing = await session.scalar(
            select(MessageThread).where(
                MessageThread.listing_id == listing.id,
                MessageThread.seller_id == seller_id,
                MessageThread.buyer_id == buyer_id,
                MessageThread.status == "open",
            )
        )
        if existing:
            return {"thread_id": existing.id, "status": existing.status}
        thread = MessageThread(
            listing_id=listing.id,
            seller_id=seller_id,
            buyer_id=buyer_id,
            subject=payload.subject,
        )
        session.add(thread)
        await session.commit()
        return {"thread_id": thread.id, "status": thread.status}


@mcp.tool
async def create_message_draft(access_token: str, thread_id: str, body: str, idempotency_key: str | None = None) -> dict:
    user, grant = await _resolve_actor_context(access_token)
    async with SessionLocal() as session:
        thread = await session.scalar(
            select(MessageThread).where(
                MessageThread.id == thread_id,
                ((MessageThread.buyer_id == user.id) | (MessageThread.seller_id == user.id)),
            )
        )
        if not thread:
            raise ValueError("Thread not found.")
        message = MessageEvent(
            thread_id=thread.id,
            sender_id=user.id,
            kind=MessageEventKind.user_message.value,
            status=MessageEventStatus.pending_approval.value,
            body=body,
        )
        session.add(message)
        await session.flush()
        approval = await create_approval_request(
            session,
            owner_user_id=user.id,
            requested_by_user_id=user.id,
            agent_grant_id=grant.id if grant else None,
            action_type="send_message",
            resource_type="message",
            resource_id=message.id,
            summary=f"Send message in thread {thread.id[:8]}.",
            diff_payload={"body_preview": body[:180]},
            action_payload={"thread_id": thread.id, "message_id": message.id},
            idempotency_key=idempotency_key,
        )
        message.approval_request_id = approval.id
        await session.commit()
        return {"message_id": message.id, "approval_request_id": approval.id, "status": message.status}


@mcp.tool
async def create_offer(access_token: str, thread_id: str, amount_cents: int, note: str | None = None, idempotency_key: str | None = None) -> dict:
    user, grant = await _resolve_actor_context(access_token)
    payload = OfferCreateRequest(thread_id=thread_id, amount_cents=amount_cents, note=note, idempotency_key=idempotency_key)
    async with SessionLocal() as session:
        thread = await session.scalar(
            select(MessageThread).where(
                MessageThread.id == payload.thread_id,
                ((MessageThread.buyer_id == user.id) | (MessageThread.seller_id == user.id)),
            )
        )
        if not thread:
            raise ValueError("Thread not found.")
        listing = await session.get(Listing, thread.listing_id)
        if not listing:
            raise ValueError("Listing not found.")
        offer = Offer(
            thread_id=thread.id,
            listing_id=thread.listing_id,
            buyer_id=thread.buyer_id,
            seller_id=thread.seller_id,
            created_by_user_id=user.id,
            amount_cents=payload.amount_cents,
            currency_code=listing.currency_code,
            status=OfferStatus.pending_approval.value,
            note=payload.note,
        )
        session.add(offer)
        await session.flush()
        approval = await create_approval_request(
            session,
            owner_user_id=user.id,
            requested_by_user_id=user.id,
            agent_grant_id=grant.id if grant else None,
            action_type="create_offer",
            resource_type="offer",
            resource_id=offer.id,
            summary=f"Create offer for {payload.amount_cents} cents on listing '{listing.title}'.",
            diff_payload={"amount_cents": payload.amount_cents, "note": payload.note},
            action_payload={"offer_id": offer.id},
            idempotency_key=payload.idempotency_key,
        )
        offer.approval_request_id = approval.id
        await session.commit()
        return {"offer_id": offer.id, "approval_request_id": approval.id, "status": offer.status}


@mcp.tool
async def counter_offer(access_token: str, offer_id: str, amount_cents: int, note: str | None = None, idempotency_key: str | None = None) -> dict:
    user, grant = await _resolve_actor_context(access_token)
    payload = OfferCounterRequest(amount_cents=amount_cents, note=note, idempotency_key=idempotency_key)
    async with SessionLocal() as session:
        target_offer = await session.scalar(
            select(Offer).where(Offer.id == offer_id, ((Offer.buyer_id == user.id) | (Offer.seller_id == user.id)))
        )
        if not target_offer:
            raise ValueError("Offer not found.")
        counter = Offer(
            thread_id=target_offer.thread_id,
            listing_id=target_offer.listing_id,
            buyer_id=target_offer.buyer_id,
            seller_id=target_offer.seller_id,
            created_by_user_id=user.id,
            supersedes_offer_id=target_offer.id,
            amount_cents=payload.amount_cents,
            currency_code=target_offer.currency_code,
            status=OfferStatus.pending_approval.value,
            note=payload.note,
        )
        session.add(counter)
        await session.flush()
        approval = await create_approval_request(
            session,
            owner_user_id=user.id,
            requested_by_user_id=user.id,
            agent_grant_id=grant.id if grant else None,
            action_type="counter_offer",
            resource_type="offer",
            resource_id=counter.id,
            summary=f"Counter offer {target_offer.id[:8]} with {payload.amount_cents} cents.",
            diff_payload={"from_amount_cents": target_offer.amount_cents, "to_amount_cents": payload.amount_cents},
            action_payload={"offer_id": counter.id, "target_offer_id": target_offer.id},
            idempotency_key=payload.idempotency_key,
        )
        counter.approval_request_id = approval.id
        await session.commit()
        return {"offer_id": counter.id, "approval_request_id": approval.id, "status": counter.status}


@mcp.tool
async def accept_offer(access_token: str, offer_id: str, idempotency_key: str | None = None) -> dict:
    user, grant = await _resolve_actor_context(access_token)
    _ = OfferDecisionRequest(idempotency_key=idempotency_key)
    async with SessionLocal() as session:
        offer = await session.scalar(
            select(Offer).where(Offer.id == offer_id, ((Offer.buyer_id == user.id) | (Offer.seller_id == user.id)))
        )
        if not offer:
            raise ValueError("Offer not found.")
        approval = await create_approval_request(
            session,
            owner_user_id=user.id,
            requested_by_user_id=user.id,
            agent_grant_id=grant.id if grant else None,
            action_type="accept_offer",
            resource_type="offer",
            resource_id=offer.id,
            summary=f"Accept offer {offer.id[:8]} for {offer.amount_cents} cents.",
            diff_payload={"from_status": offer.status, "to_status": "accepted"},
            action_payload={"offer_id": offer.id},
            idempotency_key=idempotency_key,
        )
        await session.commit()
        return {"offer_id": offer.id, "approval_request_id": approval.id, "status": offer.status}


@mcp.tool
async def reject_offer(access_token: str, offer_id: str, idempotency_key: str | None = None) -> dict:
    user, grant = await _resolve_actor_context(access_token)
    _ = OfferDecisionRequest(idempotency_key=idempotency_key)
    async with SessionLocal() as session:
        offer = await session.scalar(
            select(Offer).where(Offer.id == offer_id, ((Offer.buyer_id == user.id) | (Offer.seller_id == user.id)))
        )
        if not offer:
            raise ValueError("Offer not found.")
        approval = await create_approval_request(
            session,
            owner_user_id=user.id,
            requested_by_user_id=user.id,
            agent_grant_id=grant.id if grant else None,
            action_type="reject_offer",
            resource_type="offer",
            resource_id=offer.id,
            summary=f"Reject offer {offer.id[:8]}.",
            diff_payload={"from_status": offer.status, "to_status": "rejected"},
            action_payload={"offer_id": offer.id},
            idempotency_key=idempotency_key,
        )
        await session.commit()
        return {"offer_id": offer.id, "approval_request_id": approval.id, "status": offer.status}


@mcp.tool
async def list_approval_requests(access_token: str) -> list[dict]:
    user = await _resolve_actor(access_token)
    async with SessionLocal() as session:
        approvals = (
            await session.scalars(
                select(ApprovalRequest).where(ApprovalRequest.owner_user_id == user.id).order_by(ApprovalRequest.created_at.desc())
            )
        ).all()
        return [
            {
                "id": approval.id,
                "status": approval.status,
                "action_type": approval.action_type,
                "resource_type": approval.resource_type,
                "resource_id": approval.resource_id,
                "summary": approval.summary,
                "created_at": approval.created_at.isoformat(),
            }
            for approval in approvals
        ]


@mcp.tool
async def list_action_receipts(access_token: str) -> list[dict]:
    user = await _resolve_actor(access_token)
    async with SessionLocal() as session:
        receipts = (
            await session.scalars(
                select(ActionReceipt).where(ActionReceipt.owner_user_id == user.id).order_by(ActionReceipt.created_at.desc())
            )
        ).all()
        return [
            {
                "id": receipt.id,
                "action_type": receipt.action_type,
                "resource_type": receipt.resource_type,
                "resource_id": receipt.resource_id,
                "status": receipt.status,
                "result_payload": receipt.result_payload,
            }
            for receipt in receipts
        ]


@mcp.tool
async def prepare_seller_action(
    access_token: str,
    action_type: str,
    draft_id: str | None = None,
    listing_id: str | None = None,
    order_id: str | None = None,
    new_price_cents: int | None = None,
    status: str | None = None,
    carrier: str | None = None,
    tracking_number: str | None = None,
    summary: str | None = None,
    idempotency_key: str | None = None,
) -> dict:
    user, grant = await _resolve_actor_context(access_token)
    payload = ApprovalActionPrepareRequest(
        action_type=action_type,
        draft_id=draft_id,
        listing_id=listing_id,
        order_id=order_id,
        new_price_cents=new_price_cents,
        status=status,
        carrier=carrier,
        tracking_number=tracking_number,
        summary=summary,
        idempotency_key=idempotency_key,
    )
    async with SessionLocal() as session:
        diff_payload: dict[str, object]
        resource_type: str
        resource_id: str | None
        action_payload: dict[str, object]
        approval_summary: str

        if payload.action_type == "publish_listing":
            if not payload.draft_id:
                raise ValueError("draft_id is required.")
            draft = await session.scalar(select(ListingDraft).where(ListingDraft.id == payload.draft_id, ListingDraft.seller_id == user.id))
            if not draft:
                raise ValueError("Draft not found.")
            resource_type = "draft"
            resource_id = draft.id
            approval_summary = payload.summary or f"Publish listing draft '{draft.title or draft.product_name or draft.id}'."
            diff_payload = {"title": draft.title, "product_name": draft.product_name, "asking_price_cents": draft.asking_price_cents}
            action_payload = {"draft_id": draft.id}
        elif payload.action_type == "reprice_listing":
            if not payload.listing_id or payload.new_price_cents is None:
                raise ValueError("listing_id and new_price_cents are required.")
            listing = await session.scalar(select(Listing).where(Listing.id == payload.listing_id, Listing.seller_id == user.id))
            if not listing:
                raise ValueError("Listing not found.")
            resource_type = "listing"
            resource_id = listing.id
            approval_summary = payload.summary or f"Reprice listing '{listing.title}' to {payload.new_price_cents} cents."
            diff_payload = {"from_price_cents": listing.asking_price_cents, "to_price_cents": payload.new_price_cents}
            action_payload = {"listing_id": listing.id, "new_price_cents": payload.new_price_cents}
        elif payload.action_type == "cancel_order":
            if not payload.order_id:
                raise ValueError("order_id is required.")
            order = await session.scalar(select(Order).where(Order.id == payload.order_id, Order.seller_id == user.id))
            if not order:
                raise ValueError("Order not found.")
            resource_type = "order"
            resource_id = order.id
            approval_summary = payload.summary or f"Cancel order {order.id}."
            diff_payload = {"from_status": order.status, "to_status": "cancelled"}
            action_payload = {"order_id": order.id}
        elif payload.action_type == "update_fulfillment":
            if not payload.order_id or not payload.status:
                raise ValueError("order_id and status are required.")
            order = await session.scalar(select(Order).where(Order.id == payload.order_id, Order.seller_id == user.id))
            if not order:
                raise ValueError("Order not found.")
            resource_type = "order"
            resource_id = order.id
            approval_summary = payload.summary or f"Update order {order.id} to fulfillment status '{payload.status}'."
            diff_payload = {
                "from_status": order.status,
                "to_status": payload.status,
                "carrier": payload.carrier,
                "tracking_number": payload.tracking_number,
            }
            action_payload = {
                "order_id": order.id,
                "status": payload.status,
                "carrier": payload.carrier,
                "tracking_number": payload.tracking_number,
            }
        else:
            raise ValueError(f"Unsupported approval action: {payload.action_type}")

        approval = await create_approval_request(
            session,
            owner_user_id=user.id,
            requested_by_user_id=user.id,
            agent_grant_id=grant.id if grant else None,
            action_type=payload.action_type,
            resource_type=resource_type,
            resource_id=resource_id,
            summary=approval_summary,
            diff_payload=diff_payload,
            action_payload=action_payload,
            idempotency_key=payload.idempotency_key,
        )
        await session.commit()
        return {"approval_request_id": approval.id, "status": approval.status, "summary": approval.summary}
