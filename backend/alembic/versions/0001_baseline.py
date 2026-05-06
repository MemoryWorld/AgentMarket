"""baseline schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("city_slug", sa.String(length=80), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=False, server_default="US"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "email_otps",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("email"),
    )

    op.create_table(
        "categories",
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("parent_slug", sa.String(length=120), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["parent_slug"], ["categories.slug"]),
        sa.PrimaryKeyConstraint("slug"),
    )

    op.create_table(
        "cities",
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.PrimaryKeyConstraint("slug"),
    )

    op.create_table(
        "seller_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("handle", sa.String(length=80), nullable=False),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_seller_profiles_handle", "seller_profiles", ["handle"], unique=True)

    op.create_table(
        "credit_wallets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("balance_credits", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "usage_ledgers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("delta_credits", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("reference_type", sa.String(length=80), nullable=True),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_usage_ledgers_user_id", "usage_ledgers", ["user_id"], unique=False)

    op.create_table(
        "personal_access_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("token_prefix", sa.String(length=20), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_personal_access_tokens_token_prefix", "personal_access_tokens", ["token_prefix"], unique=False)
    op.create_index("ix_personal_access_tokens_token_hash", "personal_access_tokens", ["token_hash"], unique=True)
    op.create_index("ix_personal_access_tokens_user_id", "personal_access_tokens", ["user_id"], unique=False)

    op.create_table(
        "listing_drafts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("seller_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_slug", sa.String(length=120), nullable=True),
        sa.Column("condition", sa.String(length=40), nullable=True),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("color", sa.String(length=60), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("asking_price_cents", sa.Integer(), nullable=True),
        sa.Column("suggested_price_cents", sa.Integer(), nullable=True),
        sa.Column("currency_code", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("city_slug", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("ai_missing_fields", sa.JSON(), nullable=False),
        sa.Column("ai_safety_flags", sa.JSON(), nullable=False),
        sa.Column("ai_source_model", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["category_slug"], ["categories.slug"]),
        sa.ForeignKeyConstraint(["city_slug"], ["cities.slug"]),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listing_drafts_seller_id", "listing_drafts", ["seller_id"], unique=False)

    op.create_table(
        "listings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("seller_id", sa.String(length=36), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=True),
        sa.Column("slug", sa.String(length=220), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category_slug", sa.String(length=120), nullable=False),
        sa.Column("condition", sa.String(length=40), nullable=True),
        sa.Column("brand", sa.String(length=80), nullable=True),
        sa.Column("color", sa.String(length=60), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=False),
        sa.Column("asking_price_cents", sa.Integer(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("city_slug", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="published"),
        sa.Column("visibility", sa.String(length=16), nullable=False, server_default="public"),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("ai_source_model", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["category_slug"], ["categories.slug"]),
        sa.ForeignKeyConstraint(["city_slug"], ["cities.slug"]),
        sa.ForeignKeyConstraint(["draft_id"], ["listing_drafts.id"]),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listings_seller_id", "listings", ["seller_id"], unique=False)
    op.create_index("ix_listings_slug", "listings", ["slug"], unique=True)

    op.create_table(
        "listing_images",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=True),
        sa.Column("listing_id", sa.String(length=36), nullable=True),
        sa.Column("provenance", sa.String(length=20), nullable=False, server_default="user_upload"),
        sa.Column("storage_path", sa.String(length=255), nullable=False),
        sa.Column("public_url", sa.String(length=255), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["listing_drafts.id"]),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listing_images_draft_id", "listing_images", ["draft_id"], unique=False)
    op.create_index("ix_listing_images_listing_id", "listing_images", ["listing_id"], unique=False)

    op.create_table(
        "ai_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("draft_id", sa.String(length=36), nullable=True),
        sa.Column("job_type", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("model_id", sa.String(length=120), nullable=True),
        sa.Column("credits_spent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["draft_id"], ["listing_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_jobs_draft_id", "ai_jobs", ["draft_id"], unique=False)

    op.create_table(
        "favorites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("listing_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "listing_id", name="uq_user_listing_favorite"),
    )
    op.create_index("ix_favorites_user_id", "favorites", ["user_id"], unique=False)
    op.create_index("ix_favorites_listing_id", "favorites", ["listing_id"], unique=False)

    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("listing_id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reports_user_id", "reports", ["user_id"], unique=False)
    op.create_index("ix_reports_listing_id", "reports", ["listing_id"], unique=False)

    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("listing_id", sa.String(length=36), nullable=False),
        sa.Column("buyer_id", sa.String(length=36), nullable=False),
        sa.Column("seller_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="initiated"),
        sa.Column("address_payload", sa.JSON(), nullable=True),
        sa.Column("tracking_number", sa.String(length=120), nullable=True),
        sa.Column("carrier", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"]),
        sa.ForeignKeyConstraint(["seller_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_orders_listing_id", "orders", ["listing_id"], unique=False)
    op.create_index("ix_orders_buyer_id", "orders", ["buyer_id"], unique=False)
    op.create_index("ix_orders_seller_id", "orders", ["seller_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_orders_seller_id", table_name="orders")
    op.drop_index("ix_orders_buyer_id", table_name="orders")
    op.drop_index("ix_orders_listing_id", table_name="orders")
    op.drop_table("orders")
    op.drop_index("ix_reports_listing_id", table_name="reports")
    op.drop_index("ix_reports_user_id", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_favorites_listing_id", table_name="favorites")
    op.drop_index("ix_favorites_user_id", table_name="favorites")
    op.drop_table("favorites")
    op.drop_index("ix_ai_jobs_draft_id", table_name="ai_jobs")
    op.drop_table("ai_jobs")
    op.drop_index("ix_listing_images_listing_id", table_name="listing_images")
    op.drop_index("ix_listing_images_draft_id", table_name="listing_images")
    op.drop_table("listing_images")
    op.drop_index("ix_listings_slug", table_name="listings")
    op.drop_index("ix_listings_seller_id", table_name="listings")
    op.drop_table("listings")
    op.drop_index("ix_listing_drafts_seller_id", table_name="listing_drafts")
    op.drop_table("listing_drafts")
    op.drop_index("ix_personal_access_tokens_user_id", table_name="personal_access_tokens")
    op.drop_index("ix_personal_access_tokens_token_hash", table_name="personal_access_tokens")
    op.drop_index("ix_personal_access_tokens_token_prefix", table_name="personal_access_tokens")
    op.drop_table("personal_access_tokens")
    op.drop_index("ix_usage_ledgers_user_id", table_name="usage_ledgers")
    op.drop_table("usage_ledgers")
    op.drop_table("credit_wallets")
    op.drop_index("ix_seller_profiles_handle", table_name="seller_profiles")
    op.drop_table("seller_profiles")
    op.drop_table("cities")
    op.drop_table("categories")
    op.drop_table("email_otps")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
