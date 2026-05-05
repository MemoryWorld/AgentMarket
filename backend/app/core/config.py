from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
MEDIA_DIR = DATA_DIR / "media"
UPLOAD_DIR = MEDIA_DIR / "uploads"
GENERATED_DIR = MEDIA_DIR / "generated"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Agent Marketplace API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    base_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:3000"
    secret_key: str = "change-me-to-a-very-long-secret-key-value"
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    redis_url: str = "redis://localhost:6379/0"
    expose_debug_otp: bool = True
    default_currency: str = "USD"
    default_country_code: str = "US"
    openai_api_key: str | None = None
    openai_autofill_model: str = "gpt-4.1-mini"
    openai_autofill_fallback_model: str = "gpt-5"
    openai_image_model: str = "gpt-image-1.5"
    media_root: Path = Field(default=MEDIA_DIR)
    upload_root: Path = Field(default=UPLOAD_DIR)
    generated_root: Path = Field(default=GENERATED_DIR)
    seed_demo_data: bool = True


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.media_root.mkdir(parents=True, exist_ok=True)
    settings.upload_root.mkdir(parents=True, exist_ok=True)
    settings.generated_root.mkdir(parents=True, exist_ok=True)
    return settings
