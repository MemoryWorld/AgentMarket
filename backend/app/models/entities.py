import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ListingWorkflowStatus(str, Enum):
    draft = "draft"
    pending_review = "pending_review"
    published = "published"
    archived = "archived"


class Visibility(str, Enum):
    public = "public"
    unlisted = "unlisted"
    private = "private"


class ImageProvenance(str, Enum):
    user_upload = "user_upload"
    ai_generated = "ai_generated"


class AIJobType(str, Enum):
    autofill = "autofill"
    sale_image = "sale_image"


class AIJobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"


class OrderStatus(str, Enum):
    initiated = "initiated"
    address_pending = "address_pending"
    payment_pending = "payment_pending"
    paid = "paid"
    confirmed = "confirmed"
    shipped = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"


class MessageThreadStatus(str, Enum):
    open = "open"
    closed = "closed"


class MessageEventKind(str, Enum):
    user_message = "user_message"
    system_note = "system_note"


class MessageEventStatus(str, Enum):
    pending_approval = "pending_approval"
    sent = "sent"
    rejected = "rejected"


class OfferStatus(str, Enum):
    pending_approval = "pending_approval"
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    countered = "countered"
    expired = "expired"
    cancelled = "cancelled"


class ApprovalRequestStatus(str, Enum):
    pending = "pending"
    rejected = "rejected"
    executed = "executed"
    failed = "failed"


class ActionReceiptStatus(str, Enum):
    succeeded = "succeeded"
    rejected = "rejected"
    failed = "failed"


class AgentGrantStatus(str, Enum):
    active = "active"
    revoked = "revoked"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120))
    city_slug: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2), default="US")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    seller_profile: Mapped["SellerProfile"] = relationship(back_populates="user", uselist=False)
    wallets: Mapped[list["CreditWallet"]] = relationship(back_populates="user")
    tokens: Mapped[list["PersonalAccessToken"]] = relationship(back_populates="user")
    agent_grants: Mapped[list["AgentGrant"]] = relationship(back_populates="user")


class SellerProfile(Base):
    __tablename__ = "seller_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True)
    handle: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="seller_profile")


class CreditWallet(Base):
    __tablename__ = "credit_wallets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True)
    balance_credits: Mapped[int] = mapped_column(Integer, default=20)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped[User] = relationship(back_populates="wallets")


class UsageLedger(Base):
    __tablename__ = "usage_ledgers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    delta_credits: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(255))
    reference_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reference_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EmailOTP(Base):
    __tablename__ = "email_otps"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class PersonalAccessToken(Base):
    __tablename__ = "personal_access_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    token_prefix: Mapped[str] = mapped_column(String(20), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="tokens")
    agent_grant: Mapped["AgentGrant | None"] = relationship(back_populates="personal_access_token", uselist=False)


class Category(Base):
    __tablename__ = "categories"

    slug: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    parent_slug: Mapped[str | None] = mapped_column(String(120), ForeignKey("categories.slug"), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)


class City(Base):
    __tablename__ = "cities"

    slug: Mapped[str] = mapped_column(String(80), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120))
    country_code: Mapped[str] = mapped_column(String(2))


