import type { MetadataRoute } from "next";

import { getListings } from "@/lib/api";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";
  const listings = await getListings();
  const now = new Date();
  return [
    { url: siteUrl, lastModified: now },
    { url: `${siteUrl}/sell`, lastModified: now },
    ...listings.items.map((listing) => ({
      url: `${siteUrl}/listings/${listing.slug}`,
      lastModified: new Date(listing.created_at),
    })),
  ];
}
