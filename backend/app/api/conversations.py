from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthActor, require_scopes
from app.db.session import get_session
from app.models import Listing, MessageEvent, MessageThread, Offer
from app.models.entities import (
    MessageEventKind,
    MessageEventStatus,
    MessageThreadStatus,
    OfferStatus,
)
from app.schemas.domain import (
    MessageEventCreateRequest,
    MessageEventResponse,
    MessageThreadCreateRequest,
    MessageThreadResponse,
    OfferCounterRequest,
    OfferCreateRequest,
    OfferDecisionRequest,
    OfferResponse,
    ThreadDetailResponse,
)
from app.services.approval_ops import begin_preparation, create_approval_request

thread_router = APIRouter(prefix="/threads", tags=["threads"])
offer_router = APIRouter(prefix="/offers", tags=["offers"])


async def _get_thread_for_actor(session: AsyncSession, actor: AuthActor, thread_id: str) -> MessageThread:
    thread = await session.scalar(
        select(MessageThread)
        .where(
            MessageThread.id == thread_id,
            or_(MessageThread.buyer_id == actor.user.id, MessageThread.seller_id == actor.user.id),
        )
        .options(selectinload(MessageThread.messages), selectinload(MessageThread.offers))
    )
    if not thread:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found.")
    return thread


async def _get_offer_for_actor(session: AsyncSession, actor: AuthActor, offer_id: str) -> Offer:
    offer = await session.scalar(
        select(Offer)
        .where(
            Offer.id == offer_id,
            or_(Offer.buyer_id == actor.user.id, Offer.seller_id == actor.user.id),
        )
    )
    if not offer or (offer.status == "pending_approval" and offer.created_by_user_id != actor.user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found.")
    return offer


def _thread_response(thread: MessageThread, actor: AuthActor) -> ThreadDetailResponse:
    messages = sorted((item for item in thread.messages if item.sender_id == actor.user.id or item.status == "sent"), key=lambda item: item.created_at)
    offers = sorted((item for item in thread.offers if "offers:read" in actor.scopes and (item.created_by_user_id == actor.user.id or item.status != "pending_approval")), key=lambda item: item.created_at)
    return ThreadDetailResponse(
        id=thread.id,
        listing_id=thread.listing_id,
        seller_id=thread.seller_id,
        buyer_id=thread.buyer_id,
        subject=thread.subject,
        status=thread.status,
        last_message_at=thread.last_message_at,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=[MessageEventResponse.model_validate(item) for item in messages],
        offers=[OfferResponse.model_validate(item) for item in offers],
    )


@thread_router.get("", response_model=list[MessageThreadResponse])
async def list_threads(
    listing_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    actor: AuthActor = Depends(require_scopes("messages:read")),
    session: AsyncSession = Depends(get_session),
) -> list[MessageThreadResponse]:
    stmt = (
        select(MessageThread)
        .where(or_(MessageThread.buyer_id == actor.user.id, MessageThread.seller_id == actor.user.id))
        .order_by(MessageThread.updated_at.desc())
    )
    if listing_id:
        stmt = stmt.where(MessageThread.listing_id == listing_id)
    if status_filter:
        stmt = stmt.where(MessageThread.status == status_filter)
    threads = (await session.scalars(stmt.limit(100))).all()
    return [MessageThreadResponse.model_validate(thread) for thread in threads]


@thread_router.post("", response_model=MessageThreadResponse)
async def create_thread(
    payload: MessageThreadCreateRequest,
    actor: AuthActor = Depends(require_scopes("messages:write")),
    session: AsyncSession = Depends(get_session),
) -> MessageThreadResponse:
    listing = await session.get(Listing, payload.listing_id)
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")

    if actor.user.id == listing.seller_id:
        if not payload.participant_user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="participant_user_id is required for seller-created threads.")
        seller_id = actor.user.id
        buyer_id = payload.participant_user_id
    else:
        seller_id = listing.seller_id
        buyer_id = actor.user.id

    existing = await session.scalar(
        select(MessageThread).where(
            MessageThread.listing_id == listing.id,
            MessageThread.seller_id == seller_id,
            MessageThread.buyer_id == buyer_id,
            MessageThread.status == MessageThreadStatus.open.value,
        )
    )
    if existing:
        return MessageThreadResponse.model_validate(existing)

    thread = MessageThread(
        listing_id=listing.id,
        seller_id=seller_id,
        buyer_id=buyer_id,
        subject=payload.subject,
    )
    session.add(thread)
    await session.commit()
    await session.refresh(thread)
    return MessageThreadResponse.model_validate(thread)


