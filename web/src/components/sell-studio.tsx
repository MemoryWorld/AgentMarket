"use client";

import { FormEvent, useEffect, useState } from "react";

import { apiUrl } from "@/lib/api";
import { Category, City, Draft, Wallet } from "@/lib/types";

const TOKEN_KEY = "agent-marketplace-access-token";

async function readJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail ?? `Request failed with ${response.status}`);
  }
  return payload as T;
}

function tokenHeaders(token: string) {
  return {
    Authorization: `Bearer ${token}`,
  };
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected error. Please try again.";
}

function normalizeOptionalText(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

export function SellStudio() {
  const [token, setToken] = useState<string>("");
  const [email, setEmail] = useState("seller@example.com");
  const [displayName, setDisplayName] = useState("Seller Agent");
  const [otp, setOtp] = useState("");
  const [debugCode, setDebugCode] = useState<string>("");
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [cities, setCities] = useState<City[]>([]);
  const [activeDraft, setActiveDraft] = useState<Draft | null>(null);
  const [status, setStatus] = useState<string>("Authenticate to start creating listings.");
  const [title, setTitle] = useState("");
  const [productName, setProductName] = useState("");
  const [description, setDescription] = useState("");
  const [categorySlug, setCategorySlug] = useState("electronics");
  const [conditionLabel, setConditionLabel] = useState("Used - Good");
  const [conditionScore, setConditionScore] = useState("7");
  const [brand, setBrand] = useState("");
  const [approxDimensionsText, setApproxDimensionsText] = useState("");
  const [intendedUse, setIntendedUse] = useState("");
  const [citySlug, setCitySlug] = useState("sydney-au");
  const [askingPrice, setAskingPrice] = useState("4900");
  const [uploadFiles, setUploadFiles] = useState<FileList | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [publishedSlug, setPublishedSlug] = useState<string | null>(null);

  function applyDraft(draft: Draft | null) {
    setActiveDraft(draft);
    if (!draft) {
      setTitle("");
      setProductName("");
      setDescription("");
      setCategorySlug("electronics");
      setConditionLabel("Used - Good");
      setConditionScore("7");
      setBrand("");
      setApproxDimensionsText("");
      setIntendedUse("");
      setCitySlug("sydney-au");
      setAskingPrice("4900");
      return;
    }

    setTitle(draft.title ?? "");
    setProductName(draft.product_name ?? draft.title ?? "");
    setDescription(draft.description ?? "");
    setCategorySlug(draft.category_slug ?? "electronics");
    setConditionLabel(draft.condition ?? "Used - Good");
    setConditionScore(String(draft.condition_score ?? 7));
    setBrand(draft.brand ?? "");
    setApproxDimensionsText(draft.approx_dimensions_text ?? "");
    setIntendedUse(draft.intended_use ?? "");
    setCitySlug(draft.city_slug ?? "sydney-au");
    setAskingPrice(String(draft.asking_price_cents ?? draft.suggested_price_cents ?? 4900));
  }

  function parsePriceInput() {
    const parsed = Number.parseInt(askingPrice, 10);
    if (Number.isNaN(parsed) || parsed < 0) {
      throw new Error("Enter a valid asking price in cents.");
    }
    return parsed;
  }

  function parseConditionScoreInput() {
    const parsed = Number.parseInt(conditionScore, 10);
    if (Number.isNaN(parsed) || parsed < 1 || parsed > 10) {
      throw new Error("Condition score must be a number from 1 to 10.");
    }
    return parsed;
  }

  async function refreshWallet(accessToken = token) {
    const nextWallet = await readJson<Wallet>(apiUrl("/wallet"), {
      headers: tokenHeaders(accessToken),
    });
    setWallet(nextWallet);
  }

  async function refreshDrafts(accessToken = token, preferredDraftId?: string) {
    const items = await readJson<Draft[]>(apiUrl("/draft-listings"), {
      headers: tokenHeaders(accessToken),
    });
    setDrafts(items);
    const nextDraft = items.find((item) => item.id === preferredDraftId) ?? items[0] ?? null;
    applyDraft(nextDraft);
    return items;
  }

  async function runBusyAction(name: string, work: () => Promise<void>) {
    if (busyAction) return;
    setBusyAction(name);
    try {
      await work();
    } catch (error) {
      setStatus(getErrorMessage(error));
    } finally {
      setBusyAction(null);
    }
  }

  function isBusy(name: string) {
    return busyAction === name;
  }

  useEffect(() => {
    void (async () => {
      try {
        const [nextCategories, nextCities] = await Promise.all([
          readJson<Category[]>(apiUrl("/categories")),
          readJson<City[]>(apiUrl("/cities")),
        ]);
        setCategories(nextCategories);
        setCities(nextCities);
      } catch {
        // Keep fallback text inputs/select values if public metadata is unavailable.
      }
    })();
  }, []);

  useEffect(() => {
    const stored = window.localStorage.getItem(TOKEN_KEY);
    if (!stored) {
      return;
    }
    queueMicrotask(() => {
      setToken(stored);
    });
  }, []);

  useEffect(() => {
    if (!token) {
      window.localStorage.removeItem(TOKEN_KEY);
      return;
    }

    window.localStorage.setItem(TOKEN_KEY, token);

    let cancelled = false;

    void (async () => {
      try {
        const [nextWallet, items] = await Promise.all([
          readJson<Wallet>(apiUrl("/wallet"), {
            headers: tokenHeaders(token),
          }),
          readJson<Draft[]>(apiUrl("/draft-listings"), {
            headers: tokenHeaders(token),
          }),
        ]);

        if (cancelled) return;

        setWallet(nextWallet);
        setDrafts(items);
        applyDraft(items[0] ?? null);
        setStatus("Authenticated. Seller workspace synced.");
      } catch (error) {
        if (!cancelled) {
          setStatus(getErrorMessage(error));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token]);

  function requestOtp(event: FormEvent) {
    event.preventDefault();
    void runBusyAction("request-otp", async () => {
      setStatus("Requesting debug OTP...");
      const response = await readJson<{ sent: boolean; debug_code?: string | null }>(apiUrl("/auth/email/request-code"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      setDebugCode(response.debug_code ?? "");
      setStatus("OTP issued. Use the debug code shown below to sign in.");
    });
  }

  function verifyOtp(event: FormEvent) {
    event.preventDefault();
    void runBusyAction("verify-otp", async () => {
      setStatus("Verifying OTP...");
      const response = await readJson<{ access_token: string }>(apiUrl("/auth/email/verify"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          code: otp,
          display_name: displayName,
          city_slug: citySlug,
          country_code: "AU",
        }),
      });
      setPublishedSlug(null);
      setToken(response.access_token);
      setStatus("Authenticated. Your seller token is stored locally in this browser.");
    });
  }

  function topUpCredits() {
    void runBusyAction("top-up-credits", async () => {
      if (!token) {
        throw new Error("Authenticate before topping up credits.");
      }
      const nextWallet = await readJson<Wallet>(apiUrl("/wallet/top-up"), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ credits: 40 }),
      });
      setWallet(nextWallet);
      setStatus("Added 40 mock prepaid credits.");
    });
  }

  function createManualDraft(event: FormEvent) {
    event.preventDefault();
    void runBusyAction("create-draft", async () => {
      if (!token) {
        throw new Error("Authenticate before creating a draft.");
      }
      const draft = await readJson<Draft>(apiUrl("/draft-listings"), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          title,
          product_name: productName,
          description,
          category_slug: categorySlug,
          condition: normalizeOptionalText(conditionLabel),
          condition_score: parseConditionScoreInput(),
          brand: normalizeOptionalText(brand),
          approx_dimensions_text: normalizeOptionalText(approxDimensionsText),
          intended_use: normalizeOptionalText(intendedUse),
          asking_price_cents: parsePriceInput(),
          currency_code: "USD",
          city_slug: citySlug,
        }),
      });
      setPublishedSlug(null);
      setStatus("Manual draft created.");
      await refreshDrafts(token, draft.id);
    });
  }

  function runAutofill(event: FormEvent) {
    event.preventDefault();
    void runBusyAction("autofill-draft", async () => {
      if (!token) {
        throw new Error("Authenticate before running AI autofill.");
      }
      if (!uploadFiles?.length) {
        throw new Error("Choose at least one product photo first.");
      }

      const formData = new FormData();
      formData.append("city_slug", citySlug);
      formData.append("currency_code", "USD");
      Array.from(uploadFiles).forEach((file) => formData.append("files", file));

      const draft = await readJson<Draft>(apiUrl("/draft-listings/ai-autofill"), {
        method: "POST",
        headers: tokenHeaders(token),
        body: formData,
      });
      setPublishedSlug(null);
      setStatus("AI autofill completed. Review every field before publishing.");
      await refreshDrafts(token, draft.id);
    });
  }

  function saveDraftEdits(event: FormEvent) {
    event.preventDefault();
    void runBusyAction("save-draft", async () => {
      if (!token) {
        throw new Error("Authenticate before saving draft edits.");
      }
      if (!activeDraft) {
        throw new Error("Select a draft first.");
      }

      const draft = await readJson<Draft>(apiUrl(`/draft-listings/${activeDraft.id}`), {
        method: "PATCH",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          title,
          product_name: productName,
          description,
          category_slug: categorySlug,
          condition: normalizeOptionalText(conditionLabel),
          condition_score: parseConditionScoreInput(),
          brand: normalizeOptionalText(brand),
          approx_dimensions_text: normalizeOptionalText(approxDimensionsText),
          intended_use: normalizeOptionalText(intendedUse),
          city_slug: citySlug,
          asking_price_cents: parsePriceInput(),
        }),
      });
      setPublishedSlug(null);
      setStatus("Draft updated.");
      await refreshDrafts(token, draft.id);
    });
  }

  function generateImage() {
    void runBusyAction("generate-image", async () => {
      if (!token) {
        throw new Error("Authenticate before generating a sale image.");
      }
      if (!activeDraft) {
        throw new Error("Select a draft first.");
      }

      const draft = await readJson<Draft>(apiUrl("/draft-listings/ai-image"), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          draft_id: activeDraft.id,
          style_preset: "clean studio",
          quality: "medium",
          size: "1024x1024",
          background: "auto",
        }),
      });
      setStatus("AI sale image generated and attached to the draft.");
      await refreshWallet();
      await refreshDrafts(token, draft.id);
    });
  }

  function publishDraft() {
    void runBusyAction("publish-draft", async () => {
      if (!token) {
        throw new Error("Authenticate before publishing a draft.");
      }
      if (!activeDraft) {
        throw new Error("Select a draft first.");
      }

      const listing = await readJson<{ slug: string }>(apiUrl(`/draft-listings/${activeDraft.id}/publish`), {
        method: "POST",
        headers: tokenHeaders(token),
      });
      setPublishedSlug(listing.slug);
      setStatus(`Listing published. Live slug: ${listing.slug}`);
      await refreshDrafts(token, activeDraft.id);
    });
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-8 px-6 py-10 lg:grid-cols-[1.1fr_0.9fr]">
      <section className="surface-card relative overflow-hidden rounded-[2.2rem] p-7">
        <div className="pointer-events-none absolute right-[-4rem] top-[-3rem] h-48 w-48 rounded-full bg-[rgba(255,216,77,0.38)] blur-3xl" />
        <div className="relative">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div>
              <p className="eyebrow text-[var(--color-sea)]">Seller Studio</p>
              <h1 className="display-title mt-3 text-5xl text-[var(--color-ink)]">Review every fact before the listing goes live.</h1>
              <p className="mt-4 max-w-2xl text-base leading-7 text-[rgba(18,38,63,0.74)]">
                Upload photos, let AI prefill the listing, then check product name, brand, condition score, size, and best use before publishing.
              </p>
            </div>

            <div className="sun-panel max-w-sm rounded-[1.7rem] p-5">
              <p className="eyebrow text-[rgba(18,38,63,0.68)]">Human-first pipeline</p>
              <p className="mt-3 text-sm leading-7 text-[rgba(18,38,63,0.74)]">
                OTP → draft → AI prefill → human review → optional sale image → publish. The product facts stay explicit instead of hiding in JSON.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="price-chip">Drafts: {drafts.length}</span>
                <span className="price-chip">Credits: {wallet?.balance_credits ?? 0}</span>
                <span className="price-chip">Images: {activeDraft?.images.length ?? 0}</span>
              </div>
            </div>
          </div>

          <div className="mt-8 grid gap-4 md:grid-cols-3">
            <div className="soft-panel rounded-[1.5rem] p-4">
              <span className="step-pill">01</span>
              <p className="mt-3 text-lg font-semibold">Authenticate seller</p>
              <p className="mt-2 text-sm leading-6 text-[rgba(18,38,63,0.7)]">Request a debug OTP and cache the bearer token for local testing.</p>
            </div>
            <div className="soft-panel rounded-[1.5rem] p-4">
              <span className="step-pill">02</span>
              <p className="mt-3 text-lg font-semibold">Build the draft</p>
              <p className="mt-2 text-sm leading-6 text-[rgba(18,38,63,0.7)]">Start manually or from photos, but always keep product facts editable in one visible form.</p>
            </div>
            <div className="soft-panel rounded-[1.5rem] p-4">
              <span className="step-pill">03</span>
              <p className="mt-3 text-lg font-semibold">Publish after review</p>
              <p className="mt-2 text-sm leading-6 text-[rgba(18,38,63,0.7)]">AI suggestions stay as a draft until a human verifies the listing and attached images.</p>
            </div>
          </div>

          <div className="sun-panel mt-6 rounded-[1.7rem] p-5">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="eyebrow text-[rgba(18,38,63,0.68)]">Seller status</p>
                <p className="mt-2 break-all text-sm text-[rgba(18,38,63,0.82)]">{token ? `Bearer ${token}` : "Not authenticated yet."}</p>
                <p className="mt-3 text-sm text-[rgba(18,38,63,0.76)]">{status}</p>
              </div>
              {publishedSlug ? (
                <a href={`/listings/${publishedSlug}`} className="link-chip">
                  Open live listing
                </a>
              ) : null}
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              <button className="button-secondary" type="button" onClick={topUpCredits} disabled={!token || !!busyAction}>
                {isBusy("top-up-credits") ? "Adding credits..." : "Top up 40 credits"}
              </button>
              <button
                className="button-secondary"
                type="button"
                disabled={!!busyAction}
                onClick={() => {
                  setToken("");
                  setWallet(null);
                  setDrafts([]);
                  applyDraft(null);
                  setDebugCode("");
                  setPublishedSlug(null);
                  window.localStorage.removeItem(TOKEN_KEY);
                  setStatus("Cleared local access token.");
                }}
              >
                Clear token
              </button>
            </div>
          </div>

          <div className="mt-8 grid gap-6 lg:grid-cols-2">
            <form onSubmit={requestOtp} className="soft-panel rounded-[1.8rem] p-5">
              <div className="flex items-center gap-3">
                <span className="step-pill">01</span>
                <div>
                  <p className="font-semibold">Request seller OTP</p>
                  <p className="text-sm text-[rgba(18,38,63,0.66)]">Local development shows the debug code inline.</p>
                </div>
              </div>
              <input className="field mt-4" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="seller@example.com" />
              <input className="field mt-3" value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="Display name" />
              <button className="button-primary mt-4 w-full" type="submit" disabled={!!busyAction}>
                {isBusy("request-otp") ? "Requesting..." : "Request debug OTP"}
              </button>
              {debugCode ? <p className="mt-3 text-sm text-[var(--color-coral)]">Debug OTP: {debugCode}</p> : null}
            </form>

            <form onSubmit={verifyOtp} className="soft-panel rounded-[1.8rem] p-5">
              <div className="flex items-center gap-3">
                <span className="step-pill">02</span>
                <div>
                  <p className="font-semibold">Verify and store access token</p>
                  <p className="text-sm text-[rgba(18,38,63,0.66)]">The token is cached in local storage for this browser session.</p>
                </div>
              </div>
              {cities.length ? (
                <select className="field mt-4" value={citySlug} onChange={(event) => setCitySlug(event.target.value)}>
                  {cities.map((city) => (
                    <option key={city.slug} value={city.slug}>
                      {city.display_name} ({city.country_code})
                    </option>
                  ))}
                </select>
              ) : (
                <input className="field mt-4" value={citySlug} onChange={(event) => setCitySlug(event.target.value)} placeholder="city slug" />
              )}
              <input className="field mt-3" value={otp} onChange={(event) => setOtp(event.target.value)} placeholder="6-digit OTP" />
              <button className="button-primary mt-4 w-full" type="submit" disabled={!!busyAction}>
                {isBusy("verify-otp") ? "Verifying..." : "Verify sign-in"}
              </button>
            </form>
          </div>

          <div className="mt-8 grid gap-6 lg:grid-cols-2">
            <form onSubmit={createManualDraft} className="soft-panel rounded-[1.8rem] p-5">
              <div className="flex items-center gap-3">
                <span className="step-pill">03</span>
                <div>
                  <p className="font-semibold">Start manually</p>
                  <p className="text-sm text-[rgba(18,38,63,0.66)]">Use this when you want explicit control over the initial listing facts.</p>
                </div>
              </div>
              <input className="field mt-4" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Marketplace title" />
              <input className="field mt-3" value={productName} onChange={(event) => setProductName(event.target.value)} placeholder="Actual product name" />
              <textarea className="field mt-3 min-h-28" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Description" />
              {categories.length ? (
                <select className="field mt-3" value={categorySlug} onChange={(event) => setCategorySlug(event.target.value)}>
                  {categories.map((category) => (
                    <option key={category.slug} value={category.slug}>
                      {category.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input className="field mt-3" value={categorySlug} onChange={(event) => setCategorySlug(event.target.value)} placeholder="category slug" />
              )}
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <input className="field" value={conditionLabel} onChange={(event) => setConditionLabel(event.target.value)} placeholder="Condition label" />
                <input className="field" value={conditionScore} onChange={(event) => setConditionScore(event.target.value)} placeholder="Condition score 1-10" />
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <input className="field" value={brand} onChange={(event) => setBrand(event.target.value)} placeholder="Brand" />
                <input className="field" value={askingPrice} onChange={(event) => setAskingPrice(event.target.value)} placeholder="Price cents" />
              </div>
              <input className="field mt-3" value={approxDimensionsText} onChange={(event) => setApproxDimensionsText(event.target.value)} placeholder="Approximate dimensions" />
              <input className="field mt-3" value={intendedUse} onChange={(event) => setIntendedUse(event.target.value)} placeholder="Best use / intended use" />
              <button className="button-primary mt-4 w-full" type="submit" disabled={!token || !!busyAction}>
                {isBusy("create-draft") ? "Creating..." : "Create draft"}
              </button>
            </form>

            <form onSubmit={runAutofill} className="soft-panel rounded-[1.8rem] p-5">
              <div className="flex items-center gap-3">
                <span className="step-pill">04</span>
                <div>
                  <p className="font-semibold">Auto-fill from photos</p>
                  <p className="text-sm text-[rgba(18,38,63,0.66)]">Upload one or more product photos and let the model draft the structured listing.</p>
                </div>
              </div>
              {cities.length ? (
                <select className="field mt-4" value={citySlug} onChange={(event) => setCitySlug(event.target.value)}>
                  {cities.map((city) => (
                    <option key={city.slug} value={city.slug}>
                      {city.display_name} ({city.country_code})
                    </option>
                  ))}
                </select>
              ) : (
                <input className="field mt-4" value={citySlug} onChange={(event) => setCitySlug(event.target.value)} placeholder="city slug" />
              )}
              <label className="mt-3 block rounded-[1rem] border border-dashed border-[rgba(18,38,63,0.2)] bg-white/82 px-4 py-6 text-sm text-[rgba(18,38,63,0.72)]">
                <span className="block">Upload one or more item photos</span>
                <input className="mt-3 block w-full text-sm" type="file" accept="image/*" multiple onChange={(event) => setUploadFiles(event.target.files)} />
              </label>
              <button className="button-primary mt-4 w-full" type="submit" disabled={!token || !!busyAction}>
                {isBusy("autofill-draft") ? "Running AI autofill..." : "Run AI autofill"}
              </button>
            </form>
          </div>
        </div>
      </section>

      <section className="surface-card rounded-[2.2rem] p-7">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="eyebrow text-[var(--color-coral)]">Draft Review</p>
            <h2 className="display-title mt-2 text-4xl">Refine, validate, publish.</h2>
          </div>
          <button
            className="button-secondary"
            type="button"
            onClick={() =>
              void runBusyAction("refresh-drafts", async () => {
                if (!token) {
                  throw new Error("Authenticate before refreshing drafts.");
                }
                await refreshDrafts(token, activeDraft?.id);
                await refreshWallet(token);
                setStatus("Drafts refreshed.");
              })
            }
            disabled={!token || !!busyAction}
          >
            {isBusy("refresh-drafts") ? "Refreshing..." : "Refresh drafts"}
          </button>
        </div>

        <div className="mt-6 flex flex-wrap gap-2">
          {drafts.map((draft) => (
            <button
              key={draft.id}
              type="button"
              className={`rounded-full px-4 py-2 text-sm font-semibold ${activeDraft?.id === draft.id ? "bg-[var(--color-ink)] text-white" : "bg-white/70 text-[var(--color-ink)]"}`}
              onClick={() => {
                setPublishedSlug(null);
                applyDraft(draft);
              }}
            >
              {draft.title ?? draft.product_name ?? "Untitled draft"}
            </button>
          ))}
        </div>

        {activeDraft ? (
          <form onSubmit={saveDraftEdits} className="mt-6 space-y-4">
            <input className="field" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Marketplace title" />
            <input className="field" value={productName} onChange={(event) => setProductName(event.target.value)} placeholder="Actual product name" />
            <textarea className="field min-h-32" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Description" />

            <div className="grid gap-3 md:grid-cols-2">
              {categories.length ? (
                <select className="field" value={categorySlug} onChange={(event) => setCategorySlug(event.target.value)}>
                  {categories.map((category) => (
                    <option key={category.slug} value={category.slug}>
                      {category.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input className="field" value={categorySlug} onChange={(event) => setCategorySlug(event.target.value)} placeholder="category slug" />
              )}
              {cities.length ? (
                <select className="field" value={citySlug} onChange={(event) => setCitySlug(event.target.value)}>
                  {cities.map((city) => (
                    <option key={city.slug} value={city.slug}>
                      {city.display_name} ({city.country_code})
                    </option>
                  ))}
                </select>
              ) : (
                <input className="field" value={citySlug} onChange={(event) => setCitySlug(event.target.value)} placeholder="city slug" />
              )}
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <input className="field" value={conditionLabel} onChange={(event) => setConditionLabel(event.target.value)} placeholder="Condition label" />
              <input className="field" value={conditionScore} onChange={(event) => setConditionScore(event.target.value)} placeholder="Condition score 1-10" />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <input className="field" value={brand} onChange={(event) => setBrand(event.target.value)} placeholder="Brand" />
              <input className="field" value={askingPrice} onChange={(event) => setAskingPrice(event.target.value)} placeholder="Price cents" />
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              <input className="field" value={approxDimensionsText} onChange={(event) => setApproxDimensionsText(event.target.value)} placeholder="Approximate dimensions" />
              <input className="field" value={intendedUse} onChange={(event) => setIntendedUse(event.target.value)} placeholder="Best use / intended use" />
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="soft-panel rounded-[1.4rem] p-4 text-sm">
                <p><strong>Status:</strong> {activeDraft.status}</p>
                <p className="mt-2"><strong>AI model:</strong> {activeDraft.ai_source_model ?? "manual"}</p>
                <p className="mt-2"><strong>Suggested price:</strong> {activeDraft.suggested_price_cents ?? "n/a"} cents</p>
                <p className="mt-2"><strong>Images attached:</strong> {activeDraft.images.length}</p>
              </div>
              <div className="sky-panel rounded-[1.4rem] p-4 text-sm">
                <p><strong>Missing fields:</strong> {activeDraft.ai_missing_fields.join(", ") || "none"}</p>
                <p className="mt-2"><strong>Safety flags:</strong> {activeDraft.ai_safety_flags.join(", ") || "none"}</p>
                <p className="mt-2"><strong>Product name:</strong> {activeDraft.product_name ?? "n/a"}</p>
              </div>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="sun-panel rounded-[1.4rem] p-4 text-sm">
                <p><strong>Condition label:</strong> {activeDraft.condition ?? "n/a"}</p>
                <p className="mt-2"><strong>Condition score:</strong> {activeDraft.condition_score ? `${activeDraft.condition_score}/10` : "n/a"}</p>
                <p className="mt-2"><strong>Brand:</strong> {activeDraft.brand ?? "n/a"}</p>
              </div>
              <div className="soft-panel rounded-[1.4rem] p-4 text-sm">
                <p><strong>Approx. size:</strong> {activeDraft.approx_dimensions_text ?? "n/a"}</p>
                <p className="mt-2"><strong>Best use:</strong> {activeDraft.intended_use ?? "n/a"}</p>
                <p className="mt-2"><strong>City:</strong> {activeDraft.city_slug ?? "n/a"}</p>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-3">
              <button className="button-secondary" type="submit" disabled={!!busyAction}>
                {isBusy("save-draft") ? "Saving..." : "Save review edits"}
              </button>
              <button className="button-secondary" type="button" onClick={generateImage} disabled={!!busyAction}>
                {isBusy("generate-image") ? "Generating image..." : "Generate sale image"}
              </button>
              <button className="button-primary" type="button" onClick={publishDraft} disabled={!!busyAction}>
                {isBusy("publish-draft") ? "Publishing..." : "Publish listing"}
              </button>
            </div>

            {activeDraft.images.length ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {activeDraft.images.map((image) => (
                  <div key={image.id} className="overflow-hidden rounded-[1.3rem] border border-[rgba(18,38,63,0.08)] bg-white">
                    <img src={image.public_url} alt={activeDraft.product_name ?? activeDraft.title ?? "Draft image"} className="h-52 w-full object-cover" />
                    <div className="px-4 py-3 text-sm">
                      <p className="font-semibold">{image.provenance === "ai_generated" ? "AI-generated sale image" : "Original upload"}</p>
                      <p className="mt-1 text-[rgba(18,38,63,0.68)]">{image.width ?? "?"} × {image.height ?? "?"}</p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-[1.5rem] border border-dashed border-[rgba(18,38,63,0.18)] p-8 text-sm text-[rgba(18,38,63,0.65)]">
                No images attached yet. Upload seller photos or run AI image generation before publishing.
              </div>
            )}
          </form>
        ) : (
          <div className="mt-10 rounded-[1.5rem] border border-dashed border-[rgba(18,38,63,0.2)] p-8 text-sm text-[rgba(18,38,63,0.65)]">
            No draft selected yet. Authenticate, then create a draft manually or from photos.
          </div>
        )}
      </section>
    </div>
  );
}
