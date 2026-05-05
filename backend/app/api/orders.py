from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthActor, get_current_actor, require_scopes
from app.db.session import get_session
from app.models import Listing, Order
from app.models.entities import OrderStatus
from app.schemas.domain import OrderAddressRequest, OrderCreateRequest, OrderPaymentResponse, OrderResponse, OrderStatusUpdateRequest


router = APIRouter(prefix="/orders", tags=["orders"])


async def _get_order_for_actor(session: AsyncSession, actor: AuthActor, order_id: str) -> Order:
    order = await session.scalar(
        select(Order).where(
            Order.id == order_id,
            or_(Order.buyer_id == actor.user.id, Order.seller_id == actor.user.id),
        )
    )
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return order


@router.post("", response_model=OrderResponse)
async def create_order(
    payload: OrderCreateRequest,
    actor: AuthActor = Depends(require_scopes("orders:write")),
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    listing = await session.get(Listing, payload.listing_id)
    if not listing:
        listing = await session.scalar(select(Listing).where(Listing.slug == payload.listing_id))
    if not listing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found.")
    order = Order(
        listing_id=listing.id,
        buyer_id=actor.user.id,
        seller_id=listing.seller_id,
        status=OrderStatus.address_pending.value,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return OrderResponse.model_validate(order)


@router.patch("/{order_id}/address", response_model=OrderResponse)
async def submit_address(
    order_id: str,
    payload: OrderAddressRequest,
    actor: AuthActor = Depends(require_scopes("orders:write")),
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    order = await _get_order_for_actor(session, actor, order_id)
    if order.buyer_id != actor.user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the buyer can submit shipping address.")
    order.address_payload = payload.address.model_dump()
    order.status = OrderStatus.payment_pending.value
    await session.commit()
    await session.refresh(order)
    return OrderResponse.model_validate(order)


@router.post("/{order_id}/mock-pay", response_model=OrderPaymentResponse)
async def mock_pay(
    order_id: str,
    actor: AuthActor = Depends(require_scopes("orders:write")),
    session: AsyncSession = Depends(get_session),
) -> OrderPaymentResponse:
    order = await _get_order_for_actor(session, actor, order_id)
    if order.buyer_id != actor.user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the buyer can complete mock checkout.")
    if not order.address_payload:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shipping address must be submitted first.")
    order.status = OrderStatus.paid.value
    await session.commit()
    return OrderPaymentResponse(success=True, status=order.status)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str,
    actor: AuthActor = Depends(get_current_actor),
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    order = await _get_order_for_actor(session, actor, order_id)
    return OrderResponse.model_validate(order)


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: str,
    actor: AuthActor = Depends(require_scopes("orders:write")),
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    order = await _get_order_for_actor(session, actor, order_id)
    if order.status in {OrderStatus.shipped.value, OrderStatus.delivered.value}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shipped orders cannot be cancelled.")
    order.status = OrderStatus.cancelled.value
    await session.commit()
    await session.refresh(order)
    return OrderResponse.model_validate(order)


@router.patch("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: str,
    payload: OrderStatusUpdateRequest,
    actor: AuthActor = Depends(require_scopes("orders:write")),
    session: AsyncSession = Depends(get_session),
) -> OrderResponse:
    order = await _get_order_for_actor(session, actor, order_id)
    if order.seller_id != actor.user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the seller can update fulfillment status.")
    order.status = payload.status
    order.carrier = payload.carrier
    order.tracking_number = payload.tracking_number
    await session.commit()
    await session.refresh(order)
    return OrderResponse.model_validate(order)
