from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import Base, engine
from app.models import Category, City, CreditWallet, Listing, SellerProfile, User


DEFAULT_CATEGORIES = [
    ("electronics", "Electronics", None, 1),
    ("electronics-phones", "Phones", "electronics", 2),
    ("electronics-laptops", "Laptops", "electronics", 3),
    ("fashion", "Fashion", None, 10),
    ("fashion-shoes", "Shoes", "fashion", 11),
    ("home", "Home", None, 20),
    ("home-furniture", "Furniture", "home", 21),
    ("sports", "Sports", None, 30),
]

DEFAULT_CITIES = [
    ("new-york-us", "New York", "US"),
    ("london-gb", "London", "GB"),
    ("sydney-au", "Sydney", "AU"),
    ("singapore-sg", "Singapore", "SG"),
]


def slugify(value: str) -> str:
    slug = []
    prev_dash = False
    for char in value.lower():
        if char.isalnum():
            slug.append(char)
            prev_dash = False
        elif not prev_dash:
            slug.append("-")
            prev_dash = True
    return "".join(slug).strip("-") or "listing"


async def init_database() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_reference_data(session: AsyncSession) -> None:
    categories = await session.scalar(select(Category.slug).limit(1))
    if not categories:
        session.add_all(
            [Category(slug=slug, name=name, parent_slug=parent, display_order=order) for slug, name, parent, order in DEFAULT_CATEGORIES]
        )

    cities = await session.scalar(select(City.slug).limit(1))
    if not cities:
        session.add_all([City(slug=slug, display_name=name, country_code=country) for slug, name, country in DEFAULT_CITIES])

    demo_user = await session.scalar(select(User).where(User.email == "demo@agentmarketplace.dev"))
    if not demo_user and get_settings().seed_demo_data:
        demo_user = User(
            email="demo@agentmarketplace.dev",
            display_name="Demo Seller",
            city_slug="sydney-au",
            country_code="AU",
        )
        session.add(demo_user)
        await session.flush()
        session.add(SellerProfile(user_id=demo_user.id, handle="demo-seller", bio="Launch inventory seeded for local development."))
        session.add(CreditWallet(user_id=demo_user.id, balance_credits=120))
        session.add(
            Listing(
                seller_id=demo_user.id,
                slug="demo-vintage-camera",
                title="Vintage 35mm Camera",
                description="Film-tested camera body with strap, light cosmetic wear, and a clean lens mount.",
                category_slug="electronics",
                condition="Used - Good",
                brand="RetroCam",
                color="Black",
                attributes={"lens_mount": "Manual", "bundle": "strap included"},
                asking_price_cents=18900,
                currency_code="USD",
                city_slug="sydney-au",
                ai_confidence=0.93,
                ai_source_model="seed-data",
            )
        )

    await session.commit()
