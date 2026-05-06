import { notFound } from "next/navigation";

import { CheckoutFlow } from "@/components/checkout-flow";
import { formatPrice, getListing } from "@/lib/api";

export default async function CheckoutPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const listing = await getListing(slug);

  if (!listing) {
    notFound();
  }

  const factItems = [
    { label: "Product", value: listing.product_name ?? listing.title },
    { label: "Brand", value: listing.brand },
    { label: "Condition", value: listing.condition },
    { label: "Condition score", value: listing.condition_score ? `${listing.condition_score}/10` : null },
    { label: "Approx. size", value: listing.approx_dimensions_text },
    { label: "Best use", value: listing.intended_use },
  ].filter((item) => item.value);

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-8 px-6 py-12 lg:grid-cols-[1fr_0.9fr]">
      <section className="sun-panel rounded-[2rem] p-7">
        <p className="eyebrow text-[var(--color-sea)]">Order Preview</p>
        <h1 className="display-title mt-2 text-5xl">{listing.title}</h1>
        {listing.product_name && listing.product_name !== listing.title ? (
          <p className="mt-3 text-lg font-semibold text-[rgba(18,38,63,0.72)]">{listing.product_name}</p>
        ) : null}
        <div className="mt-5 flex flex-wrap gap-3">
          <span className="price-chip">{formatPrice(listing.asking_price_cents, listing.currency_code)}</span>
          <span className="price-chip">{listing.city_slug}</span>
          {listing.condition ? <span className="price-chip">{listing.condition}</span> : null}
        </div>
        <p className="mt-5 max-w-2xl leading-8 text-[rgba(18,38,63,0.74)]">{listing.description}</p>
        {factItems.length ? (
          <div className="mt-6 grid gap-3 md:grid-cols-2">
            {factItems.map((item) => (
              <div key={item.label} className="rounded-[1.3rem] bg-white/66 p-4">
                <p className="eyebrow text-[rgba(18,38,63,0.54)]">{item.label}</p>
                <p className="mt-2 font-semibold text-[var(--color-ink)]">{item.value}</p>
              </div>
            ))}
          </div>
        ) : null}
        <div className="mt-7 grid gap-4 md:grid-cols-2">
          {listing.images.map((image) => (
            <img
              key={image.id}
              src={image.public_url}
              alt={listing.product_name ?? listing.title}
              className="h-64 w-full rounded-[1.4rem] object-cover"
            />
          ))}
        </div>
      </section>
      <CheckoutFlow listing={listing} />
    </div>
  );
}
