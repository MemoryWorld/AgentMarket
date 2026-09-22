import asyncio
import json
import os
import sqlite3
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from alembic import command
from app.main import app
from app.mcp_server import mcp
from app.services import approval_ops
from fastapi.testclient import TestClient
from fastmcp import Client
from fastmcp.exceptions import ToolError
from sqlalchemy.engine import make_url
from test_api import (
    create_agent_grant,
    create_published_listing,
    get_me,
    issue_token,
    make_alembic_config,
    make_test_image,
)


def headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def market():
    with TestClient(app) as client:
        seller = issue_token(client, f"seller-{uuid.uuid4().hex}@example.com")
        buyer = issue_token(client, f"buyer-{uuid.uuid4().hex}@example.com")
        stranger = issue_token(client, f"other-{uuid.uuid4().hex}@example.com")
        listing = create_published_listing(client, seller)
        grant = create_agent_grant(client, seller)
        response = client.post("/api/v1/threads", headers=headers(seller), json={
            "listing_id": listing["id"], "participant_user_id": get_me(client, buyer)["id"],
        })
        response.raise_for_status()
        yield client, seller, buyer, stranger, listing, grant, response.json()["id"]


def mcp_call(client, name, **arguments):
    async def call():
        async with Client(mcp) as protocol:
            return (await protocol.call_tool(name, arguments)).data
    return client.portal.call(call)


def query(sql, parameters=()):
    with sqlite3.connect(make_url(os.environ["DATABASE_URL"]).database) as connection:
        return connection.execute(sql, parameters).fetchall()


def change(sql, parameters=()):
    with sqlite3.connect(make_url(os.environ["DATABASE_URL"]).database) as connection:
        connection.execute(sql, parameters)


def prepare_message(market, key="message-1"):
    client, _, _, _, _, grant, thread_id = market
    response = client.post(f"/api/v1/threads/{thread_id}/messages", headers=headers(grant["token"]),
                           json={"body": "Private draft until human approval", "idempotency_key": key})
    response.raise_for_status()
    return response.json()


def test_pat_cannot_self_approve_or_mint_credentials(market):
    client, seller, _, stranger, listing, grant, _ = market
    message = prepare_message(market)
    approval_id = message["approval_request_id"]
    for decision in ("approve", "reject"):
        assert client.post(f"/api/v1/approval-requests/{approval_id}/{decision}", headers=headers(grant["token"])).status_code == 403
        assert client.post(f"/api/v1/approval-requests/{approval_id}/{decision}", headers=headers(stranger)).status_code == 404
    for path, payload in [("personal-access-tokens", {"name": "escalation", "scopes": ["grants:write"]}),
                          ("agent-grants", {"name": "escalation", "agent_family": "codex", "scopes": ["grants:write"]})]:
        assert client.post(f"/api/v1/{path}", headers=headers(grant["token"]), json=payload).status_code == 403
    assert client.get("/api/v1/personal-access-tokens", headers=headers(grant["token"])).status_code == 403
    draft_id = query("SELECT draft_id FROM listings WHERE id = ?", (listing["id"],))[0][0]
    assert client.post(f"/api/v1/draft-listings/{draft_id}/publish", headers=headers(grant["token"])).status_code == 403
    with pytest.raises(ToolError, match="Human approval"):
        mcp_call(client, "publish_listing_draft", access_token=grant["token"], draft_id=draft_id)
    approved = client.post(f"/api/v1/approval-requests/{approval_id}/approve", headers=headers(seller))
    approved.raise_for_status()
    assert approved.json()["receipt"]["status"] == "succeeded"