class ListingDraft(Base):
    __tablename__ = "listing_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    seller_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    title: Mapped[str | None] = mapped_column(String(180), nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_slug: Mapped[str | None] = mapped_column(String(120), ForeignKey("categories.slug"), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(40), nullable=True)
    condition_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    color: Mapped[str | None] = mapped_column(String(60), nullable=True)
    approx_dimensions_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    intended_use: Mapped[str | None] = mapped_column(String(160), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    asking_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    city_slug: Mapped[str | None] = mapped_column(String(80), ForeignKey("cities.slug"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=ListingWorkflowStatus.draft.value)
    ai_confidence: Mapped[float | None] = mapped_column(nullable=True)
    ai_missing_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_safety_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_source_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    images: Mapped[list["ListingImage"]] = relationship(back_populates="draft", cascade="all, delete-orphan")
    jobs: Mapped[list["AIJob"]] = relationship(back_populates="draft", cascade="all, delete-orphan")


class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    seller_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    draft_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("listing_drafts.id"), nullable=True)
    slug: Mapped[str] = mapped_column(String(220), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    product_name: Mapped[str | None] = mapped_column(String(180), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    category_slug: Mapped[str] = mapped_column(String(120), ForeignKey("categories.slug"))
    condition: Mapped[str | None] = mapped_column(String(40), nullable=True)
    condition_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(80), nullable=True)
    color: Mapped[str | None] = mapped_column(String(60), nullable=True)
    approx_dimensions_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    intended_use: Mapped[str | None] = mapped_column(String(160), nullable=True)
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    asking_price_cents: Mapped[int] = mapped_column(Integer)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    city_slug: Mapped[str] = mapped_column(String(80), ForeignKey("cities.slug"))
    status: Mapped[str] = mapped_column(String(32), default=ListingWorkflowStatus.published.value)
    visibility: Mapped[str] = mapped_column(String(16), default=Visibility.public.value)
    ai_confidence: Mapped[float | None] = mapped_column(nullable=True)
    ai_source_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    images: Mapped[list["ListingImage"]] = relationship(back_populates="listing", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="listing")


class ListingImage(Base):
    __tablename__ = "listing_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    draft_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("listing_drafts.id"), nullable=True, index=True)
    listing_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("listings.id"), nullable=True, index=True)
    provenance: Mapped[str] = mapped_column(String(20), default=ImageProvenance.user_upload.value)
    storage_path: Mapped[str] = mapped_column(String(255))
    public_url: Mapped[str] = mapped_column(String(255))
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    draft: Mapped[ListingDraft | None] = relationship(back_populates="images")
    listing: Mapped[Listing | None] = relationship(back_populates="images")


class AIJob(Base):
    __tablename__ = "ai_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    draft_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("listing_drafts.id"), nullable=True, index=True)
    job_type: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(24), default=AIJobStatus.queued.value)
    model_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    credits_spent: Mapped[int] = mapped_column(Integer, default=0)
    request_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    draft: Mapped[ListingDraft | None] = relationship(back_populates="jobs")


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="uq_user_listing_favorite"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    listing_id: Mapped[str] = mapped_column(String(36), ForeignKey("listings.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    listing_id: Mapped[str] = mapped_column(String(36), ForeignKey("listings.id"), index=True)
    reason: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    listing_id: Mapped[str] = mapped_column(String(36), ForeignKey("listings.id"), index=True)
    buyer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    seller_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default=OrderStatus.initiated.value)
    address_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tracking_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    carrier: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    listing: Mapped[Listing] = relationship(back_populates="orders")


class MessageThread(Base):
    __tablename__ = "message_threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    listing_id: Mapped[str] = mapped_column(String(36), ForeignKey("listings.id"), index=True)
    seller_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    buyer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    subject: Mapped[str | None] = mapped_column(String(180), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default=MessageThreadStatus.open.value)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages: Mapped[list["MessageEvent"]] = relationship(back_populates="thread", cascade="all, delete-orphan")
    offers: Mapped[list["Offer"]] = relationship(back_populates="thread", cascade="all, delete-orphan")


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = (Index("uq_approval_owner_idempotency_slot", "owner_user_id", "idempotency_slot", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    requested_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    agent_grant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_grants.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default=ApprovalRequestStatus.pending.value)
    action_type: Mapped[str] = mapped_column(String(40))
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    summary: Mapped[str] = mapped_column(String(255))
    diff_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    action_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    idempotency_slot: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    agent_grant: Mapped["AgentGrant | None"] = relationship(back_populates="approval_requests")
    receipts: Mapped[list["ActionReceipt"]] = relationship(back_populates="approval_request", cascade="all, delete-orphan")


class MessageEvent(Base):
    __tablename__ = "message_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(String(36), ForeignKey("message_threads.id"), index=True)
    sender_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    approval_request_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("approval_requests.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(24), default=MessageEventKind.user_message.value)
    status: Mapped[str] = mapped_column(String(24), default=MessageEventStatus.pending_approval.value)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    thread: Mapped[MessageThread] = relationship(back_populates="messages")


class Offer(Base):
    __tablename__ = "offers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id: Mapped[str] = mapped_column(String(36), ForeignKey("message_threads.id"), index=True)
    listing_id: Mapped[str] = mapped_column(String(36), ForeignKey("listings.id"), index=True)
    buyer_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    seller_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    approval_request_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("approval_requests.id"), nullable=True, index=True)
    supersedes_offer_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("offers.id"), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(24), default=OfferStatus.pending_approval.value)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    thread: Mapped[MessageThread] = relationship(back_populates="offers")


class AgentGrant(Base):
    __tablename__ = "agent_grants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    personal_access_token_id: Mapped[str] = mapped_column(String(36), ForeignKey("personal_access_tokens.id"), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    agent_family: Mapped[str] = mapped_column(String(40))
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list)
    approval_mode: Mapped[str] = mapped_column(String(40), default="prepare_then_confirm")
    status: Mapped[str] = mapped_column(String(24), default=AgentGrantStatus.active.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="agent_grants")
    personal_access_token: Mapped[PersonalAccessToken] = relationship(back_populates="agent_grant")
    approval_requests: Mapped[list[ApprovalRequest]] = relationship(back_populates="agent_grant")


class ActionReceipt(Base):
    __tablename__ = "action_receipts"
    __table_args__ = (Index("uq_receipt_decision_slot", "decision_slot", unique=True),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    approval_request_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("approval_requests.id"), nullable=True, index=True)
    decision_slot: Mapped[str | None] = mapped_column(String(36), nullable=True)
    owner_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    requested_by_user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    agent_grant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("agent_grants.id"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(40))
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default=ActionReceiptStatus.succeeded.value)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    result_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    approval_request: Mapped[ApprovalRequest | None] = relationship(back_populates="receipts")
