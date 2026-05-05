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

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-8 px-6 py-12 lg:grid-cols-[1fr_0.9fr]">
      <section className="sun-panel rounded-[2rem] p-7">
        <p className="eyebrow text-[var(--color-sea)]">Order Preview</p>
        <h1 className="display-title mt-2 text-5xl">{listing.title}</h1>
        <div className="mt-5 flex flex-wrap gap-3">
          <span className="price-chip">{formatPrice(listing.asking_price_cents, listing.currency_code)}</span>
          <span className="price-chip">{listing.city_slug}</span>
        </div>
        <p className="mt-5 max-w-2xl leading-8 text-[rgba(18,38,63,0.74)]">{listing.description}</p>
        <div className="mt-7 grid gap-4 md:grid-cols-2">
          {listing.images.map((image) => (
            <img
              key={image.id}
              src={image.public_url}
              alt={listing.title}
              className="h-64 w-full rounded-[1.4rem] object-cover"
            />
          ))}
        </div>
      </section>
      <CheckoutFlow listing={listing} />
    </div>
  );
}
