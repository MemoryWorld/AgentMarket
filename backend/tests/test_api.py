import io
import os
import sqlite3
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image


os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test.db")
os.environ.setdefault("EXPOSE_DEBUG_OTP", "true")

from app.main import app  # noqa: E402


def make_test_image() -> bytes:
    image = Image.new("RGB", (256, 256), color=(220, 180, 140))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def issue_token(client: TestClient, email: str) -> str:
    otp_response = client.post("/api/v1/auth/email/request-code", json={"email": email})
    otp_response.raise_for_status()
    code = otp_response.json()["debug_code"]
    verify_response = client.post(
        "/api/v1/auth/email/verify",
        json={
            "email": email,
            "code": code,
            "display_name": email.split("@")[0].replace(".", " ").title(),
            "city_slug": "sydney-au",
            "country_code": "AU",
        },
    )
    verify_response.raise_for_status()
    return verify_response.json()["access_token"]


def get_me(client: TestClient, token: str) -> dict:
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    response.raise_for_status()
    return response.json()


def create_agent_grant(client: TestClient, token: str, name: str = "Seller Codex") -> dict:
    response = client.post(
        "/api/v1/agent-grants",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": name,
            "agent_family": "codex",
            "scopes": [
                "listings:write",
                "orders:write",
                "messages:read",
                "messages:write",
                "offers:read",
                "offers:write",
                "approvals:read",
                "approvals:write",
                "receipts:read",
            ],
        },
    )
    response.raise_for_status()
    return response.json()


def create_published_listing(client: TestClient, seller_token: str, title: str = "Agent-tested camera") -> dict:
    client.post(
        "/api/v1/wallet/top-up",
        headers={"Authorization": f"Bearer {seller_token}"},
        json={"credits": 40},
    ).raise_for_status()

    image_bytes = make_test_image()
    draft_response = client.post(
        "/api/v1/draft-listings/ai-autofill",
        headers={"Authorization": f"Bearer {seller_token}"},
        files=[("files", ("camera.jpg", image_bytes, "image/jpeg"))],
        data={"city_slug": "sydney-au", "currency_code": "USD"},
    )
    draft_response.raise_for_status()
    draft = draft_response.json()

    client.patch(
        f"/api/v1/draft-listings/{draft['id']}",
        headers={"Authorization": f"Bearer {seller_token}"},
        json={
            "title": title,
            "product_name": f"{title} body",
            "description": "Fully reviewed and ready for buyer negotiation.",
            "category_slug": "electronics",
            "condition": "Used - Very Good",
            "condition_score": 8,
            "brand": "TorchCam",
            "approx_dimensions_text": "15 x 9 x 6 cm",
            "intended_use": "Film photography",
            "city_slug": "sydney-au",
            "asking_price_cents": 15500,
        },
    ).raise_for_status()

    publish_response = client.post(
        f"/api/v1/draft-listings/{draft['id']}/publish",
        headers={"Authorization": f"Bearer {seller_token}"},
    )
    publish_response.raise_for_status()
    return publish_response.json()


def make_alembic_config(url: str) -> Config:
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def test_public_seed_data() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/listings")
        response.raise_for_status()
        payload = response.json()
        assert payload["total"] >= 1
        assert any(item["slug"] == "demo-vintage-camera" for item in payload["items"])


def test_pat_creation() -> None:
    with TestClient(app) as client:
        token = issue_token(client, f"pat-{uuid.uuid4().hex[:8]}@example.com")
        response = client.post(
            "/api/v1/personal-access-tokens",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Local agent", "scopes": ["listings:read", "listings:write", "orders:write", "ai:generate"]},
        )
        response.raise_for_status()
        payload = response.json()
        assert payload["token"].startswith("pat_")
        assert "listings:write" in payload["scopes"]