@thread_router.get("/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread(
    thread_id: str,
    actor: AuthActor = Depends(require_scopes("messages:read")),
    session: AsyncSession = Depends(get_session),
) -> ThreadDetailResponse:
    thread = await _get_thread_for_actor(session, actor, thread_id)
    return _thread_response(thread, actor)


@thread_router.post("/{thread_id}/messages", response_model=MessageEventResponse)
async def create_message_draft(
    thread_id: str,
    payload: MessageEventCreateRequest,
    actor: AuthActor = Depends(require_scopes("messages:write", "approvals:write")),
    session: AsyncSession = Depends(get_session),
) -> MessageEventResponse:
    existing, fingerprint = await begin_preparation(session, actor, "send_message", payload, thread_id=thread_id)
    thread = await _get_thread_for_actor(session, actor, thread_id)
    if existing and existing.resource_type == "message" and existing.resource_id:
        message = await session.get(MessageEvent, existing.resource_id)
        if message:
            return MessageEventResponse.model_validate(message)

    message = MessageEvent(
        thread_id=thread.id,
        sender_id=actor.user.id,
        kind=MessageEventKind.user_message.value,
        status=MessageEventStatus.pending_approval.value,
        body=payload.body,
    )
    session.add(message)
    await session.flush()
    summary = f"Send message in thread {thread.id[:8]}."
    approval = await create_approval_request(
        session,
        owner_user_id=actor.user.id,
        requested_by_user_id=actor.user.id,
        agent_grant_id=actor.agent_grant.id if actor.agent_grant else None,
        action_type="send_message",
        resource_type="message",
        resource_id=message.id,
        summary=summary,
        diff_payload={"body_preview": payload.body[:180]},
        action_payload={"thread_id": thread.id, "message_id": message.id},
        idempotency_key=payload.idempotency_key,
        request_fingerprint=fingerprint,
    )
    message.approval_request_id = approval.id
    await session.commit()
    await session.refresh(message)
    return MessageEventResponse.model_validate(message)


@offer_router.get("", response_model=list[OfferResponse])
async def list_offers(
    thread_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    actor: AuthActor = Depends(require_scopes("offers:read")),
    session: AsyncSession = Depends(get_session),
) -> list[OfferResponse]:
    stmt = (
        select(Offer)
        .where(or_(Offer.buyer_id == actor.user.id, Offer.seller_id == actor.user.id))
        .order_by(Offer.created_at.desc())
    )
    if thread_id:
        stmt = stmt.where(Offer.thread_id == thread_id)
    if status_filter:
        stmt = stmt.where(Offer.status == status_filter)
    offers = (await session.scalars(stmt.limit(100))).all()
    return [OfferResponse.model_validate(offer) for offer in offers if offer.created_by_user_id == actor.user.id or offer.status != "pending_approval"]


@offer_router.post("", response_model=OfferResponse)
async def create_offer(
    payload: OfferCreateRequest,
    actor: AuthActor = Depends(require_scopes("offers:write", "approvals:write")),
    session: AsyncSession = Depends(get_session),
) -> OfferResponse:
    existing, fingerprint = await begin_preparation(session, actor, "create_offer", payload)
    thread = await _get_thread_for_actor(session, actor, payload.thread_id)
    listing = await session.get(Listing, thread.listing_id)
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")

    if existing and existing.resource_type == "offer" and existing.resource_id:
        offer = await session.get(Offer, existing.resource_id)
        if offer:
            return OfferResponse.model_validate(offer)

    offer = Offer(
        thread_id=thread.id,
        listing_id=thread.listing_id,
        buyer_id=thread.buyer_id,
        seller_id=thread.seller_id,
        created_by_user_id=actor.user.id,
        amount_cents=payload.amount_cents,
        currency_code=listing.currency_code,
        status=OfferStatus.pending_approval.value,
        note=payload.note,
    )
    session.add(offer)
    await session.flush()
    summary = f"Create offer for {payload.amount_cents} cents on listing '{listing.title}'."
    approval = await create_approval_request(
        session,
        owner_user_id=actor.user.id,
        requested_by_user_id=actor.user.id,
        agent_grant_id=actor.agent_grant.id if actor.agent_grant else None,
        action_type="create_offer",
        resource_type="offer",
        resource_id=offer.id,
        summary=summary,
        diff_payload={"amount_cents": payload.amount_cents, "note": payload.note},
        action_payload={"offer_id": offer.id},
        idempotency_key=payload.idempotency_key,
        request_fingerprint=fingerprint,
    )
    offer.approval_request_id = approval.id
    await session.commit()
    await session.refresh(offer)
    return OfferResponse.model_validate(offer)


