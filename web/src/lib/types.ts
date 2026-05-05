export interface ListingImage {
  id: string;
  provenance: string;
  public_url: string;
  width?: number | null;
  height?: number | null;
  position: number;
}

export interface ListingSummary {
  id: string;
  slug: string;
  title: string;
  asking_price_cents: number;
  currency_code: string;
  city_slug: string;
  category_slug: string;
  condition?: string | null;
  primary_image_url?: string | null;
  created_at: string;
}

export interface Listing {
  id: string;
  slug: string;
  seller_id: string;
  title: string;
  description: string;
  category_slug: string;
  condition?: string | null;
  brand?: string | null;
  color?: string | null;
  attributes: Record<string, string | number | boolean>;
  asking_price_cents: number;
  currency_code: string;
  city_slug: string;
  visibility: string;
  ai_confidence?: number | null;
  ai_source_model?: string | null;
  images: ListingImage[];
  created_at: string;
}

export interface SearchResponse {
  items: ListingSummary[];
  total: number;
}

export interface Category {
  slug: string;
  name: string;
  parent_slug?: string | null;
}

export interface City {
  slug: string;
  display_name: string;
  country_code: string;
}

export interface User {
  id: string;
  email: string;
  display_name: string;
  city_slug?: string | null;
  country_code: string;
}

export interface SellerProfile {
  id: string;
  handle: string;
  bio?: string | null;
  user?: User | null;
}

export interface Draft {
  id: string;
  seller_id: string;
  title?: string | null;
  description?: string | null;
  category_slug?: string | null;
  condition?: string | null;
  brand?: string | null;
  color?: string | null;
  attributes: Record<string, string | number | boolean>;
  asking_price_cents?: number | null;
  suggested_price_cents?: number | null;
  currency_code: string;
  city_slug?: string | null;
  status: string;
  ai_confidence?: number | null;
  ai_missing_fields: string[];
  ai_safety_flags: string[];
  ai_source_model?: string | null;
  images: ListingImage[];
  created_at: string;
  updated_at: string;
}

export interface Wallet {
  balance_credits: number;
}

export interface Order {
  id: string;
  listing_id: string;
  buyer_id: string;
  seller_id: string;
  status: string;
  address_payload?: Record<string, string> | null;
  carrier?: string | null;
  tracking_number?: string | null;
}
