"""add review fields to listing drafts and listings

Revision ID: 0002_listing_review_fields
Revises: 0001_baseline
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_listing_review_fields"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listing_drafts", sa.Column("product_name", sa.String(length=180), nullable=True))
    op.add_column("listing_drafts", sa.Column("condition_score", sa.Integer(), nullable=True))
    op.add_column("listing_drafts", sa.Column("approx_dimensions_text", sa.String(length=120), nullable=True))
    op.add_column("listing_drafts", sa.Column("intended_use", sa.String(length=160), nullable=True))

    op.add_column("listings", sa.Column("product_name", sa.String(length=180), nullable=True))
    op.add_column("listings", sa.Column("condition_score", sa.Integer(), nullable=True))
    op.add_column("listings", sa.Column("approx_dimensions_text", sa.String(length=120), nullable=True))
    op.add_column("listings", sa.Column("intended_use", sa.String(length=160), nullable=True))

    op.execute("UPDATE listing_drafts SET product_name = title WHERE product_name IS NULL")
    op.execute("UPDATE listings SET product_name = title WHERE product_name IS NULL")


def downgrade() -> None:
    op.drop_column("listings", "intended_use")
    op.drop_column("listings", "approx_dimensions_text")
    op.drop_column("listings", "condition_score")
    op.drop_column("listings", "product_name")

    op.drop_column("listing_drafts", "intended_use")
    op.drop_column("listing_drafts", "approx_dimensions_text")
    op.drop_column("listing_drafts", "condition_score")
    op.drop_column("listing_drafts", "product_name")
