"""Exercise the actual API against an isolated, disposable PostgreSQL database.

POSTGRES_TEST_URL must name a test server whose role can create databases.
The supplied database is never migrated or cleared. Only the generated database
is created/dropped. Model calls, payments and email delivery remain local mocks.
"""

import asyncio
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import uuid

import asyncpg
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def provision(url, database, *, drop=False):
    connection = await asyncpg.connect(url.set(drivername="postgresql").render_as_string(hide_password=False))
    try:
        # The identifier is generated below, never supplied by the environment.
        assert database.startswith("marketplace_verify_") and database.isidentifier()
        if drop:
            await connection.execute(f'DROP DATABASE "{database}" WITH (FORCE)')
        else:
            await connection.execute(f'CREATE DATABASE "{database}"')
    finally:
        await connection.close()


def exercise(client):
    def request(method, path, token=None, **kwargs):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = client.request(method, "/api/v1" + path, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()

    def login(name):
        email = f"{name}@example.com"
        otp = request("POST", "/auth/email/request-code", json={"email": email})
        return request("POST", "/auth/email/verify", json={"email": email, "code": otp["debug_code"],
                       "display_name": name, "city_slug": "sydney-au", "country_code": "AU"})["access_token"]

    seller, buyer = login("postgres-seller"), login("postgres-buyer")
    image = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(image, "JPEG")
    draft = request("POST", "/draft-listings/ai-autofill", seller,
                    files=[("files", ("camera.jpg", image.getvalue(), "image/jpeg"))],
                    data={"city_slug": "sydney-au", "currency_code": "USD"})
    assert draft["ai_source_model"] == "mock-autofill"
    request("PATCH", f"/draft-listings/{draft['id']}", seller, json={
        "title": "Postgres fixture camera", "product_name": "Fixture camera", "description": "Synthetic test item",
        "category_slug": "electronics", "condition": "Used - Good", "condition_score": 7,
        "brand": "Fixture", "approx_dimensions_text": "10 x 10 cm", "intended_use": "Test display",
        "city_slug": "sydney-au", "asking_price_cents": 12000,
    })
    listing = request("POST", f"/draft-listings/{draft['id']}/publish", seller)
    grant = request("POST", "/agent-grants", seller, json={"name": "Postgres test agent", "agent_family": "test",
                    "scopes": ["listings:write", "approvals:read", "approvals:write", "receipts:read"]})
    payload = {"action_type": "reprice_listing", "listing_id": listing["id"],
               "new_price_cents": 11000, "idempotency_key": "postgres-reprice-1"}
    approval = request("POST", "/approval-requests", grant["token"], json=payload)
    assert request("POST", "/approval-requests", grant["token"], json=payload)["id"] == approval["id"]
    forbidden = client.post(f"/api/v1/approval-requests/{approval['id']}/approve",
                            headers={"Authorization": f"Bearer {grant['token']}"})
    assert forbidden.status_code == 403
    decision = request("POST", f"/approval-requests/{approval['id']}/approve", seller)
    assert decision["receipt"]["status"] == "succeeded"
    replay = request("POST", f"/approval-requests/{approval['id']}/approve", seller)
    assert replay["receipt"]["id"] == decision["receipt"]["id"]
    assert request("GET", f"/listings/{listing['id']}")["asking_price_cents"] == 11000
    order = request("POST", "/orders", buyer, json={"listing_id": listing["id"]})
    request("PATCH", f"/orders/{order['id']}/address", buyer, json={"address": {
        "full_name": "Fixture Buyer", "line1": "1 Example Street", "city": "Sydney",
        "postal_code": "2000", "country_code": "AU",
    }})
    assert request("POST", f"/orders/{order['id']}/mock-pay", buyer)["status"] == "paid"
    assert request("GET", f"/orders/{order['id']}", buyer)["status"] == "paid"
    request("POST", f"/agent-grants/{grant['id']}/revoke", seller)
    revoked = client.get("/api/v1/approval-requests", headers={"Authorization": f"Bearer {grant['token']}"})
    assert revoked.status_code == 401
    return ["registration", "mock vision draft", "review/publish", "scoped grant", "prepare replay",
            "human-only approval", "decision replay", "receipt", "repricing", "order", "mock checkout", "revocation"]


def main():
    raw = os.environ.get("POSTGRES_TEST_URL")
    if not raw:
        raise SystemExit("Set POSTGRES_TEST_URL to a disposable test server (postgresql+asyncpg://...).")
    url = make_url(raw)
    if url.drivername != "postgresql+asyncpg":
        raise SystemExit("POSTGRES_TEST_URL must use postgresql+asyncpg.")
    database = "marketplace_verify_" + uuid.uuid4().hex[:16]
    asyncio.run(provision(url, database))
    try:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.environ.update(DATABASE_URL=url.set(database=database).render_as_string(hide_password=False),
                              OPENAI_API_KEY="", EXPOSE_DEBUG_OTP="true", SEED_DEMO_DATA="false",
                              MEDIA_ROOT=str(root), UPLOAD_ROOT=str(root / "uploads"), GENERATED_ROOT=str(root / "generated"))
            from app.core.config import Settings
            Settings.model_config["env_file"] = None
            from app.main import app
            from app.db.session import engine

            async def inspect_database():
                async with engine.connect() as connection:
                    revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                    version = await connection.scalar(text("SELECT version()"))
                    receipts = await connection.scalar(text("SELECT count(*) FROM action_receipts"))
                return revision, version, receipts

            with TestClient(app) as client:
                try:
                    checks = exercise(client)
                    revision, version, receipts = client.portal.call(inspect_database)
                    assert revision == "0004_approval_integrity" and receipts == 1
                finally:
                    client.portal.call(engine.dispose)
            print(json.dumps({"status": "passed", "database": "isolated disposable PostgreSQL", "server": version,
                              "alembic_revision": revision, "checks": checks,
                              "external_models": "not called", "payment": "mock"}, indent=2))
    finally:
        asyncio.run(provision(url, database, drop=True))


if __name__ == "__main__":
    main()