def test_listing_autofill_publish_and_mock_checkout() -> None:
    with TestClient(app) as client:
        seller_token = issue_token(client, f"seller-{uuid.uuid4().hex[:8]}@example.com")
        buyer_token = issue_token(client, f"buyer-{uuid.uuid4().hex[:8]}@example.com")

        client.post(
            "/api/v1/wallet/top-up",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={"credits": 40},
        ).raise_for_status()

        image_bytes = make_test_image()
        draft_response = client.post(
            "/api/v1/draft-listings/ai-autofill",
            headers={"Authorization": f"Bearer {seller_token}"},
            files=[("files", ("camera.jpg", image_bytes, "image/jpeg"))],
            data={"city_slug": "sydney-au", "currency_code": "USD"},
        )
        draft_response.raise_for_status()
        draft = draft_response.json()
        assert draft["id"]
        assert draft["images"]
        assert draft["product_name"]
        assert draft["condition_score"] == 7

        patch_response = client.patch(
            f"/api/v1/draft-listings/{draft['id']}",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={
                "title": "Agent-tested camera",
                "product_name": "Agent-tested camera body",
                "description": "Fully reviewed and ready for mock checkout.",
                "category_slug": "electronics",
                "condition": "Used - Very Good",
                "condition_score": 8,
                "brand": "TorchCam",
                "approx_dimensions_text": "15 x 9 x 6 cm",
                "intended_use": "Film photography",
                "city_slug": "sydney-au",
                "asking_price_cents": 15500,
            },
        )
        patch_response.raise_for_status()

        image_response = client.post(
            "/api/v1/draft-listings/ai-image",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={"draft_id": draft["id"], "style_preset": "clean studio", "quality": "medium", "size": "1024x1024"},
        )
        image_response.raise_for_status()
        assert any(image["provenance"] == "ai_generated" for image in image_response.json()["images"])

        publish_response = client.post(
            f"/api/v1/draft-listings/{draft['id']}/publish",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        publish_response.raise_for_status()
        listing = publish_response.json()
        assert listing["slug"]
        assert listing["product_name"] == "Agent-tested camera body"
        assert listing["condition_score"] == 8
        assert listing["approx_dimensions_text"] == "15 x 9 x 6 cm"
        assert listing["intended_use"] == "Film photography"

        order_response = client.post(
            "/api/v1/orders",
            headers={"Authorization": f"Bearer {buyer_token}"},
            json={"listing_id": listing["id"]},
        )
        order_response.raise_for_status()
        order = order_response.json()

        address_response = client.patch(
            f"/api/v1/orders/{order['id']}/address",
            headers={"Authorization": f"Bearer {buyer_token}"},
            json={
                "address": {
                    "full_name": "Buyer Agent",
                    "line1": "1 Circular Quay",
                    "city": "Sydney",
                    "postal_code": "2000",
                    "country_code": "AU",
                }
            },
        )
        address_response.raise_for_status()
        assert address_response.json()["status"] == "payment_pending"

        payment_response = client.post(
            f"/api/v1/orders/{order['id']}/mock-pay",
            headers={"Authorization": f"Bearer {buyer_token}"},
        )
        payment_response.raise_for_status()
        assert payment_response.json()["status"] == "paid"

        seller_orders = client.get(
            "/api/v1/orders?role=seller",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        seller_orders.raise_for_status()
        assert any(item["id"] == order["id"] for item in seller_orders.json())


def test_publish_requires_review_fields_and_images() -> None:
    with TestClient(app) as client:
        seller_token = issue_token(client, f"seller-{uuid.uuid4().hex[:8]}@example.com")

        incomplete = client.post(
            "/api/v1/draft-listings",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={"title": "Incomplete draft"},
        )
        incomplete.raise_for_status()

        missing_fields_response = client.post(
            f"/api/v1/draft-listings/{incomplete.json()['id']}/publish",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        assert missing_fields_response.status_code == 400
        assert missing_fields_response.json()["detail"] == "Draft is missing required publish fields."

        ready_without_images = client.post(
            "/api/v1/draft-listings",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={
                "title": "Ready except images",
                "product_name": "Ready except images",
                "description": "Structured data is filled in, but no images are attached yet.",
                "category_slug": "electronics",
                "condition": "Used - Good",
                "condition_score": 7,
                "asking_price_cents": 9900,
                "currency_code": "USD",
                "city_slug": "sydney-au",
            },
        )
        ready_without_images.raise_for_status()

        missing_images_response = client.post(
            f"/api/v1/draft-listings/{ready_without_images.json()['id']}/publish",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        assert missing_images_response.status_code == 400
        assert missing_images_response.json()["detail"] == "Draft needs at least one image before publishing."


def test_legacy_listing_tables_upgrade_to_review_fields(tmp_path) -> None:
    db_path = tmp_path / "legacy-marketplace.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE listing_drafts (id TEXT PRIMARY KEY, title TEXT)")
        connection.execute("CREATE TABLE listings (id TEXT PRIMARY KEY, title TEXT NOT NULL)")
        connection.execute("INSERT INTO listing_drafts (id, title) VALUES (?, ?)", ("draft-1", "Legacy draft"))
        connection.execute("INSERT INTO listings (id, title) VALUES (?, ?)", ("listing-1", "Legacy listing"))
        connection.commit()

    config = make_alembic_config(f"sqlite+aiosqlite:///{db_path}")
    command.stamp(config, "0001_baseline")
    command.upgrade(config, "head")

    with sqlite3.connect(db_path) as connection:
        draft_columns = {row[1] for row in connection.execute("PRAGMA table_info(listing_drafts)").fetchall()}
        listing_columns = {row[1] for row in connection.execute("PRAGMA table_info(listings)").fetchall()}
        assert {"product_name", "condition_score", "approx_dimensions_text", "intended_use"} <= draft_columns
        assert {"product_name", "condition_score", "approx_dimensions_text", "intended_use"} <= listing_columns

        draft_product_name = connection.execute("SELECT product_name FROM listing_drafts WHERE id = 'draft-1'").fetchone()[0]
        listing_product_name = connection.execute("SELECT product_name FROM listings WHERE id = 'listing-1'").fetchone()[0]
        assert draft_product_name == "Legacy draft"
        assert listing_product_name == "Legacy listing"


def test_agent_grant_message_offer_and_approval_receipts() -> None:
    with TestClient(app) as client:
        seller_token = issue_token(client, f"seller-{uuid.uuid4().hex[:8]}@example.com")
        buyer_token = issue_token(client, f"buyer-{uuid.uuid4().hex[:8]}@example.com")
        seller = get_me(client, seller_token)
        buyer = get_me(client, buyer_token)
        listing = create_published_listing(client, seller_token)

        grant = create_agent_grant(client, seller_token)
        seller_pat = grant["token"]
        assert grant["agent_family"] == "codex"

        thread_response = client.post(
            "/api/v1/threads",
            headers={"Authorization": f"Bearer {seller_pat}"},
            json={"listing_id": listing["id"], "participant_user_id": buyer["id"], "subject": "Potential buyer conversation"},
        )
        thread_response.raise_for_status()
        thread_id = thread_response.json()["id"]

        message_response = client.post(
            f"/api/v1/threads/{thread_id}/messages",
            headers={"Authorization": f"Bearer {seller_pat}"},
            json={"body": "Hi, I can ship tomorrow if you confirm today.", "idempotency_key": "msg-1"},
        )
        message_response.raise_for_status()
        message = message_response.json()
        assert message["status"] == "pending_approval"

        approvals = client.get(
            "/api/v1/approval-requests?status=pending",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        approvals.raise_for_status()
        message_approval = next(item for item in approvals.json() if item["action_type"] == "send_message")

        approve_message = client.post(
            f"/api/v1/approval-requests/{message_approval['id']}/approve",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        approve_message.raise_for_status()
        assert approve_message.json()["receipt"]["status"] == "succeeded"

        buyer_offer_response = client.post(
            "/api/v1/offers",
            headers={"Authorization": f"Bearer {buyer_token}"},
            json={"thread_id": thread_id, "amount_cents": 14200, "note": "Can pay now if you accept.", "idempotency_key": "offer-1"},
        )
        buyer_offer_response.raise_for_status()
        offer = buyer_offer_response.json()
        assert offer["status"] == "pending_approval"

        buyer_approvals = client.get(
            "/api/v1/approval-requests?status=pending",
            headers={"Authorization": f"Bearer {buyer_token}"},
        )
        buyer_approvals.raise_for_status()
        buyer_offer_approval = next(item for item in buyer_approvals.json() if item["action_type"] == "create_offer")
        client.post(
            f"/api/v1/approval-requests/{buyer_offer_approval['id']}/approve",
            headers={"Authorization": f"Bearer {buyer_token}"},
        ).raise_for_status()

        accept_response = client.post(
            f"/api/v1/offers/{offer['id']}/accept",
            headers={"Authorization": f"Bearer {seller_pat}"},
            json={"idempotency_key": "accept-1"},
        )
        accept_response.raise_for_status()

        seller_approvals = client.get(
            "/api/v1/approval-requests?status=pending",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        seller_approvals.raise_for_status()
        accept_approval = next(item for item in seller_approvals.json() if item["action_type"] == "accept_offer")
        approve_accept = client.post(
            f"/api/v1/approval-requests/{accept_approval['id']}/approve",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        approve_accept.raise_for_status()
        assert approve_accept.json()["receipt"]["status"] == "succeeded"

        thread_detail = client.get(
            f"/api/v1/threads/{thread_id}",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        thread_detail.raise_for_status()
        payload = thread_detail.json()
        assert payload["messages"][0]["status"] == "sent"
        assert any(item["status"] == "accepted" for item in payload["offers"])

        receipts = client.get(
            "/api/v1/action-receipts",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        receipts.raise_for_status()
        action_types = {item["action_type"] for item in receipts.json()}
        assert {"send_message", "accept_offer"} <= action_types


def test_prepare_seller_action_and_revoke_grant() -> None:
    with TestClient(app) as client:
        seller_token = issue_token(client, f"seller-{uuid.uuid4().hex[:8]}@example.com")
        listing = create_published_listing(client, seller_token, title="Approval-managed camera")
        grant = create_agent_grant(client, seller_token, name="Seller Hermes")
        seller_pat = grant["token"]

        prepare_response = client.post(
            "/api/v1/approval-requests",
            headers={"Authorization": f"Bearer {seller_pat}"},
            json={
                "action_type": "reprice_listing",
                "listing_id": listing["id"],
                "new_price_cents": 13300,
                "idempotency_key": "repr-1",
            },
        )
        prepare_response.raise_for_status()
        assert prepare_response.json()["status"] == "pending"

        approvals = client.get(
            "/api/v1/approval-requests?status=pending",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        approvals.raise_for_status()
        repricing = next(item for item in approvals.json() if item["action_type"] == "reprice_listing")
        receipt = client.post(
            f"/api/v1/approval-requests/{repricing['id']}/approve",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        receipt.raise_for_status()
        assert receipt.json()["receipt"]["result_payload"]["asking_price_cents"] == 13300

        listing_response = client.get(f"/api/v1/listings/{listing['id']}")
        listing_response.raise_for_status()
        assert listing_response.json()["asking_price_cents"] == 13300

        revoke_response = client.post(
            f"/api/v1/agent-grants/{grant['id']}/revoke",
            headers={"Authorization": f"Bearer {seller_token}"},
        )
        revoke_response.raise_for_status()
        assert revoke_response.json()["status"] == "revoked"

        denied_response = client.get(
            "/api/v1/approval-requests",
            headers={"Authorization": f"Bearer {seller_pat}"},
        )
        assert denied_response.status_code == 401
