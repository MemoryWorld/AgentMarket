import { getListings, getSeller, formatPrice } from "@/lib/api";

export default async function SellerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const seller = await getSeller(id);
  const searchParams = new URLSearchParams({ seller_id: id });
  const listings = await getListings(searchParams);

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-12">
      <section className="sun-panel rounded-[2rem] p-8">
        <p className="eyebrow text-[var(--color-sea)]">Seller Profile</p>
        <h1 className="display-title mt-2 text-5xl">{seller?.handle ?? "Seller unavailable"}</h1>
        <p className="mt-4 max-w-2xl leading-8 text-[rgba(18,38,63,0.74)]">
          {seller?.bio ?? "Public seller profiles stay crawlable so search engines and agents can attribute inventory correctly."}
        </p>
      </section>

      <section className="mt-8 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {listings.items.map((listing) => (
          <a key={listing.id} href={`/listings/${listing.slug}`} className="surface-card rounded-[1.7rem] p-5 transition-transform hover:-translate-y-1">
            {listing.primary_image_url ? (
              <img src={listing.primary_image_url} alt={listing.title} className="h-56 w-full rounded-[1.2rem] object-cover" />
            ) : (
              <div className="flex h-56 items-center justify-center rounded-[1.2rem] bg-[rgba(11,150,255,0.08)] text-sm text-[rgba(18,38,63,0.6)]">
                No image yet
              </div>
            )}
            <p className="mt-4 text-xl font-semibold">{listing.title}</p>
            <div className="mt-3 flex flex-wrap gap-3">
              <span className="price-chip">{formatPrice(listing.asking_price_cents, listing.currency_code)}</span>
              <span className="price-chip">{listing.city_slug}</span>
            </div>
          </a>
        ))}
      </section>
    </div>
  );
}
