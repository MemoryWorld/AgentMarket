from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router, token_router, wallet_router
from app.api.listings import listing_router, router as draft_router
from app.api.orders import router as orders_router
from app.api.public import router as public_router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.bootstrap import init_database, seed_reference_data


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_database()
    async with SessionLocal() as session:
        await seed_reference_data(session)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=settings.media_root), name="media")

app.include_router(public_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(wallet_router, prefix=settings.api_v1_prefix)
app.include_router(token_router, prefix=settings.api_v1_prefix)
app.include_router(draft_router, prefix=settings.api_v1_prefix)
app.include_router(listing_router, prefix=settings.api_v1_prefix)
app.include_router(orders_router, prefix=settings.api_v1_prefix)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "openapi": f"{settings.base_url}/openapi.json"}