@pytest.mark.parametrize("scopes", [["approvals:write"], ["messages:read"]])
def test_rest_mcp_enforce_scopes_and_owner(market, scopes):
    client, seller, _, stranger, listing, _, thread_id = market
    pat = client.post("/api/v1/personal-access-tokens", headers=headers(seller), json={"name": "narrow", "scopes": scopes}).json()["token"]
    assert client.post(f"/api/v1/threads/{thread_id}/messages", headers=headers(pat), json={"body": "blocked"}).status_code == 403
    with pytest.raises(ToolError, match="Missing required scopes"):
        mcp_call(client, "create_message_draft", access_token=pat, thread_id=thread_id, body="blocked")
    args = {"action_type": "reprice_listing", "listing_id": listing["id"], "new_price_cents": 99}
    assert client.post("/api/v1/approval-requests", headers=headers(pat), json=args).status_code == 403
    with pytest.raises(ToolError, match="Missing required scopes"):
        mcp_call(client, "prepare_seller_action", access_token=pat, **args)
    assert client.post("/api/v1/approval-requests", headers=headers(stranger), json=args).status_code == 404
    with pytest.raises(ToolError, match="Listing not found"):
        mcp_call(client, "prepare_seller_action", access_token=stranger, **args)


def test_grant_scope_intersection_owner_mismatch_and_revocation(market):
    client, seller, _, stranger, _, grant, thread_id = market
    change("UPDATE agent_grants SET scopes = ? WHERE id = ?", ('["approvals:read"]', grant["id"]))
    assert client.get("/api/v1/threads", headers=headers(grant["token"])).status_code == 403
    with pytest.raises(ToolError, match="Missing required scopes"):
        mcp_call(client, "list_threads", access_token=grant["token"])
    change("UPDATE agent_grants SET user_id = ? WHERE id = ?", (get_me(client, stranger)["id"], grant["id"]))
    assert client.get("/api/v1/approval-requests", headers=headers(grant["token"])).status_code == 401
    with pytest.raises(ToolError, match="invalid or revoked"):
        mcp_call(client, "list_approval_requests", access_token=grant["token"])
    fresh = create_agent_grant(client, seller, name="revoked")
    prepared = mcp_call(client, "create_message_draft", access_token=fresh["token"], thread_id=thread_id, body="never sent")
    client.post(f"/api/v1/agent-grants/{fresh['id']}/revoke", headers=headers(seller)).raise_for_status()
    with pytest.raises(ToolError, match="Invalid personal access token"):
        mcp_call(client, "list_threads", access_token=fresh["token"])
    failed = client.post(f"/api/v1/approval-requests/{prepared['approval_request_id']}/approve", headers=headers(seller))
    assert failed.status_code == 400
    assert query("SELECT status FROM message_events WHERE id = ?", (prepared["message_id"],)) == [("pending_approval",)]


def test_cross_transport_message_offer_replay_and_payload_conflicts(market):
    client, _, _, _, _, grant, thread_id = market
    message = prepare_message(market)
    replay = mcp_call(client, "create_message_draft", access_token=grant["token"], thread_id=thread_id,
                      body=message["body"], idempotency_key="message-1")
    assert replay["message_id"] == message["id"]
    with pytest.raises(ToolError, match="Idempotency key"):
        mcp_call(client, "create_message_draft", access_token=grant["token"], thread_id=thread_id, body="changed", idempotency_key="message-1")
    assert client.post(f"/api/v1/threads/{thread_id}/messages", headers=headers(grant["token"]), json={"body": "changed", "idempotency_key": "message-1"}).status_code == 409
    offer = mcp_call(client, "create_offer", access_token=grant["token"], thread_id=thread_id, amount_cents=500, note="same", idempotency_key="offer-1")
    replay_offer = client.post("/api/v1/offers", headers=headers(grant["token"]), json={"thread_id": thread_id, "amount_cents": 500, "note": "same", "idempotency_key": "offer-1"})
    replay_offer.raise_for_status()
    assert replay_offer.json()["id"] == offer["offer_id"]
    with pytest.raises(ToolError, match="Idempotency key"):
        mcp_call(client, "create_offer", access_token=grant["token"], thread_id=thread_id, amount_cents=600, note="same", idempotency_key="offer-1")
    with pytest.raises(ToolError, match="Idempotency key"):
        mcp_call(client, "create_offer", access_token=grant["token"], thread_id=thread_id, amount_cents=500, idempotency_key="message-1")
    assert query("SELECT count(*) FROM message_events WHERE thread_id = ?", (thread_id,)) == [(1,)]
    assert query("SELECT count(*) FROM offers WHERE thread_id = ?", (thread_id,)) == [(1,)]


