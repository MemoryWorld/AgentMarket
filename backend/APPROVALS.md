# Approval integrity and local verification

The existing REST and MCP endpoints now share the credential policy and the
message, offer and seller-action preparation handlers. Public tool signatures
and response fields remain compatible. Intentional authorization changes:

- PAT scopes are intersected with the linked grant's scopes. Revoked tokens,
  revoked grants, inactive users and mismatched grant owners are rejected.
- Creating/revoking credentials, approving/rejecting proposals, direct listing
  publication and direct seller fulfillment/cancellation require an interactive
  user access token. PATs cannot become human approvers by requesting more scopes.
- Preparing an action requires both `approvals:write` and the corresponding
  `messages:write`, `offers:write`, `listings:write` or `orders:write` scope.
- Draft messages/offers are visible only to their author until approval. Thread
  responses include offers only when the viewer has `offers:read`.
- A publication proposal stores a fingerprint of the complete draft and its
  images. Editing either invalidates the proposal; the seller must review a new
  proposal. Dispatch rechecks resource ownership and linked grant revocation.

## Idempotency and transactions

An owner-row database write serializes preparation before any message or offer
draft is created. An owner-scoped key identifies the normalized original request
(action, target, input fields and grant); generated resource IDs are excluded.
REST/MCP retries therefore return the same proposal and resource. Reusing a key
for different input returns HTTP 409 (an MCP tool error).

Decisions acquire the same owner lock, then conditionally transition `pending`
to an internal `executing` state. One unique decision slot permits one new
receipt per proposal. Repeated identical decisions return the existing receipt;
opposite decisions return 409. Failed approvals return HTTP 400 consistently on
replay and never rerun the action.

Business writes run inside a savepoint. The preceding owner/claim UPDATE starts
a **real outer SQLite transaction**, preventing the legacy driver's standalone
SAVEPOINT behavior. An action exception rolls back even flushed business writes;
the failed state and failed receipt are then committed together. A receipt-store
or outer-commit failure rolls back the entire decision, including successful
business writes. Exceptions leave no `executing` row committed by this path.

The database guarantees apply to this database's effects. There is no external
payment/network side effect in the approval dispatcher, and this implementation
does not claim exactly-once delivery to third-party systems. SQLite remains a
local single-writer database; PostgreSQL concurrency and deployment at scale have
not been measured. Interactive access tokens are the application's current human
authentication boundary, not a proof of physical user presence.

## Migration 0004

`idempotency_slot` has a unique `(owner_user_id, idempotency_slot)` index;
`decision_slot` has a unique index. New application records occupy these slots.
The original historical keys and receipt foreign keys are retained unchanged.

- A unique historical approval receives its slot, but reuse of its key is
  rejected because old rows have no verifiable request fingerprint.
- Every approval in a historical duplicate-key group is frozen (slot is NULL),
  including an earlier pending proposal followed by an executed duplicate.
  Those rows and keys cannot be decided or reused through the API; use a new key.
- Duplicate historical receipts remain linked to their original approval; the
  earliest receipt owns its decision slot. Migration does not erase history or
  reverse effects that already happened before the upgrade.
- Unkeyed historical proposals remain unkeyed. An old publication proposal
  without a draft snapshot must be prepared again before it can publish.

Back up the database before applying schema migrations. The normal application
startup runs Alembic to `head`; the migration also supports downgrade without
deleting the original approval/receipt rows.

## Reproduce tests without external services

From `backend`, after installing `requirements.txt` and `requirements-dev.txt`:

```sh
python -m pytest -q
```

The test configuration disables dotenv loading, forces an empty provider key,
and assigns a fresh temporary SQLite database/media directory. It exercises the
real FastAPI routes, MCP protocol client and SQLAlchemy sessions; only fault
injection tests replace the dispatcher or receipt writer. No real model, Redis,
payment provider or external API is required.

Coverage includes restricted scopes, credential escalation, owner/revocation
checks, private pending content, cross-transport replay and conflicting payloads,
concurrent preparation and approve/reject races, flushed-write rollback, receipt
failure rollback, modified publication snapshots, checkout terminal states,
database unique indexes and migration of duplicate legacy rows.
