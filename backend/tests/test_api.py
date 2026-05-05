import io
import os
import uuid

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

        patch_response = client.patch(
            f"/api/v1/draft-listings/{draft['id']}",
            headers={"Authorization": f"Bearer {seller_token}"},
            json={
                "title": "Agent-tested camera",
                "description": "Fully reviewed and ready for mock checkout.",
                "category_slug": "electronics",
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
