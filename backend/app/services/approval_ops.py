import hashlib
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import utcnow
from app.models import (
    ActionReceipt,
    AgentGrant,
    ApprovalRequest,
    Listing,
    ListingDraft,
    MessageEvent,
    MessageThread,
    Offer,
    Order,
    PersonalAccessToken,
    User,
)
from app.models.entities import (
    ActionReceiptStatus,
    ApprovalRequestStatus,
    MessageEventStatus,
    OfferStatus,
    OrderStatus,
)
from app.services.marketplace_ops import (
    draft_snapshot,
    publish_draft_listing,
    validate_fulfillment_transition,
)


async def find_existing_approval(
    session: AsyncSession,
    owner_user_id: str,
    idempotency_key: str | None,
) -> ApprovalRequest | None:
    if not idempotency_key:
        return None
    return await session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.owner_user_id == owner_user_id,
            ApprovalRequest.idempotency_slot == idempotency_key,
        )
    )


async def begin_preparation(session: AsyncSession, actor, action_type: str, payload, **target):
    """Lock before creating drafts, so replay cannot leave orphan business rows.

    The UPDATE also starts a real SQLite transaction before any SAVEPOINT.
    Authentication has read only (or already committed last_used_at).
    """
    owner_id = actor.user.id
    await session.commit()
    await session.execute(update(User).where(User.id == owner_id).values(id=User.id))
    normalized = {
        "action": action_type,
        "target": target,
        "payload": payload.model_dump(exclude={"idempotency_key"}),
        "grant_id": actor.agent_grant.id if actor.agent_grant else None,
    }
    fingerprint = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = await find_existing_approval(session, owner_id, payload.idempotency_key)
    if not existing and payload.idempotency_key:
        legacy = await session.scalar(select(ApprovalRequest.id).where(
            ApprovalRequest.owner_user_id == owner_id,
            ApprovalRequest.idempotency_key == payload.idempotency_key,
        ).limit(1))
        if legacy:
            raise HTTPException(status_code=409, detail="Historical duplicate key is retained for audit only; use a new idempotency key.")
    if existing and existing.request_fingerprint != fingerprint:
        raise HTTPException(status_code=409, detail="Idempotency key already used for a different request, or a legacy request whose contents cannot be verified.")
    return existing, fingerprint


async def create_approval_request(
    session: AsyncSession,
    *,
    owner_user_id: str,
    requested_by_user_id: str,
    agent_grant_id: str | None,
    action_type: str,
    resource_type: str,
    resource_id: str | None,
    summary: str,
    diff_payload: dict[str, Any],
    action_payload: dict[str, Any],
    idempotency_key: str | None,
    request_fingerprint: str,
) -> ApprovalRequest:
    existing = await find_existing_approval(session, owner_user_id, idempotency_key)
    if existing:
        if existing.request_fingerprint != request_fingerprint:
            raise HTTPException(status_code=409, detail="Idempotency key already used for a different request.")
        return existing

    approval = ApprovalRequest(
        owner_user_id=owner_user_id,
        requested_by_user_id=requested_by_user_id,
        agent_grant_id=agent_grant_id,
        action_type=action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        summary=summary,
        diff_payload=diff_payload,
        action_payload=action_payload,
        idempotency_key=idempotency_key,
        idempotency_slot=idempotency_key or None,
        request_fingerprint=request_fingerprint,
    )
    session.add(approval)
    await session.flush()
    return approval


async def _record_receipt(
    session: AsyncSession,
    *,
    approval: ApprovalRequest,
    actor_user_id: str | None,
    resource_type: str,
    resource_id: str | None,
    status: str,
    result_payload: dict[str, Any] | None = None,
    error_message: str | None = None,
) -> ActionReceipt:
    receipt = ActionReceipt(
        approval_request_id=approval.id,
        decision_slot=approval.id,
        owner_user_id=approval.owner_user_id,
        actor_user_id=actor_user_id,
        requested_by_user_id=approval.requested_by_user_id,
        agent_grant_id=approval.agent_grant_id,
        action_type=approval.action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        idempotency_key=approval.idempotency_key,
        result_payload=result_payload or {},
        error_message=error_message,
    )
    session.add(receipt)
    await session.flush()
    return receipt