def test_unapproved_content_is_private_and_read_scopes_are_separate(market):
    client, seller, buyer, _, _, grant, thread_id = market
    message = prepare_message(market)
    offer = mcp_call(client, "create_offer", access_token=grant["token"], thread_id=thread_id, amount_cents=500)
    other_view = client.get(f"/api/v1/threads/{thread_id}", headers=headers(buyer)).json()
    assert other_view["messages"] == [] and other_view["offers"] == []
    assert client.get(f"/api/v1/offers?thread_id={thread_id}", headers=headers(buyer)).json() == []
    assert client.post(f"/api/v1/offers/{offer['offer_id']}/accept", headers=headers(buyer), json={}).status_code == 404
    client.post(f"/api/v1/approval-requests/{message['approval_request_id']}/approve", headers=headers(seller)).raise_for_status()
    client.post(f"/api/v1/approval-requests/{offer['approval_request_id']}/approve", headers=headers(seller)).raise_for_status()
    narrow = client.post("/api/v1/personal-access-tokens", headers=headers(buyer), json={"name": "messages only", "scopes": ["messages:read"]}).json()["token"]
    view = client.get(f"/api/v1/threads/{thread_id}", headers=headers(narrow)).json()
    assert len(view["messages"]) == 1 and view["offers"] == []


@pytest.mark.parametrize("decisions", [("approve", "approve"), ("reject", "reject"), ("approve", "reject")])
def test_concurrent_decisions_have_one_terminal_receipt(market, monkeypatch, decisions):
    client, seller, _, _, _, _, thread_id = market
    message = prepare_message(market)
    original = approval_ops._dispatch_action
    executed = []
    async def slow_dispatch(session, approval):
        executed.append(approval.id)
        await asyncio.sleep(0.03)
        return await original(session, approval)
    monkeypatch.setattr(approval_ops, "_dispatch_action", slow_dispatch)
    barrier = Barrier(2)
    def decide(decision):
        barrier.wait(timeout=5)
        return client.post(f"/api/v1/approval-requests/{message['approval_request_id']}/{decision}", headers=headers(seller))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, decisions))
    assert sorted(result.status_code for result in results) == ([200, 200] if decisions[0] == decisions[1] else [200, 409])
    assert len(executed) <= 1
    rows = query("SELECT id, status FROM action_receipts WHERE approval_request_id = ?", (message["approval_request_id"],))
    assert len(rows) == 1
    if decisions[0] == decisions[1]:
        assert results[0].json()["receipt"]["id"] == results[1].json()["receipt"]["id"]
    assert query("SELECT count(*) FROM message_events WHERE thread_id = ?", (thread_id,)) == [(1,)]


