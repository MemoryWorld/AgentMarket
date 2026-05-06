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
  product_name?: string | null;
  description: string;
  category_slug: string;
  condition?: string | null;
  condition_score?: number | null;
  brand?: string | null;
  color?: string | null;
  approx_dimensions_text?: string | null;
  intended_use?: string | null;
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

export interface AgentGrant {
  id: string;
  user_id: string;
  personal_access_token_id: string;
  name: string;
  agent_family: string;
  scopes: string[];
  approval_mode: string;
  status: string;
  created_at: string;
  revoked_at?: string | null;
}

export interface AgentGrantCreateResponse extends AgentGrant {
  token: string;
  token_prefix: string;
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
  product_name?: string | null;
  description?: string | null;
  category_slug?: string | null;
  condition?: string | null;
  condition_score?: number | null;
  brand?: string | null;
  color?: string | null;
  approx_dimensions_text?: string | null;
  intended_use?: string | null;
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
  created_at: string;
  updated_at: string;
}

export interface MessageEvent {
  id: string;
  thread_id: string;
  sender_id: string;
  approval_request_id?: string | null;
  kind: string;
  status: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface Offer {
  id: string;
  thread_id: string;
  listing_id: string;
  buyer_id: string;
  seller_id: string;
  created_by_user_id: string;
  approval_request_id?: string | null;
  supersedes_offer_id?: string | null;
  amount_cents: number;
  currency_code: string;
  status: string;
  note?: string | null;
  created_at: string;
  updated_at: string;
}

export interface MessageThread {
  id: string;
  listing_id: string;
  seller_id: string;
  buyer_id: string;
  subject?: string | null;
  status: string;
  last_message_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ThreadDetail extends MessageThread {
  messages: MessageEvent[];
  offers: Offer[];
}

export interface ApprovalRequest {
  id: string;
  owner_user_id: string;
  requested_by_user_id: string;
  agent_grant_id?: string | null;
  status: string;
  action_type: string;
  resource_type: string;
  resource_id?: string | null;
  summary: string;
  diff_payload: Record<string, unknown>;
  action_payload: Record<string, unknown>;
  idempotency_key?: string | null;
  decided_at?: string | null;
  executed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActionReceipt {
  id: string;
  approval_request_id?: string | null;
  owner_user_id: string;
  actor_user_id?: string | null;
  requested_by_user_id?: string | null;
  agent_grant_id?: string | null;
  action_type: string;
  resource_type: string;
  resource_id?: string | null;
  status: string;
  idempotency_key?: string | null;
  result_payload: Record<string, unknown>;
  error_message?: string | null;
  created_at: string;
}

export interface ApprovalDecision {
  approval_request: ApprovalRequest;
  receipt?: ActionReceipt | null;
}