async def _claim_decision(session: AsyncSession, approval: ApprovalRequest, actor_user_id: str, decision: str):
    if approval.owner_user_id != actor_user_id:
        raise HTTPException(status_code=404, detail="Approval request not found.")
    if approval.idempotency_key and not approval.idempotency_slot:
        raise HTTPException(status_code=409, detail="Historical duplicate approval is retained for audit only; prepare a new request.")
    # Release the read transaction before taking the owner write lock. All decisions
    # for one owner serialize, including different approvals for the same resource.
    owner_id, approval_id = approval.owner_user_id, approval.id
    await session.commit()
    await session.execute(update(User).where(User.id == owner_id).values(id=User.id))
    claimed = await session.execute(
        update(ApprovalRequest)
        .where(ApprovalRequest.id == approval_id, ApprovalRequest.owner_user_id == actor_user_id,
               ApprovalRequest.status == ApprovalRequestStatus.pending.value)
        .values(status="executing", decided_at=utcnow())
        .execution_options(synchronize_session=False)
    )
    await session.refresh(approval)
    if not claimed.rowcount:
        existing = await session.scalar(select(ActionReceipt).where(ActionReceipt.decision_slot == approval.id))
        replayable = {"approve": {"executed", "failed"}, "reject": {"rejected"}}
        if existing and approval.status in replayable[decision]:
            return existing
        raise HTTPException(status_code=409, detail="Approval request already has a different decision.")
    return None


async def execute_approval_request(session: AsyncSession, approval: ApprovalRequest, actor_user_id: str) -> ActionReceipt:
    existing = await _claim_decision(session, approval, actor_user_id, "approve")
    if existing:
        return existing
    try:
        async with session.begin_nested():
            if approval.agent_grant_id:
                grant = await session.get(AgentGrant, approval.agent_grant_id)
                pat = await session.get(PersonalAccessToken, grant.personal_access_token_id) if grant else None
                if not grant or grant.user_id != actor_user_id or grant.status != "active" or not pat or pat.revoked or pat.user_id != actor_user_id:
                    raise ValueError("Requesting agent grant is invalid or revoked.")
            resource_type, resource_id, result_payload = await _dispatch_action(session, approval)
            await session.flush()
    except Exception as exc:
        # Nested rollback removes every action write, even writes already flushed.
        # The failure receipt and terminal state remain in the caller's transaction.
        approval.status = ApprovalRequestStatus.failed.value
        return await _record_receipt(
            session,
            approval=approval,
            actor_user_id=actor_user_id,
            resource_type=approval.resource_type,
            resource_id=approval.resource_id,
            status=ActionReceiptStatus.failed.value,
            result_payload={},
            error_message=str(exc),
        )
    approval.status = ApprovalRequestStatus.executed.value
    approval.executed_at = utcnow()
    return await _record_receipt(
        session, approval=approval, actor_user_id=actor_user_id,
        resource_type=resource_type, resource_id=resource_id,
        status=ActionReceiptStatus.succeeded.value, result_payload=result_payload,
    )


async def reject_approval_request(session: AsyncSession, approval: ApprovalRequest, actor_user_id: str) -> ActionReceipt:
    existing = await _claim_decision(session, approval, actor_user_id, "reject")
    if existing:
        return existing
    approval.status = ApprovalRequestStatus.rejected.value
    approval.decided_at = utcnow()
    return await _record_receipt(
        session,
        approval=approval,
        actor_user_id=actor_user_id,
        resource_type=approval.resource_type,
        resource_id=approval.resource_id,
        status=ActionReceiptStatus.rejected.value,
        result_payload={"rejected": True},
    )


