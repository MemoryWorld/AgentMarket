from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import utcnow
from app.models import ActionReceipt, ApprovalRequest, Listing, ListingDraft, MessageEvent, MessageThread, Offer, Order
from app.models.entities import (
    ActionReceiptStatus,
    ApprovalRequestStatus,
    MessageEventStatus,
    OfferStatus,
    OrderStatus,
)
from app.services.marketplace_ops import publish_draft_listing


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
            ApprovalRequest.idempotency_key == idempotency_key,
        )
    )


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
) -> ApprovalRequest:
    existing = await find_existing_approval(session, owner_user_id, idempotency_key)
    if existing:
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


async def execute_approval_request(session: AsyncSession, approval: ApprovalRequest, actor_user_id: str) -> ActionReceipt:
    if approval.status == ApprovalRequestStatus.executed.value:
        existing = await session.scalar(select(ActionReceipt).where(ActionReceipt.approval_request_id == approval.id))
        if existing:
            return existing
    if approval.status != ApprovalRequestStatus.pending.value:
        raise ValueError("Approval request is not pending.")

    approval.decided_at = utcnow()

    try:
        resource_type, resource_id, result_payload = await _dispatch_action(session, approval)
        approval.status = ApprovalRequestStatus.executed.value
        approval.executed_at = utcnow()
        receipt = await _record_receipt(
            session,
            approval=approval,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            status=ActionReceiptStatus.succeeded.value,
            result_payload=result_payload,
        )
    except Exception as exc:
        approval.status = ApprovalRequestStatus.failed.value
        receipt = await _record_receipt(
            session,
            approval=approval,
            actor_user_id=actor_user_id,
            resource_type=approval.resource_type,
            resource_id=approval.resource_id,
            status=ActionReceiptStatus.failed.value,
            result_payload={},
            error_message=str(exc),
        )
        raise

    return receipt


async def reject_approval_request(session: AsyncSession, approval: ApprovalRequest, actor_user_id: str) -> ActionReceipt:
    if approval.status == ApprovalRequestStatus.rejected.value:
        existing = await session.scalar(select(ActionReceipt).where(ActionReceipt.approval_request_id == approval.id))
        if existing:
            return existing
    if approval.status != ApprovalRequestStatus.pending.value:
        raise ValueError("Approval request is not pending.")

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
        if not message:
            raise ValueError("Message draft not found.")
        if message.status != MessageEventStatus.pending_approval.value:
            raise ValueError("Message draft is not awaiting approval.")
        message.status = MessageEventStatus.sent.value
        thread = await session.get(MessageThread, message.thread_id)
        if thread:
            thread.last_message_at = utcnow()
        return "message", message.id, {"message_id": message.id, "status": message.status}

    if action_type in {"create_offer", "counter_offer"}:
        offer = await session.get(Offer, approval.resource_id)
        if not offer:
            raise ValueError("Offer draft not found.")
        if offer.status != OfferStatus.pending_approval.value:
            raise ValueError("Offer draft is not awaiting approval.")
        if action_type == "counter_offer" and payload.get("target_offer_id"):
            target_offer = await session.get(Offer, payload["target_offer_id"])
            if not target_offer:
                raise ValueError("Target offer not found.")
            target_offer.status = OfferStatus.countered.value
        offer.status = OfferStatus.pending.value
        return "offer", offer.id, {"offer_id": offer.id, "status": offer.status}

    if action_type == "accept_offer":
        offer = await session.get(Offer, payload.get("offer_id") or approval.resource_id)
        if not offer:
            raise ValueError("Offer not found.")
        if offer.status != OfferStatus.pending.value:
            raise ValueError("Only pending offers can be accepted.")
        offer.status = OfferStatus.accepted.value
        return "offer", offer.id, {"offer_id": offer.id, "status": offer.status}

    if action_type == "reject_offer":
        offer = await session.get(Offer, payload.get("offer_id") or approval.resource_id)
        if not offer:
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
        if not draft:
            raise ValueError("Draft not found.")
        listing = await publish_draft_listing(session, approval.owner_user_id, draft)
        return "listing", listing.id, {"listing_id": listing.id, "slug": listing.slug}

    if action_type == "reprice_listing":
        listing = await session.get(Listing, payload.get("listing_id") or approval.resource_id)
        if not listing:
            raise ValueError("Listing not found.")
        new_price_cents = payload.get("new_price_cents")
        if new_price_cents is None:
            raise ValueError("New price is required.")
        listing.asking_price_cents = new_price_cents
        return "listing", listing.id, {"listing_id": listing.id, "asking_price_cents": listing.asking_price_cents}

    if action_type == "cancel_order":
        order = await session.get(Order, payload.get("order_id") or approval.resource_id)
        if not order:
            raise ValueError("Order not found.")
        if order.status in {OrderStatus.shipped.value, OrderStatus.delivered.value}:
            raise ValueError("Shipped orders cannot be cancelled.")
        order.status = OrderStatus.cancelled.value
        return "order", order.id, {"order_id": order.id, "status": order.status}

    if action_type == "update_fulfillment":
        order = await session.get(Order, payload.get("order_id") or approval.resource_id)
        if not order:
            raise ValueError("Order not found.")
        next_status = payload.get("status")
        if not next_status:
            raise ValueError("Fulfillment status is required.")
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
