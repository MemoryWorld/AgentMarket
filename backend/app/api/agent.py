from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthActor, check_scopes, require_human, require_scopes
from app.core.security import create_personal_access_token, utcnow
from app.db.session import get_session
from app.models import (
    ActionReceipt,
    AgentGrant,
    ApprovalRequest,
    Listing,
    ListingDraft,
    Order,
    PersonalAccessToken,
)
from app.models.entities import AgentGrantStatus
from app.schemas.domain import (
    ActionReceiptResponse,
    AgentGrantCreateRequest,
    AgentGrantCreateResponse,
    AgentGrantResponse,
    ApprovalActionPrepareRequest,
    ApprovalDecisionResponse,
    ApprovalRequestResponse,
)
from app.services.approval_ops import (
    begin_preparation,
    create_approval_request,
    execute_approval_request,
    reject_approval_request,
)
from app.services.marketplace_ops import draft_snapshot

DEFAULT_AGENT_SCOPES = [
    "listings:write",
    "orders:write",
    "messages:read",
    "messages:write",
    "offers:read",
    "offers:write",
    "approvals:read",
    "approvals:write",
    "receipts:read",
]


grant_router = APIRouter(prefix="/agent-grants", tags=["agent-grants"])
approval_router = APIRouter(prefix="/approval-requests", tags=["approval-requests"])
receipt_router = APIRouter(prefix="/action-receipts", tags=["action-receipts"])


async def _get_approval_for_owner(session: AsyncSession, owner_user_id: str, approval_id: str) -> ApprovalRequest:
    approval = await session.scalar(
        select(ApprovalRequest).where(ApprovalRequest.id == approval_id, ApprovalRequest.owner_user_id == owner_user_id)
    )
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")
    return approval


async def _load_listing_for_seller(session: AsyncSession, seller_id: str, listing_id: str) -> Listing:
    listing = await session.scalar(select(Listing).where(Listing.id == listing_id, Listing.seller_id == seller_id))
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")
    return listing


async def _load_draft_for_seller(session: AsyncSession, seller_id: str, draft_id: str) -> ListingDraft:
    draft = await session.scalar(select(ListingDraft).where(ListingDraft.id == draft_id, ListingDraft.seller_id == seller_id).options(selectinload(ListingDraft.images)))
    if not draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Draft not found.")
    return draft


async def _load_order_for_seller(session: AsyncSession, seller_id: str, order_id: str) -> Order:
    order = await session.scalar(select(Order).where(Order.id == order_id, Order.seller_id == seller_id))
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return order


@grant_router.get("", response_model=list[AgentGrantResponse])
async def list_agent_grants(
    actor: AuthActor = Depends(require_scopes("grants:read")),
    session: AsyncSession = Depends(get_session),
) -> list[AgentGrantResponse]:
    grants = (await session.scalars(select(AgentGrant).where(AgentGrant.user_id == actor.user.id).order_by(AgentGrant.created_at.desc()))).all()
    return [AgentGrantResponse.model_validate(grant) for grant in grants]


@grant_router.post("", response_model=AgentGrantCreateResponse)
async def create_agent_grant(
    payload: AgentGrantCreateRequest,
    actor: AuthActor = Depends(require_human("grants:write")),
    session: AsyncSession = Depends(get_session),
) -> AgentGrantCreateResponse:
    scopes = payload.scopes or DEFAULT_AGENT_SCOPES
    check_scopes(actor, *scopes)
    if payload.approval_mode != "prepare_then_confirm":
        raise HTTPException(status_code=400, detail="Only prepare_then_confirm approval mode is supported.")
    token, prefix, token_hash = create_personal_access_token()
    pat = PersonalAccessToken(
        user_id=actor.user.id,
        name=payload.name,
        token_prefix=prefix,
        token_hash=token_hash,
        scopes=scopes,
    )
    session.add(pat)
    await session.flush()
    grant = AgentGrant(
        user_id=actor.user.id,
        personal_access_token_id=pat.id,
        name=payload.name,
        agent_family=payload.agent_family,
        scopes=scopes,
        approval_mode=payload.approval_mode,
    )
    session.add(grant)
    await session.commit()
    await session.refresh(grant)
    grant_payload = AgentGrantResponse.model_validate(grant).model_dump()
    return AgentGrantCreateResponse(**grant_payload, token=token, token_prefix=prefix)


@grant_router.post("/{grant_id}/revoke", response_model=AgentGrantResponse)
async def revoke_agent_grant(
    grant_id: str,
    actor: AuthActor = Depends(require_human("grants:write")),
    session: AsyncSession = Depends(get_session),
) -> AgentGrantResponse:
    grant = await session.scalar(select(AgentGrant).where(AgentGrant.id == grant_id, AgentGrant.user_id == actor.user.id))
    if not grant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent grant not found.")
    grant.status = AgentGrantStatus.revoked.value
    grant.revoked_at = utcnow()
    pat = await session.get(PersonalAccessToken, grant.personal_access_token_id)
    if pat:
        pat.revoked = True
    await session.commit()
    await session.refresh(grant)
    return AgentGrantResponse.model_validate(grant)


@approval_router.get("", response_model=list[ApprovalRequestResponse])
async def list_approval_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    actor: AuthActor = Depends(require_scopes("approvals:read")),
    session: AsyncSession = Depends(get_session),
) -> list[ApprovalRequestResponse]:
    stmt = select(ApprovalRequest).where(ApprovalRequest.owner_user_id == actor.user.id).order_by(ApprovalRequest.created_at.desc())
    if status_filter:
        stmt = stmt.where(ApprovalRequest.status == status_filter)
    approvals = (await session.scalars(stmt.limit(100))).all()
    return [ApprovalRequestResponse.model_validate(item) for item in approvals]


