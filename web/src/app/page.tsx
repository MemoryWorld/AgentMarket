import { formatPrice, getCategories, getCities, getListings } from "@/lib/api";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const q = typeof params.q === "string" ? params.q : undefined;
  const citySlug = typeof params.city_slug === "string" ? params.city_slug : undefined;
  const listingQuery = new URLSearchParams();
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
  const backendRoot = apiBaseUrl.replace(/\/api\/v1$/, "");

  if (q) listingQuery.set("q", q);
  if (citySlug) listingQuery.set("city_slug", citySlug);

  const [categories, cities, listings] = await Promise.all([
    getCategories(),
    getCities(),
    getListings(listingQuery),
  ]);

  const featuredCategories = categories.slice(0, 8);
  const featuredListings = listings.items.slice(0, 6);

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <section className="surface-card relative overflow-hidden rounded-[2.6rem] px-7 py-8 md:px-10 md:py-10">
        <div className="pointer-events-none absolute right-[-5rem] top-[-3rem] h-52 w-52 rounded-full bg-[rgba(255,216,77,0.46)] blur-3xl" />
        <div className="pointer-events-none absolute bottom-[-4rem] left-[-2rem] h-56 w-56 rounded-full bg-[rgba(11,150,255,0.12)] blur-3xl" />
        <div className="relative grid gap-10 lg:grid-cols-[1.08fr_0.92fr]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-[rgba(18,38,63,0.08)] bg-white/78 px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-[rgba(18,38,63,0.72)]">
              Bright yellow MVP
            </div>
            <p className="eyebrow mt-5 text-[var(--color-sea)]">AI pre-fill + GPT image + open crawling</p>
            <h1 className="display-title mt-4 text-6xl text-[var(--color-ink)] md:text-7xl">
              A brighter marketplace for humans first and agents by default.
            </h1>
            <p className="mt-6 max-w-2xl text-lg leading-8 text-[rgba(18,38,63,0.76)]">
              Feed-style discovery, AI-assisted selling, mock checkout, and fully crawlable public inventory in one compact marketplace MVP.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a href="/sell" className="button-primary inline-flex">Start selling with AI</a>
              <a href="/llms.txt" className="button-secondary inline-flex">Read llms.txt</a>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              <div className="soft-panel rounded-[1.4rem] p-4">
                <p className="eyebrow text-[rgba(18,38,63,0.54)]">Public inventory</p>
                <p className="mt-3 text-3xl font-semibold">{listings.total}</p>
                <p className="mt-2 text-sm text-[rgba(18,38,63,0.68)]">Every public listing is crawlable in HTML and JSON.</p>
              </div>
              <div className="soft-panel rounded-[1.4rem] p-4">
                <p className="eyebrow text-[rgba(18,38,63,0.54)]">Launch cities</p>
                <p className="mt-3 text-3xl font-semibold">{cities.length}</p>
                <p className="mt-2 text-sm text-[rgba(18,38,63,0.68)]">Local-market browsing stays simple and fast.</p>
              </div>
              <div className="soft-panel rounded-[1.4rem] p-4">
                <p className="eyebrow text-[rgba(18,38,63,0.54)]">Seed categories</p>
                <p className="mt-3 text-3xl font-semibold">{categories.length}</p>
                <p className="mt-2 text-sm text-[rgba(18,38,63,0.68)]">Enough taxonomy to prove the workflow end to end.</p>
              </div>
            </div>
          </div>

          <div className="relative space-y-4">
            <div className="sun-panel rounded-[2rem] p-6">
              <p className="eyebrow text-[rgba(18,38,63,0.68)]">MVP lanes</p>
              <div className="mt-4 grid gap-3">
                <div className="rounded-[1.4rem] bg-white/66 p-4">
                  <span className="step-pill">01</span>
                  <p className="mt-3 text-lg font-semibold">Sell with AI</p>
                  <p className="mt-2 text-sm leading-6 text-[rgba(18,38,63,0.72)]">Request OTP, upload photos, draft faster, and spend credits on a cleaner sale image.</p>
                </div>
                <div className="rounded-[1.4rem] bg-white/66 p-4">
                  <span className="step-pill">02</span>
                  <p className="mt-3 text-lg font-semibold">Buy through mock checkout</p>
                  <p className="mt-2 text-sm leading-6 text-[rgba(18,38,63,0.72)]">Keep the buyer flow tangible now without pretending payments are fully live.</p>
                </div>
                <div className="rounded-[1.4rem] bg-white/66 p-4">
                  <span className="step-pill">03</span>
                  <p className="mt-3 text-lg font-semibold">Expose everything to agents</p>
                  <p className="mt-2 text-sm leading-6 text-[rgba(18,38,63,0.72)]">Listings, seller pages, llms.txt, REST, OpenAPI, and MCP all point to the same public inventory.</p>
                </div>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="soft-panel rounded-[1.6rem] p-5">
                <p className="eyebrow text-[var(--color-coral)]">Launch cities</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {cities.slice(0, 4).map((city) => (
                    <span key={city.slug} className="price-chip">
                      {city.display_name}
                    </span>
                  ))}
                  {!cities.length ? <span className="text-sm text-[rgba(18,38,63,0.66)]">Add launch cities in the backend seed data.</span> : null}
                </div>
              </div>
              <div className="sky-panel rounded-[1.6rem] p-5">
                <p className="eyebrow text-[var(--color-sea)]">Crawler policy</p>
                <p className="mt-4 text-sm leading-7 text-[rgba(18,38,63,0.72)]">
                  Public listing pages, category views, seller pages, and read APIs stay open. Auth gates only protect writes, AI generation, and checkout transitions.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mt-8 grid gap-8 lg:grid-cols-[0.78fr_1.22fr]">
        <aside className="sun-panel rounded-[2rem] p-7">
          <p className="eyebrow text-[rgba(18,38,63,0.68)]">Search the market</p>
          <h2 className="mt-3 text-3xl font-semibold text-[var(--color-ink)]">Local, open, and already indexable.</h2>
          <form className="mt-5 space-y-4" action="/" method="get">
            <input className="field" type="text" name="q" defaultValue={q ?? ""} placeholder="Search listings, brands, or product names" />
            <select className="field" name="city_slug" defaultValue={citySlug ?? ""}>
              <option value="">All launch cities</option>
              {cities.map((city) => (
                <option key={city.slug} value={city.slug}>
                  {city.display_name} ({city.country_code})
                </option>
              ))}
            </select>
            <button className="button-primary w-full" type="submit">Search public listings</button>
          </form>

          <div className="mt-7">
            <p className="eyebrow text-[rgba(18,38,63,0.68)]">Category seed</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {featuredCategories.map((category) => (
                <span key={category.slug} className="rounded-full border border-[rgba(18,38,63,0.08)] bg-white/68 px-3 py-2 text-sm font-medium">
                  {category.name}
                </span>
              ))}
              {!featuredCategories.length ? <span className="text-sm text-[rgba(18,38,63,0.66)]">Category seeds will show up here once the API is available.</span> : null}
            </div>
          </div>

          <div className="soft-panel mt-7 rounded-[1.6rem] p-5">
            <p className="font-semibold text-[var(--color-ink)]">Crawler-ready by default</p>
            <p className="mt-2 text-sm leading-7 text-[rgba(18,38,63,0.72)]">
              Public listing pages, seller pages, `llms.txt`, `robots.txt`, `sitemap.xml`, and read APIs are part of the MVP surface from day one.
            </p>
          </div>
        </aside>

        <section>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="eyebrow text-[var(--color-sea)]">Marketplace feed</p>
              <h2 className="display-title mt-2 text-4xl">Scroll the public catalog.</h2>
            </div>
            <div className="soft-panel rounded-[1.4rem] px-4 py-3 text-sm font-semibold text-[var(--color-ink)]">
              {listings.total} live listings
            </div>
          </div>

          {featuredListings.length ? (
            <div className="mt-5 grid gap-5 md:grid-cols-2">
              {featuredListings.map((listing) => (
                <a
                  key={listing.id}
                  href={`/listings/${listing.slug}`}
                  className="surface-card rounded-[1.8rem] p-5 transition-transform hover:-translate-y-1"
                >
                  {listing.primary_image_url ? (
                    <img src={listing.primary_image_url} alt={listing.title} className="h-56 w-full rounded-[1.3rem] object-cover" />
                  ) : (
                    <div className="flex h-56 items-center justify-center rounded-[1.3rem] bg-[rgba(11,150,255,0.08)] text-sm text-[rgba(18,38,63,0.6)]">
                      No image yet
                    </div>
                  )}
                  <div className="mt-4 flex items-start justify-between gap-4">
                    <p className="text-xl font-semibold leading-7">{listing.title}</p>
                    <span className="rounded-full bg-[rgba(11,150,255,0.1)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.14em] text-[var(--color-sea)]">
                      {listing.category_slug}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-3">
                    <span className="price-chip">{formatPrice(listing.asking_price_cents, listing.currency_code)}</span>
                    <span className="price-chip">{listing.city_slug}</span>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-[rgba(18,38,63,0.68)]">
                    {listing.condition ?? "Used item"} • Crawlable HTML page • Agent-readable JSON
                  </p>
                </a>
              ))}
            </div>
          ) : (
            <div className="surface-card mt-5 rounded-[1.8rem] p-6">
              <p className="text-lg font-semibold">No public listings yet.</p>
              <p className="mt-2 max-w-2xl text-sm leading-7 text-[rgba(18,38,63,0.72)]">
                The browse experience is ready. Seed a few listings from the seller studio or the backend bootstrap data to make the feed feel alive.
              </p>
              <a href="/sell" className="button-primary mt-5 inline-flex">Open seller studio</a>
            </div>
          )}
        </section>
      </section>

      <section className="mt-8 grid gap-5 md:grid-cols-3">
        <div className="soft-panel rounded-[1.8rem] p-6">
          <p className="eyebrow text-[var(--color-coral)]">Seller Studio</p>
          <h3 className="mt-2 text-2xl font-semibold">OTP, draft, image, publish.</h3>
          <p className="mt-3 text-sm leading-7 text-[rgba(18,38,63,0.72)]">
            The seller workflow stays intentionally linear so the MVP can prove AI autofill and prepaid image generation without clutter.
          </p>
          <a href="/sell" className="link-chip mt-5">Open seller flow</a>
        </div>
        <div className="soft-panel rounded-[1.8rem] p-6">
          <p className="eyebrow text-[var(--color-sea)]">Mock Checkout</p>
          <h3 className="mt-2 text-2xl font-semibold">Buyer path is visible today.</h3>
          <p className="mt-3 text-sm leading-7 text-[rgba(18,38,63,0.72)]">
            Buyers can request OTP, submit an address, and confirm a mock payment so the order lifecycle feels real enough to demo.
          </p>
          <span className="link-chip mt-5">Listing pages route into checkout</span>
        </div>
        <div className="sky-panel rounded-[1.8rem] p-6">
          <p className="eyebrow text-[var(--color-sea)]">Agent Surface</p>
          <h3 className="mt-2 text-2xl font-semibold">Humans and crawlers see the same catalog.</h3>
          <p className="mt-3 text-sm leading-7 text-[rgba(18,38,63,0.72)]">
            Public HTML, REST, OpenAPI, and MCP all reflect one inventory model, which is the core proof this product is agent-ready.
          </p>
          <a href={`${backendRoot}/openapi.json`} className="link-chip mt-5">Open OpenAPI spec</a>
        </div>
      </section>

      <section className="surface-card mt-8 rounded-[2rem] p-7">
        <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <p className="eyebrow text-[var(--color-coral)]">Public API Surface</p>
            <h2 className="display-title mt-2 text-4xl">Ship the marketplace, not just the mockup.</h2>
            <p className="mt-4 max-w-2xl text-base leading-8 text-[rgba(18,38,63,0.74)]">
              This MVP already exposes the crawlable documents that search engines, LLM tools, and agent frameworks expect. The web UI now matches that ambition with a brighter marketplace tone instead of a muted editorial palette.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <a href="/llms.txt" className="link-chip justify-between">llms.txt <span>→</span></a>
            <a href="/robots.txt" className="link-chip justify-between">robots.txt <span>→</span></a>
            <a href="/sitemap.xml" className="link-chip justify-between">sitemap.xml <span>→</span></a>
            <a href={`${backendRoot}/openapi.json`} className="link-chip justify-between">OpenAPI <span>→</span></a>
          </div>
        </div>
      </section>
    </div>
  );
}
