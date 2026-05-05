from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CategoryResponse(BaseSchema):
    slug: str
    name: str
    parent_slug: str | None = None


class CityResponse(BaseSchema):
    slug: str
    display_name: str
    country_code: str


class ListingImageResponse(BaseSchema):
    id: str
    provenance: str
    public_url: str
    width: int | None = None
    height: int | None = None
    position: int


class UserResponse(BaseSchema):
    id: str
    email: EmailStr
    display_name: str
    city_slug: str | None = None
    country_code: str


class SellerProfileResponse(BaseSchema):
    id: str
    handle: str
    bio: str | None = None
    user: UserResponse | None = None


class WalletResponse(BaseSchema):
    balance_credits: int


class OTPRequest(BaseModel):
    email: EmailStr


class OTPRequestResponse(BaseModel):
    sent: bool
    debug_code: str | None = None


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    display_name: str | None = None
    city_slug: str | None = None
    country_code: str | None = None


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    wallet: WalletResponse


class PATCreateRequest(BaseModel):
    name: str
    scopes: list[str]


class PATResponse(BaseSchema):
    id: str
    name: str
    token_prefix: str
    scopes: list[str]
    revoked: bool
    created_at: datetime


class PATCreateResponse(PATResponse):
    token: str


class ListingAutofillOutput(BaseModel):
    title: str
    description: str
    category_path: list[str]
    condition: str
    brand: str | None = None
    color: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    suggested_price: float
    currency_code: str = "USD"
    price_confidence: float
    missing_fields: list[str] = Field(default_factory=list)
    safety_flags: list[str] = Field(default_factory=list)


class DraftCreateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    category_slug: str | None = None
    condition: str | None = None
    brand: str | None = None
    color: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    asking_price_cents: int | None = None
    currency_code: str = "USD"
    city_slug: str | None = None


class DraftUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    category_slug: str | None = None
    condition: str | None = None
    brand: str | None = None
    color: str | None = None
    attributes: dict[str, Any] | None = None
    asking_price_cents: int | None = None
    currency_code: str | None = None
    city_slug: str | None = None


class DraftImageGenerateRequest(BaseModel):
    draft_id: str
    style_preset: str = "clean studio"
    size: str = "1024x1024"
    quality: str = "medium"
    background: str = "auto"


class DraftResponse(BaseSchema):
    id: str
    seller_id: str
    title: str | None = None
    description: str | None = None
    category_slug: str | None = None
    condition: str | None = None
    brand: str | None = None
    color: str | None = None
    attributes: dict[str, Any]
    asking_price_cents: int | None = None
    suggested_price_cents: int | None = None
    currency_code: str
    city_slug: str | None = None
    status: str
    ai_confidence: float | None = None
    ai_missing_fields: list[str]
    ai_safety_flags: list[str]
    ai_source_model: str | None = None
    images: list[ListingImageResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ListingResponse(BaseSchema):
    id: str
    slug: str
    seller_id: str
    title: str
    description: str
    category_slug: str
    condition: str | None = None
    brand: str | None = None
    color: str | None = None
    attributes: dict[str, Any]
    asking_price_cents: int
    currency_code: str
    city_slug: str
    visibility: str
    ai_confidence: float | None = None
    ai_source_model: str | None = None
    images: list[ListingImageResponse] = Field(default_factory=list)
    created_at: datetime


class ListingSummaryResponse(BaseSchema):
    id: str
    slug: str
    title: str
    asking_price_cents: int
    currency_code: str
    city_slug: str
    category_slug: str
    condition: str | None = None
    primary_image_url: str | None = None
    created_at: datetime


class FavoriteResponse(BaseSchema):
    listing_id: str
    created_at: datetime


class ReportRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=255)


class AddressPayload(BaseModel):
    full_name: str
    line1: str
    line2: str | None = None
    city: str
    state: str | None = None
    postal_code: str
    country_code: str
    phone: str | None = None


class OrderCreateRequest(BaseModel):
    listing_id: str


class OrderAddressRequest(BaseModel):
    address: AddressPayload


class OrderPaymentResponse(BaseModel):
    success: bool
    status: str


class OrderStatusUpdateRequest(BaseModel):
    status: str
    carrier: str | None = None
    tracking_number: str | None = None


class OrderResponse(BaseSchema):
    id: str
    listing_id: str
    buyer_id: str
    seller_id: str
    status: str
    address_payload: dict[str, Any] | None = None
    carrier: str | None = None
    tracking_number: str | None = None
    created_at: datetime
    updated_at: datetime


class SearchResponse(BaseModel):
    items: list[ListingSummaryResponse]
    total: int


class TopUpRequest(BaseModel):
    credits: int = Field(ge=1, le=500)


class TopUpResponse(BaseModel):
    balance_credits: int