@approval_router.post("", response_model=ApprovalRequestResponse)
async def prepare_approval_request(
    payload: ApprovalActionPrepareRequest,
    actor: AuthActor = Depends(require_scopes("approvals:write")),
    session: AsyncSession = Depends(get_session),
) -> ApprovalRequestResponse:
    required = "listings:write" if payload.action_type in {"publish_listing", "reprice_listing"} else "orders:write"
    check_scopes(actor, "approvals:write", required)
    existing, fingerprint = await begin_preparation(session, actor, payload.action_type, payload)
    if existing:
        return ApprovalRequestResponse.model_validate(existing)
    action_payload: dict[str, object]
    diff_payload: dict[str, object]
    resource_type: str
    resource_id: str | None
    summary: str

    if payload.action_type == "publish_listing":
        if not payload.draft_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="draft_id is required.")
        draft = await _load_draft_for_seller(session, actor.user.id, payload.draft_id)
        resource_type = "draft"
        resource_id = draft.id
        summary = payload.summary or f"Publish listing draft '{draft.title or draft.product_name or draft.id}'."
        diff_payload = {
            "title": draft.title,
            "product_name": draft.product_name,
            "asking_price_cents": draft.asking_price_cents,
        }
        action_payload = {"draft_id": draft.id, "draft_snapshot": draft_snapshot(draft)}
    elif payload.action_type == "reprice_listing":
        if not payload.listing_id or payload.new_price_cents is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="listing_id and new_price_cents are required.")
        listing = await _load_listing_for_seller(session, actor.user.id, payload.listing_id)
        resource_type = "listing"
        resource_id = listing.id
        summary = payload.summary or f"Reprice listing '{listing.title}' to {payload.new_price_cents} cents."
        diff_payload = {"from_price_cents": listing.asking_price_cents, "to_price_cents": payload.new_price_cents}
        action_payload = {"listing_id": listing.id, "new_price_cents": payload.new_price_cents}
    elif payload.action_type == "cancel_order":
        if not payload.order_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order_id is required.")
        order = await _load_order_for_seller(session, actor.user.id, payload.order_id)
        resource_type = "order"
        resource_id = order.id
        summary = payload.summary or f"Cancel order {order.id}."
        diff_payload = {"from_status": order.status, "to_status": "cancelled"}
        action_payload = {"order_id": order.id}
    elif payload.action_type == "update_fulfillment":
        if not payload.order_id or not payload.status:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order_id and status are required.")
        order = await _load_order_for_seller(session, actor.user.id, payload.order_id)
        resource_type = "order"
        resource_id = order.id
        summary = payload.summary or f"Update order {order.id} to fulfillment status '{payload.status}'."
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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported approval action: {payload.action_type}")

    approval = await create_approval_request(
        session,
        owner_user_id=actor.user.id,
        requested_by_user_id=actor.user.id,
        agent_grant_id=actor.agent_grant.id if actor.agent_grant else None,
        action_type=payload.action_type,
        resource_type=resource_type,
        resource_id=resource_id,
        summary=summary,
        diff_payload=diff_payload,
        action_payload=action_payload,
        idempotency_key=payload.idempotency_key,
        request_fingerprint=fingerprint,
    )
    await session.commit()
    await session.refresh(approval)
    return ApprovalRequestResponse.model_validate(approval)


@approval_router.post("/{approval_id}/approve", response_model=ApprovalDecisionResponse)
async def approve_request(
    approval_id: str,
    actor: AuthActor = Depends(require_human("approvals:write")),
    session: AsyncSession = Depends(get_session),
) -> ApprovalDecisionResponse:
    approval = await _get_approval_for_owner(session, actor.user.id, approval_id)
    try:
        receipt = await execute_approval_request(session, approval, actor.user.id)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    if receipt.status == "failed":
        raise HTTPException(status_code=400, detail=receipt.error_message)
    await session.refresh(approval)
    return ApprovalDecisionResponse(
        approval_request=ApprovalRequestResponse.model_validate(approval),
        receipt=ActionReceiptResponse.model_validate(receipt),
    )


@approval_router.post("/{approval_id}/reject", response_model=ApprovalDecisionResponse)
async def reject_request(
    approval_id: str,
    actor: AuthActor = Depends(require_human("approvals:write")),
    session: AsyncSession = Depends(get_session),
) -> ApprovalDecisionResponse:
    approval = await _get_approval_for_owner(session, actor.user.id, approval_id)
    try:
        receipt = await reject_approval_request(session, approval, actor.user.id)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    await session.refresh(approval)
    return ApprovalDecisionResponse(
        approval_request=ApprovalRequestResponse.model_validate(approval),
        receipt=ActionReceiptResponse.model_validate(receipt),
    )


@receipt_router.get("", response_model=list[ActionReceiptResponse])
async def list_action_receipts(
    action_type: str | None = Query(default=None),
    actor: AuthActor = Depends(require_scopes("receipts:read")),
    session: AsyncSession = Depends(get_session),
) -> list[ActionReceiptResponse]:
    stmt = select(ActionReceipt).where(ActionReceipt.owner_user_id == actor.user.id).order_by(ActionReceipt.created_at.desc())
    if action_type:
        stmt = stmt.where(ActionReceipt.action_type == action_type)
    receipts = (await session.scalars(stmt.limit(100))).all()
    return [ActionReceiptResponse.model_validate(receipt) for receipt in receipts]
