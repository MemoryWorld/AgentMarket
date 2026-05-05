import { Category, City, Listing, SearchResponse, SellerProfile } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    next: { revalidate: 60 },
  });
  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function getListings(searchParams?: URLSearchParams): Promise<SearchResponse> {
  const suffix = searchParams?.toString() ? `?${searchParams.toString()}` : "";
  try {
    return await fetchJson<SearchResponse>(`/listings${suffix}`);
  } catch {
    return { items: [], total: 0 };
  }
}

export async function getListing(slug: string): Promise<Listing | null> {
  try {
    return await fetchJson<Listing>(`/listings/${slug}`);
  } catch {
    return null;
  }
}

export async function getCategories(): Promise<Category[]> {
  try {
    return await fetchJson<Category[]>("/categories");
  } catch {
    return [];
  }
}

export async function getCities(): Promise<City[]> {
  try {
    return await fetchJson<City[]>("/cities");
  } catch {
    return [];
  }
}

export async function getSeller(id: string): Promise<SellerProfile | null> {
  try {
    return await fetchJson<SellerProfile>(`/sellers/${id}`);
  } catch {
    return null;
  }
}

export function formatPrice(amountCents: number, currencyCode: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currencyCode,
    maximumFractionDigits: 0,
  }).format(amountCents / 100);
}