def test_concurrent_prepare_returns_same_resource_without_orphans(market):
    client, _, _, _, _, grant, thread_id = market
    barrier = Barrier(2)
    def prepare(_):
        barrier.wait(timeout=5)
        return client.post(f"/api/v1/threads/{thread_id}/messages", headers=headers(grant["token"]), json={"body": "same", "idempotency_key": "parallel"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(prepare, range(2)))
    for result in results:
        result.raise_for_status()
    assert results[0].json()["id"] == results[1].json()["id"]
    assert query("SELECT count(*) FROM message_events WHERE thread_id = ?", (thread_id,)) == [(1,)]


def test_failure_rolls_back_flushed_business_writes_and_replays_receipt(market, monkeypatch):
    client, seller, _, _, _, _, thread_id = market
    message = prepare_message(market)
    original = approval_ops._dispatch_action
    attempts = []
    async def fail_after_flush(session, approval):
        attempts.append(approval.id)
        await original(session, approval)
        await session.flush()
        raise RuntimeError("injected failure after message and thread writes")
    monkeypatch.setattr(approval_ops, "_dispatch_action", fail_after_flush)
    for _ in range(2):
        response = client.post(f"/api/v1/approval-requests/{message['approval_request_id']}/approve", headers=headers(seller))
        assert response.status_code == 400
        assert "injected failure" in response.json()["detail"]
    assert len(attempts) == 1
    assert query("SELECT status FROM message_events WHERE id = ?", (message["id"],)) == [("pending_approval",)]
    assert query("SELECT last_message_at FROM message_threads WHERE id = ?", (thread_id,)) == [(None,)]
    assert query("SELECT status FROM approval_requests WHERE id = ?", (message["approval_request_id"],)) == [("failed",)]
    assert query("SELECT status FROM action_receipts WHERE approval_request_id = ?", (message["approval_request_id"],)) == [("failed",)]


def test_receipt_storage_failure_rolls_back_entire_decision_after_savepoint(market, monkeypatch):
    client, seller, _, _, _, _, thread_id = market
    message = prepare_message(market)
    async def fail_receipt(*args, **kwargs):
        raise RuntimeError("receipt persistence unavailable")
    monkeypatch.setattr(approval_ops, "_record_receipt", fail_receipt)
    with pytest.raises(RuntimeError, match="receipt persistence"):
        client.post(f"/api/v1/approval-requests/{message['approval_request_id']}/approve", headers=headers(seller))
    assert query("SELECT status FROM message_events WHERE id = ?", (message["id"],)) == [("pending_approval",)]
    assert query("SELECT last_message_at FROM message_threads WHERE id = ?", (thread_id,)) == [(None,)]
    assert query("SELECT status FROM approval_requests WHERE id = ?", (message["approval_request_id"],)) == [("pending",)]
    assert query("SELECT count(*) FROM action_receipts WHERE approval_request_id = ?", (message["approval_request_id"],)) == [(0,)]


def test_publish_approval_rejects_changed_draft_and_preserves_original(market):
    client, seller, _, _, _, grant, _ = market
    draft = client.post("/api/v1/draft-listings/ai-autofill", headers=headers(seller), files=[("files", ("test.jpg", make_test_image(), "image/jpeg"))]).json()
    prepared = mcp_call(client, "prepare_seller_action", access_token=grant["token"], action_type="publish_listing", draft_id=draft["id"], idempotency_key="publish")
    client.patch(f"/api/v1/draft-listings/{draft['id']}", headers=headers(grant["token"]), json={"asking_price_cents": 1}).raise_for_status()
    response = client.post(f"/api/v1/approval-requests/{prepared['approval_request_id']}/approve", headers=headers(seller))
    assert response.status_code == 400 and "Draft changed" in response.json()["detail"]
    assert query("SELECT count(*) FROM listings WHERE draft_id = ?", (draft["id"],)) == [(0,)]


def test_checkout_cannot_restore_cancelled_order_via_rest_or_mcp(market):
    client, seller, buyer, _, listing, _, _ = market
    order = client.post("/api/v1/orders", headers=headers(buyer), json={"listing_id": listing["id"]}).json()
    client.post(f"/api/v1/orders/{order['id']}/cancel", headers=headers(seller)).raise_for_status()
    address = {"full_name": "Buyer", "line1": "1 Test St", "city": "Sydney", "postal_code": "2000", "country_code": "AU"}
    assert client.patch(f"/api/v1/orders/{order['id']}/address", headers=headers(buyer), json={"address": address}).status_code == 409
    assert client.post(f"/api/v1/orders/{order['id']}/mock-pay", headers=headers(buyer)).status_code == 409
    with pytest.raises(ToolError, match="no longer accepts"):
        mcp_call(client, "submit_shipping_address", access_token=buyer, order_id=order["id"], address=address)
    with pytest.raises(ToolError, match="not awaiting payment"):
        mcp_call(client, "confirm_mock_payment", access_token=buyer, order_id=order["id"])
    assert query("SELECT status FROM orders WHERE id = ?", (order["id"],)) == [("cancelled",)]


def test_database_unique_slots_and_legacy_duplicate_decisions(market):
    client, seller, _, _, _, _, _ = market
    message = prepare_message(market)
    client.post(f"/api/v1/approval-requests/{message['approval_request_id']}/approve", headers=headers(seller)).raise_for_status()
    with pytest.raises(sqlite3.IntegrityError):
        change("INSERT INTO action_receipts SELECT 'duplicate', approval_request_id, owner_user_id, actor_user_id, requested_by_user_id, agent_grant_id, action_type, resource_type, resource_id, status, idempotency_key, result_payload, error_message, created_at, decision_slot FROM action_receipts WHERE approval_request_id = ?", (message["approval_request_id"],))
    other = prepare_message(market, key="different")
    with pytest.raises(sqlite3.IntegrityError):
        change("UPDATE approval_requests SET idempotency_slot = 'message-1' WHERE id = ?", (other["approval_request_id"],))
    change("UPDATE approval_requests SET idempotency_slot = NULL WHERE id = ?", (other["approval_request_id"],))
    assert client.post(f"/api/v1/approval-requests/{other['approval_request_id']}/approve", headers=headers(seller)).status_code == 409


def test_migration_preserves_and_freezes_ambiguous_history(tmp_path):
    path = tmp_path / "legacy.db"
    config = make_alembic_config(f"sqlite+aiosqlite:///{path.as_posix()}")
    command.upgrade(config, "0003_agent_native_core")
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO users (id,email,display_name) VALUES ('owner','legacy@example.com','Legacy')")
        for approval_id, status in [("a", "pending"), ("b", "executed"), ("c", "pending")]:
            connection.execute("INSERT INTO approval_requests (id,owner_user_id,requested_by_user_id,status,action_type,resource_type,summary,diff_payload,action_payload,idempotency_key) VALUES (?,?,?,?,'send_message','message','legacy','{}','{}',?)", (approval_id, "owner", "owner", status, "duplicate" if approval_id != "c" else "unique"))
        for receipt_id in ("r1", "r2"):
            connection.execute("INSERT INTO action_receipts (id,approval_request_id,owner_user_id,action_type,resource_type,status,result_payload) VALUES (?,'b','owner','send_message','message','succeeded','{}')", (receipt_id,))
    command.upgrade(config, "head")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT id,idempotency_key,idempotency_slot FROM approval_requests ORDER BY id").fetchall() == [("a", "duplicate", None), ("b", "duplicate", None), ("c", "unique", "unique")]
        assert connection.execute("SELECT id,approval_request_id,decision_slot FROM action_receipts ORDER BY id").fetchall() == [("r1", "b", "b"), ("r2", "b", None)]


def test_seller_action_and_counter_decision_cross_transport_replays(market):
    client, seller, buyer, _, listing, grant, thread_id = market
    args = {"action_type": "reprice_listing", "listing_id": listing["id"], "new_price_cents": 12000, "idempotency_key": "price"}
    prepared = client.post("/api/v1/approval-requests", headers=headers(grant["token"]), json=args)
    prepared.raise_for_status()
    replay = mcp_call(client, "prepare_seller_action", access_token=grant["token"], **args)
    assert replay["approval_request_id"] == prepared.json()["id"]
    with pytest.raises(ToolError, match="Idempotency key"):
        mcp_call(client, "prepare_seller_action", access_token=grant["token"], **{**args, "new_price_cents": 1})
    offer = mcp_call(client, "create_offer", access_token=buyer, thread_id=thread_id, amount_cents=8000, idempotency_key="buyer-offer")
    client.post(f"/api/v1/approval-requests/{offer['approval_request_id']}/approve", headers=headers(buyer)).raise_for_status()
    counter = mcp_call(client, "counter_offer", access_token=grant["token"], offer_id=offer["offer_id"], amount_cents=10000, idempotency_key="counter")
    response = client.post(f"/api/v1/offers/{offer['offer_id']}/counter", headers=headers(grant["token"]), json={"amount_cents": 10000, "idempotency_key": "counter"})
    response.raise_for_status()
    assert response.json()["id"] == counter["offer_id"]
    client.post(f"/api/v1/approval-requests/{counter['approval_request_id']}/approve", headers=headers(seller)).raise_for_status()
    decision = mcp_call(client, "accept_offer", access_token=buyer, offer_id=counter["offer_id"], idempotency_key="accept-counter")
    repeat = client.post(f"/api/v1/offers/{counter['offer_id']}/accept", headers=headers(buyer), json={"idempotency_key": "accept-counter"})
    repeat.raise_for_status()
    assert mcp_call(client, "accept_offer", access_token=buyer, offer_id=counter["offer_id"], idempotency_key="accept-counter")["approval_request_id"] == decision["approval_request_id"]
    client.post(f"/api/v1/approval-requests/{decision['approval_request_id']}/approve", headers=headers(buyer)).raise_for_status()
    assert query("SELECT status FROM offers WHERE id = ?", (counter["offer_id"],)) == [("accepted",)]


def test_dispatch_rechecks_owner_and_private_listing_read_policy(market):
    client, seller, _, stranger, listing, grant, _ = market
    foreign = create_published_listing(client, stranger)
    prepared = mcp_call(client, "prepare_seller_action", access_token=grant["token"], action_type="reprice_listing", listing_id=listing["id"], new_price_cents=1)
    # Simulate an invalid legacy/imported approval. Decision must not trust its payload.
    change("UPDATE approval_requests SET action_payload = ? WHERE id = ?", (json.dumps({"listing_id": foreign["id"], "new_price_cents": 1}), prepared["approval_request_id"]))
    assert client.post(f"/api/v1/approval-requests/{prepared['approval_request_id']}/approve", headers=headers(seller)).status_code == 400
    assert query("SELECT asking_price_cents FROM listings WHERE id = ?", (foreign["id"],)) == [(15500,)]
    change("UPDATE listings SET visibility = 'private' WHERE id = ?", (listing["id"],))
    assert client.get(f"/api/v1/listings/{listing['id']}").status_code == 404
    with pytest.raises(ToolError, match="Listing not found"):
        mcp_call(client, "get_listing", listing_id_or_slug=listing["id"])


def test_even_management_scopes_do_not_make_pat_a_human(market):
    client, seller, _, _, _, _, _ = market
    pat = client.post("/api/v1/personal-access-tokens", headers=headers(seller), json={"name": "management", "scopes": ["grants:write", "approvals:write"]}).json()["token"]
    message = prepare_message(market)
    for path, payload in [("agent-grants", {"name": "child", "agent_family": "codex"}), ("personal-access-tokens", {"name": "child", "scopes": ["ai:generate"]})]:
        response = client.post(f"/api/v1/{path}", headers=headers(pat), json=payload)
        assert response.status_code == 403 and "Human approval" in response.json()["detail"]
    response = client.post(f"/api/v1/approval-requests/{message['approval_request_id']}/approve", headers=headers(pat))
    assert response.status_code == 403 and "Human approval" in response.json()["detail"]


def test_unchanged_publish_snapshot_executes_once(market):
    client, seller, _, _, _, grant, _ = market
    response = client.post("/api/v1/draft-listings/ai-autofill", headers=headers(seller),
                           files=[("files", ("test.jpg", make_test_image(), "image/jpeg"))],
                           data={"city_slug": "sydney-au", "currency_code": "USD"})
    response.raise_for_status()
    draft_id = response.json()["id"]
    client.patch(f"/api/v1/draft-listings/{draft_id}", headers=headers(grant["token"]), json={
        "title": "Snapshot-approved camera", "product_name": "Camera body", "description": "Reviewed details",
        "category_slug": "electronics", "condition_score": 8, "asking_price_cents": 5000, "city_slug": "sydney-au",
    }).raise_for_status()
    prepared = mcp_call(client, "prepare_seller_action", access_token=grant["token"], action_type="publish_listing", draft_id=draft_id, idempotency_key="publish-once")
    receipts = []
    for _ in range(2):
        decision = client.post(f"/api/v1/approval-requests/{prepared['approval_request_id']}/approve", headers=headers(seller))
        decision.raise_for_status()
        receipts.append(decision.json()["receipt"])
    assert receipts[0]["id"] == receipts[1]["id"]
    assert query("SELECT count(*), asking_price_cents FROM listings WHERE draft_id = ?", (draft_id,)) == [(1, 5000)]