@offer_router.post("/{offer_id}/accept", response_model=OfferResponse)
async def accept_offer(
    offer_id: str,
    payload: OfferDecisionRequest,
    actor: AuthActor = Depends(require_scopes("offers:write", "approvals:write")),
    session: AsyncSession = Depends(get_session),
) -> OfferResponse:
    existing, fingerprint = await begin_preparation(session, actor, "accept_offer", payload, offer_id=offer_id)
    offer = await _get_offer_for_actor(session, actor, offer_id)
    if offer.created_by_user_id == actor.user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot accept your own offer.")
    if existing:
        session.info["prepared_approval_id"] = existing.id
        return OfferResponse.model_validate(offer)
    approval = await create_approval_request(
        session,
        owner_user_id=actor.user.id,
        requested_by_user_id=actor.user.id,
        agent_grant_id=actor.agent_grant.id if actor.agent_grant else None,
        action_type="accept_offer",
        resource_type="offer",
        resource_id=offer.id,
        summary=f"Accept offer {offer.id[:8]} for {offer.amount_cents} cents.",
        diff_payload={"amount_cents": offer.amount_cents, "from_status": offer.status, "to_status": OfferStatus.accepted.value},
        action_payload={"offer_id": offer.id},
        idempotency_key=payload.idempotency_key,
        request_fingerprint=fingerprint,
    )
    session.info["prepared_approval_id"] = approval.id
    await session.commit()
    return OfferResponse.model_validate(offer)


@offer_router.post("/{offer_id}/reject", response_model=OfferResponse)
async def reject_offer(
    offer_id: str,
    payload: OfferDecisionRequest,
    actor: AuthActor = Depends(require_scopes("offers:write", "approvals:write")),
    session: AsyncSession = Depends(get_session),
) -> OfferResponse:
    existing, fingerprint = await begin_preparation(session, actor, "reject_offer", payload, offer_id=offer_id)
    offer = await _get_offer_for_actor(session, actor, offer_id)
    if offer.created_by_user_id == actor.user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot reject your own offer.")
    if existing:
        session.info["prepared_approval_id"] = existing.id
        return OfferResponse.model_validate(offer)
    approval = await create_approval_request(
        session,
        owner_user_id=actor.user.id,
        requested_by_user_id=actor.user.id,
        agent_grant_id=actor.agent_grant.id if actor.agent_grant else None,
        action_type="reject_offer",
        resource_type="offer",
        resource_id=offer.id,
        summary=f"Reject offer {offer.id[:8]}.",
        diff_payload={"from_status": offer.status, "to_status": OfferStatus.rejected.value},
        action_payload={"offer_id": offer.id},
        idempotency_key=payload.idempotency_key,
        request_fingerprint=fingerprint,
    )
    session.info["prepared_approval_id"] = approval.id
    await session.commit()
    return OfferResponse.model_validate(offer)


@offer_router.post("/{offer_id}/counter", response_model=OfferResponse)
async def counter_offer(
    offer_id: str,
    payload: OfferCounterRequest,
    actor: AuthActor = Depends(require_scopes("offers:write", "approvals:write")),
    session: AsyncSession = Depends(get_session),
) -> OfferResponse:
    existing, fingerprint = await begin_preparation(session, actor, "counter_offer", payload, offer_id=offer_id)
    target_offer = await _get_offer_for_actor(session, actor, offer_id)
    if target_offer.created_by_user_id == actor.user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot counter your own offer.")

    if existing and existing.resource_type == "offer" and existing.resource_id:
        offer = await session.get(Offer, existing.resource_id)
        if offer:
            return OfferResponse.model_validate(offer)

    counter = Offer(
        thread_id=target_offer.thread_id,
        listing_id=target_offer.listing_id,
        buyer_id=target_offer.buyer_id,
        seller_id=target_offer.seller_id,
        created_by_user_id=actor.user.id,
        approval_request_id=None,
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
        owner_user_id=actor.user.id,
        requested_by_user_id=actor.user.id,
        agent_grant_id=actor.agent_grant.id if actor.agent_grant else None,
        action_type="counter_offer",
        resource_type="offer",
        resource_id=counter.id,
        summary=f"Counter offer {target_offer.id[:8]} with {payload.amount_cents} cents.",
        diff_payload={
            "from_offer_id": target_offer.id,
            "from_amount_cents": target_offer.amount_cents,
            "to_amount_cents": payload.amount_cents,
        },
        action_payload={"offer_id": counter.id, "target_offer_id": target_offer.id},
        idempotency_key=payload.idempotency_key,
        request_fingerprint=fingerprint,
    )
    counter.approval_request_id = approval.id
    await session.commit()
    await session.refresh(counter)
    return OfferResponse.model_validate(counter)