async def _dispatch_action(session: AsyncSession, approval: ApprovalRequest) -> tuple[str, str | None, dict[str, Any]]:
    payload = approval.action_payload
    action_type = approval.action_type

    if action_type == "send_message":
        message = await session.get(MessageEvent, approval.resource_id)
        if not message or message.sender_id != approval.owner_user_id or message.approval_request_id != approval.id:
            raise ValueError("Message draft not found.")
        if message.status != MessageEventStatus.pending_approval.value:
            raise ValueError("Message draft is not awaiting approval.")
        thread = await session.get(MessageThread, message.thread_id)
        if not thread or approval.owner_user_id not in {thread.buyer_id, thread.seller_id}:
            raise ValueError("Thread not found.")
        message.status = MessageEventStatus.sent.value
        thread.last_message_at = utcnow()
        return "message", message.id, {"message_id": message.id, "status": message.status}

    if action_type in {"create_offer", "counter_offer"}:
        offer = await session.get(Offer, approval.resource_id)
        if not offer or offer.created_by_user_id != approval.owner_user_id or offer.approval_request_id != approval.id:
            raise ValueError("Offer draft not found.")
        if offer.status != OfferStatus.pending_approval.value:
            raise ValueError("Offer draft is not awaiting approval.")
        if action_type == "counter_offer" and payload.get("target_offer_id"):
            target_offer = await session.get(Offer, payload["target_offer_id"])
            if (not target_offer or target_offer.thread_id != offer.thread_id
                    or target_offer.created_by_user_id == approval.owner_user_id
                    or target_offer.status != OfferStatus.pending.value):
                raise ValueError("Target offer not found.")
            target_offer.status = OfferStatus.countered.value
        offer.status = OfferStatus.pending.value
        return "offer", offer.id, {"offer_id": offer.id, "status": offer.status}

    if action_type == "accept_offer":
        offer = await session.get(Offer, payload.get("offer_id") or approval.resource_id)
        if not offer or approval.owner_user_id not in {offer.buyer_id, offer.seller_id} or offer.created_by_user_id == approval.owner_user_id:
            raise ValueError("Offer not found.")
        if offer.status != OfferStatus.pending.value:
            raise ValueError("Only pending offers can be accepted.")
        offer.status = OfferStatus.accepted.value
        return "offer", offer.id, {"offer_id": offer.id, "status": offer.status}

    if action_type == "reject_offer":
        offer = await session.get(Offer, payload.get("offer_id") or approval.resource_id)
        if not offer or approval.owner_user_id not in {offer.buyer_id, offer.seller_id} or offer.created_by_user_id == approval.owner_user_id:
            raise ValueError("Offer not found.")
        if offer.status not in {OfferStatus.pending.value, OfferStatus.pending_approval.value}:
            raise ValueError("Offer cannot be rejected in its current state.")
        offer.status = OfferStatus.rejected.value
        return "offer", offer.id, {"offer_id": offer.id, "status": offer.status}

    if action_type == "publish_listing":
        draft = await session.scalar(
            select(ListingDraft)
            .where(ListingDraft.id == (payload.get("draft_id") or approval.resource_id))
            .options(selectinload(ListingDraft.images))
        )
        if not draft or draft.seller_id != approval.owner_user_id:
            raise ValueError("Draft not found.")
        if payload.get("draft_snapshot") != draft_snapshot(draft):
            raise ValueError("Draft changed after preparation; prepare a new approval to review the current content.")
        listing = await publish_draft_listing(session, approval.owner_user_id, draft)
        return "listing", listing.id, {"listing_id": listing.id, "slug": listing.slug}

    if action_type == "reprice_listing":
        listing = await session.get(Listing, payload.get("listing_id") or approval.resource_id)
        if not listing or listing.seller_id != approval.owner_user_id:
            raise ValueError("Listing not found.")
        new_price_cents = payload.get("new_price_cents")
        if not isinstance(new_price_cents, int) or new_price_cents < 0:
            raise ValueError("New price is required.")
        listing.asking_price_cents = new_price_cents
        return "listing", listing.id, {"listing_id": listing.id, "asking_price_cents": listing.asking_price_cents}

    if action_type == "cancel_order":
        order = await session.get(Order, payload.get("order_id") or approval.resource_id)
        if not order or order.seller_id != approval.owner_user_id:
            raise ValueError("Order not found.")
        if order.status in {OrderStatus.shipped.value, OrderStatus.delivered.value}:
            raise ValueError("Shipped orders cannot be cancelled.")
        order.status = OrderStatus.cancelled.value
        return "order", order.id, {"order_id": order.id, "status": order.status}

    if action_type == "update_fulfillment":
        order = await session.get(Order, payload.get("order_id") or approval.resource_id)
        if not order or order.seller_id != approval.owner_user_id:
            raise ValueError("Order not found.")
        next_status = payload.get("status")
        if next_status not in {OrderStatus.confirmed.value, OrderStatus.shipped.value, OrderStatus.delivered.value}:
            raise ValueError("Invalid fulfillment status.")
        validate_fulfillment_transition(order.status, next_status)
        order.status = next_status
        order.carrier = payload.get("carrier")
        order.tracking_number = payload.get("tracking_number")
        return "order", order.id, {
            "order_id": order.id,
            "status": order.status,
            "carrier": order.carrier,
            "tracking_number": order.tracking_number,
        }

    raise ValueError(f"Unsupported approval action: {action_type}")
