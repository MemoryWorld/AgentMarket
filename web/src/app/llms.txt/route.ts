export async function GET() {
  const body = `# Agent Marketplace

Purpose: AI-assisted classifieds marketplace with public crawlable inventory.

Public read interfaces:
- GET /api/v1/listings
- GET /api/v1/listings/{id_or_slug}
- GET /api/v1/search
- GET /api/v1/categories
- GET /api/v1/cities
- GET /api/v1/sellers/{id}

Seller-authorized write interfaces:
- POST /api/v1/draft-listings
- POST /api/v1/draft-listings/ai-autofill
- POST /api/v1/draft-listings/ai-image
- PATCH /api/v1/draft-listings/{id}
- POST /api/v1/draft-listings/{id}/publish

Buyer-authorized write interfaces:
- POST /api/v1/orders
- PATCH /api/v1/orders/{id}/address
- POST /api/v1/orders/{id}/mock-pay
- GET /api/v1/orders/{id}

Auth:
- Bearer access token from email OTP
- Personal access token for agent integrations

MCP:
- search_listings
- get_listing
- get_category_tree
- create_listing_draft
- autofill_listing_from_photos
- generate_listing_image
- publish_listing_draft
- create_order
- submit_shipping_address
- confirm_mock_payment
- get_order
`;

  return new Response(body, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
    },
  });
}
