"""add agent-native messaging, offers, approvals, receipts, and grants

Revision ID: 0003_agent_native_core
Revises: 0002_listing_review_fields
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_agent_native_core"
down_revision = "0002_listing_review_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_threads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("listing_id", sa.String(length=36), nullable=False),
        sa.Column("seller_id", sa.String(length=36), nullable=False),
        sa.Column("buyer_id", sa.String(length=36), nullable=False),
        sa.Column("subject", sa.String(length=180), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_threads_listing_id", "message_threads", ["listing_id"], unique=False)
    op.create_index("ix_message_threads_seller_id", "message_threads", ["seller_id"], unique=False)
    op.create_index("ix_message_threads_buyer_id", "message_threads", ["buyer_id"], unique=False)

    op.create_table(
        "agent_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("personal_access_token_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("agent_family", sa.String(length=40), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("approval_mode", sa.String(length=40), nullable=False, server_default="prepare_then_confirm"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["personal_access_token_id"], ["personal_access_tokens.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("personal_access_token_id"),
    )
    op.create_index("ix_agent_grants_user_id", "agent_grants", ["user_id"], unique=False)
    op.create_index("ix_agent_grants_personal_access_token_id", "agent_grants", ["personal_access_token_id"], unique=True)

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("agent_grant_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=True),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("diff_payload", sa.JSON(), nullable=False),
        sa.Column("action_payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_grant_id"], ["agent_grants.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_requests_owner_user_id", "approval_requests", ["owner_user_id"], unique=False)
    op.create_index("ix_approval_requests_requested_by_user_id", "approval_requests", ["requested_by_user_id"], unique=False)
    op.create_index("ix_approval_requests_agent_grant_id", "approval_requests", ["agent_grant_id"], unique=False)

    op.create_table(
        "message_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("sender_id", sa.String(length=36), nullable=False),
        sa.Column("approval_request_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=24), nullable=False, server_default="user_message"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending_approval"),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"]),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["thread_id"], ["message_threads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_events_thread_id", "message_events", ["thread_id"], unique=False)
    op.create_index("ix_message_events_sender_id", "message_events", ["sender_id"], unique=False)
    op.create_index("ix_message_events_approval_request_id", "message_events", ["approval_request_id"], unique=False)

    op.create_table(
        "offers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("listing_id", sa.String(length=36), nullable=False),
        sa.Column("buyer_id", sa.String(length=36), nullable=False),
        sa.Column("seller_id", sa.String(length=36), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=False),
        sa.Column("approval_request_id", sa.String(length=36), nullable=True),
        sa.Column("supersedes_offer_id", sa.String(length=36), nullable=True),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending_approval"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"]),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["supersedes_offer_id"], ["offers.id"]),
        sa.ForeignKeyConstraint(["thread_id"], ["message_threads.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offers_thread_id", "offers", ["thread_id"], unique=False)
    op.create_index("ix_offers_listing_id", "offers", ["listing_id"], unique=False)
    op.create_index("ix_offers_buyer_id", "offers", ["buyer_id"], unique=False)
    op.create_index("ix_offers_seller_id", "offers", ["seller_id"], unique=False)
    op.create_index("ix_offers_created_by_user_id", "offers", ["created_by_user_id"], unique=False)
    op.create_index("ix_offers_approval_request_id", "offers", ["approval_request_id"], unique=False)

    op.create_table(
        "action_receipts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("approval_request_id", sa.String(length=36), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("requested_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("agent_grant_id", sa.String(length=36), nullable=True),
        sa.Column("action_type", sa.String(length=40), nullable=False),
        sa.Column("resource_type", sa.String(length=40), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="succeeded"),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["agent_grant_id"], ["agent_grants.id"]),
        sa.ForeignKeyConstraint(["approval_request_id"], ["approval_requests.id"]),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_action_receipts_approval_request_id", "action_receipts", ["approval_request_id"], unique=False)
    op.create_index("ix_action_receipts_owner_user_id", "action_receipts", ["owner_user_id"], unique=False)
    op.create_index("ix_action_receipts_actor_user_id", "action_receipts", ["actor_user_id"], unique=False)
    op.create_index("ix_action_receipts_requested_by_user_id", "action_receipts", ["requested_by_user_id"], unique=False)
    op.create_index("ix_action_receipts_agent_grant_id", "action_receipts", ["agent_grant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_action_receipts_agent_grant_id", table_name="action_receipts")
    op.drop_index("ix_action_receipts_requested_by_user_id", table_name="action_receipts")
    op.drop_index("ix_action_receipts_actor_user_id", table_name="action_receipts")
    op.drop_index("ix_action_receipts_owner_user_id", table_name="action_receipts")
    op.drop_index("ix_action_receipts_approval_request_id", table_name="action_receipts")
    op.drop_table("action_receipts")

    op.drop_index("ix_offers_approval_request_id", table_name="offers")
    op.drop_index("ix_offers_created_by_user_id", table_name="offers")
    op.drop_index("ix_offers_seller_id", table_name="offers")
    op.drop_index("ix_offers_buyer_id", table_name="offers")
    op.drop_index("ix_offers_listing_id", table_name="offers")
    op.drop_index("ix_offers_thread_id", table_name="offers")
    op.drop_table("offers")

    op.drop_index("ix_message_events_approval_request_id", table_name="message_events")
    op.drop_index("ix_message_events_sender_id", table_name="message_events")
    op.drop_index("ix_message_events_thread_id", table_name="message_events")
    op.drop_table("message_events")

    op.drop_index("ix_approval_requests_agent_grant_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_requested_by_user_id", table_name="approval_requests")
    op.drop_index("ix_approval_requests_owner_user_id", table_name="approval_requests")
    op.drop_table("approval_requests")

    op.drop_index("ix_agent_grants_personal_access_token_id", table_name="agent_grants")
    op.drop_index("ix_agent_grants_user_id", table_name="agent_grants")
    op.drop_table("agent_grants")

    op.drop_index("ix_message_threads_buyer_id", table_name="message_threads")
    op.drop_index("ix_message_threads_seller_id", table_name="message_threads")
    op.drop_index("ix_message_threads_listing_id", table_name="message_threads")
    op.drop_table("message_threads")
