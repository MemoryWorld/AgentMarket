"""Preserve historical rows while assigning unique replay/decision slots."""

import sqlalchemy as sa
from alembic import op

revision = "0004_approval_integrity"
down_revision = "0003_agent_native_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approval_requests", sa.Column("idempotency_slot", sa.String(120), nullable=True))
    op.add_column("approval_requests", sa.Column("request_fingerprint", sa.String(64), nullable=True))
    op.add_column("action_receipts", sa.Column("decision_slot", sa.String(36), nullable=True))
    connection = op.get_bind()
    # Keep every legacy key, relationship and receipt. Ambiguous approval groups
    # are frozen; receipt duplicates retain their original links.
    groups = {}
    for row in connection.execute(sa.text("SELECT id, owner_user_id, idempotency_key FROM approval_requests ORDER BY created_at, id")).mappings():
        if row["idempotency_key"]:
            groups.setdefault((row["owner_user_id"], row["idempotency_key"]), []).append(row["id"])
    for (_, key), ids in groups.items():
        # Freeze ambiguous groups, even when an earlier pending row predates an
        # executed duplicate. Never pick a pending historical winner.
        if len(ids) == 1:
            connection.execute(sa.text("UPDATE approval_requests SET idempotency_slot = :slot WHERE id = :id"), {"slot": key, "id": ids[0]})
    seen = set()
    for row in connection.execute(sa.text("SELECT id, approval_request_id FROM action_receipts ORDER BY created_at, id")).mappings():
        key = row["approval_request_id"]
        if key and key not in seen:
            connection.execute(sa.text("UPDATE action_receipts SET decision_slot = :slot WHERE id = :id"), {"slot": key, "id": row["id"]})
            seen.add(key)
    op.create_index("uq_approval_owner_idempotency_slot", "approval_requests", ["owner_user_id", "idempotency_slot"], unique=True)
    op.create_index("uq_receipt_decision_slot", "action_receipts", ["decision_slot"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_receipt_decision_slot", table_name="action_receipts")
    op.drop_index("uq_approval_owner_idempotency_slot", table_name="approval_requests")
    op.drop_column("action_receipts", "decision_slot")
    op.drop_column("approval_requests", "request_fingerprint")
    op.drop_column("approval_requests", "idempotency_slot")
