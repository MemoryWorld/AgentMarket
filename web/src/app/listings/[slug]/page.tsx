import { notFound } from "next/navigation";

import { formatPrice, getListing, getSeller } from "@/lib/api";

export default async function ListingPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const listing = await getListing(slug);

  if (!listing) {
    notFound();
  }

  const seller = await getSeller(listing.seller_id);
  const factItems = [
    { label: "Product", value: listing.product_name ?? listing.title },
    { label: "Brand", value: listing.brand },
    { label: "Condition", value: listing.condition },
    { label: "Condition score", value: listing.condition_score ? `${listing.condition_score}/10` : null },
    { label: "Approx. size", value: listing.approx_dimensions_text },
    { label: "Best use", value: listing.intended_use },
  ].filter((item) => item.value);
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: listing.product_name ?? listing.title,
    description: listing.description,
    category: listing.category_slug,
    image: listing.images.map((image) => image.public_url),
    brand: listing.brand
      ? {
          "@type": "Brand",
          name: listing.brand,
        }
      : undefined,
    additionalProperty: factItems.map((item) => ({
      "@type": "PropertyValue",
      name: item.label,
      value: item.value,
    })),
    offers: {
      "@type": "Offer",
      priceCurrency: listing.currency_code,
      price: (listing.asking_price_cents / 100).toFixed(2),
      availability: "https://schema.org/InStock",
    },
    seller: seller?.handle
      ? {
          "@type": "Person",
          name: seller.handle,
        }
      : undefined,
  };

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-8 px-6 py-12 lg:grid-cols-[1.15fr_0.85fr]">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <section className="surface-card relative overflow-hidden rounded-[2rem] p-7">
        <div className="pointer-events-none absolute right-[-4rem] top-[-3rem] h-44 w-44 rounded-full bg-[rgba(255,216,77,0.34)] blur-3xl" />
        <div className="relative">
          <p className="eyebrow text-[var(--color-coral)]">Public Listing</p>
          <h1 className="display-title mt-2 text-5xl">{listing.title}</h1>
          {listing.product_name && listing.product_name !== listing.title ? (
            <p className="mt-3 text-lg font-semibold text-[rgba(18,38,63,0.72)]">{listing.product_name}</p>
          ) : null}
          <div className="mt-5 flex flex-wrap gap-3">
            <span className="price-chip">{formatPrice(listing.asking_price_cents, listing.currency_code)}</span>
            <span className="price-chip">{listing.city_slug}</span>
            <span className="price-chip">{listing.condition ?? "Used item"}</span>
            {listing.condition_score ? <span className="price-chip">{listing.condition_score}/10 condition</span> : null}
          </div>
          <p className="mt-5 max-w-3xl leading-8 text-[rgba(18,38,63,0.74)]">{listing.description}</p>

          {factItems.length ? (
            <div className="mt-7 grid gap-4 md:grid-cols-2">
              {factItems.map((item) => (
                <div key={item.label} className="soft-panel rounded-[1.4rem] p-4">
                  <p className="eyebrow text-[rgba(18,38,63,0.54)]">{item.label}</p>
                  <p className="mt-2 text-base font-semibold text-[var(--color-ink)]">{item.value}</p>
                </div>
              ))}
            </div>
          ) : null}

          <div className="mt-7 grid gap-4 md:grid-cols-2">
            {listing.images.length ? (
              listing.images.map((image) => (
                <figure key={image.id} className="overflow-hidden rounded-[1.4rem] border border-[rgba(18,38,63,0.08)] bg-white">
                  <img src={image.public_url} alt={listing.product_name ?? listing.title} className="h-72 w-full object-cover" />
                  <figcaption className="px-4 py-3 text-sm text-[rgba(18,38,63,0.72)]">
                    {image.provenance === "ai_generated" ? "AI-generated sale image" : "Original seller photo"}
                  </figcaption>
                </figure>
              ))
            ) : (
              <div className="rounded-[1.4rem] border border-dashed border-[rgba(18,38,63,0.22)] p-10 text-sm text-[rgba(18,38,63,0.65)]">
                No images were attached to this listing yet.
              </div>
            )}
          </div>
        </div>
      </section>

      <aside className="space-y-6">
        <div className="sun-panel rounded-[2rem] p-7">
          <p className="eyebrow text-[var(--color-sea)]">Buy Flow</p>
          <h2 className="display-title mt-2 text-4xl">Mock checkout now, real agent handoff later.</h2>
          <p className="mt-4 text-sm leading-7 text-[rgba(18,38,63,0.72)]">
            v1 intentionally keeps the public catalog crawlable while protecting writes and checkout state transitions behind auth.
          </p>
          <a href={`/checkout/${listing.slug}`} className="button-primary mt-6 inline-flex">Buy now</a>
        </div>

        <div className="soft-panel rounded-[2rem] p-7">
          <p className="eyebrow text-[var(--color-coral)]">Seller</p>
          <p className="mt-2 text-xl font-semibold">{seller?.handle ?? "Marketplace seller"}</p>
          <p className="mt-3 text-sm leading-7 text-[rgba(18,38,63,0.72)]">
            {seller?.bio ?? "Seller profile available through the public REST API and public profile page."}
          </p>
          <a href={`/sellers/${listing.seller_id}`} className="button-secondary mt-5 inline-flex">View seller page</a>
        </div>

        <div className="sky-panel rounded-[2rem] p-7">
          <p className="eyebrow text-[var(--color-sea)]">Agent Access</p>
          <ul className="mt-3 space-y-2 text-sm leading-7 text-[rgba(18,38,63,0.72)]">
            <li>REST search and listing detail endpoints are public.</li>
            <li>Seller-authorized writes are available via PAT or bearer tokens.</li>
            <li>The same checkout states are mirrored through MCP tools.</li>
          </ul>
        </div>
      </aside>
    </div>
  );
}
