"use client";

import { FormEvent, useEffect, useState } from "react";

import { apiUrl, formatPrice } from "@/lib/api";
import { Listing, Order } from "@/lib/types";

const TOKEN_KEY = "agent-marketplace-buyer-token";

async function readJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail ?? `Request failed with ${response.status}`);
  }
  return payload as T;
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected error. Please try again.";
}

export function CheckoutFlow({ listing }: { listing: Listing }) {
  const [token, setToken] = useState("");
  const [email, setEmail] = useState("buyer@example.com");
  const [code, setCode] = useState("");
  const [debugCode, setDebugCode] = useState("");
  const [order, setOrder] = useState<Order | null>(null);
  const [status, setStatus] = useState("Authenticate as a buyer, then start the mock checkout flow.");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [address, setAddress] = useState({
    full_name: "Taylor Buyer",
    line1: "24 Harbour Street",
    line2: "",
    city: "Sydney",
    state: "NSW",
    postal_code: "2000",
    country_code: "AU",
    phone: "",
  });

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
    const stored = window.localStorage.getItem(TOKEN_KEY);
    if (stored) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setToken(stored);
    }
  }, []);

  useEffect(() => {
    if (token) {
      window.localStorage.setItem(TOKEN_KEY, token);
    }
  }, [token]);

  function requestOtp(event: FormEvent) {
    event.preventDefault();
    void runBusyAction("request-otp", async () => {
      const response = await readJson<{ debug_code?: string | null }>(apiUrl("/auth/email/request-code"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      setDebugCode(response.debug_code ?? "");
      setStatus("Buyer OTP requested.");
    });
  }

  function verifyOtp(event: FormEvent) {
    event.preventDefault();
    void runBusyAction("verify-otp", async () => {
      const response = await readJson<{ access_token: string }>(apiUrl("/auth/email/verify"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          code,
          display_name: "Buyer Agent",
          city_slug: listing.city_slug,
          country_code: "AU",
        }),
      });
      setToken(response.access_token);
      setStatus("Buyer authenticated.");
    });
  }

  function createOrder() {
    void runBusyAction("create-order", async () => {
      if (!token) {
        throw new Error("Authenticate before creating an order.");
      }
      const nextOrder = await readJson<Order>(apiUrl("/orders"), {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ listing_id: listing.id }),
      });
      setOrder(nextOrder);
      setStatus("Order created. Submit shipping address next.");
    });
  }

  function submitAddress() {
    void runBusyAction("submit-address", async () => {
      if (!token) {
        throw new Error("Authenticate before submitting an address.");
      }
      if (!order) {
        throw new Error("Create an order first.");
      }

      const nextOrder = await readJson<Order>(apiUrl(`/orders/${order.id}/address`), {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ address }),
      });
      setOrder(nextOrder);
      setStatus("Shipping address saved. Ready for mock payment.");
    });
  }

  function mockPay() {
    void runBusyAction("mock-pay", async () => {
      if (!token) {
        throw new Error("Authenticate before confirming payment.");
      }
      if (!order) {
        throw new Error("Create an order first.");
      }

      const result = await readJson<{ status: string }>(apiUrl(`/orders/${order.id}/mock-pay`), {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      setStatus(`Mock checkout complete. Order status: ${result.status}.`);
      const refreshed = await readJson<Order>(apiUrl(`/orders/${order.id}`), {
        headers: { Authorization: `Bearer ${token}` },
      });
      setOrder(refreshed);
    });
  }

  const stageLabels = [
    { label: "Identity", complete: Boolean(token) },
    { label: "Order", complete: Boolean(order) },
    { label: "Address", complete: Boolean(order?.address_payload) },
    { label: "Paid", complete: order?.status === "paid" },
  ];

  return (
    <div className="surface-card rounded-[2.2rem] p-7">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow text-[var(--color-coral)]">Mock Checkout</p>
          <h2 className="display-title mt-2 text-4xl">Buy now without hiding the future agent path.</h2>
          <p className="mt-3 text-sm leading-7 text-[rgba(18,38,63,0.72)]">
            This remains a mock payment flow, but the buyer identity, order lifecycle, and state transitions already mirror the agent-facing APIs.
          </p>
        </div>
        <span className="price-chip">{order?.status ?? "awaiting buyer"}</span>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-4">
        {stageLabels.map((stage, index) => (
          <div
            key={stage.label}
            className={`${stage.complete ? "sun-panel" : "soft-panel"} rounded-[1.3rem] p-4`}
          >
            <span className="step-pill">{String(index + 1).padStart(2, "0")}</span>
            <p className="mt-3 font-semibold">{stage.label}</p>
            <p className="mt-1 text-sm text-[rgba(18,38,63,0.68)]">{stage.complete ? "Ready" : "Pending"}</p>
          </div>
        ))}
      </div>

      <div className="sun-panel mt-6 rounded-[1.7rem] p-5">
        <p className="font-semibold text-[var(--color-ink)]">{listing.title}</p>
        <p className="mt-2 text-sm leading-7 text-[rgba(18,38,63,0.72)]">{listing.description}</p>
        <div className="mt-4 flex flex-wrap gap-3">
          <span className="price-chip">{formatPrice(listing.asking_price_cents, listing.currency_code)}</span>
          <span className="price-chip">{listing.city_slug}</span>
          <span className="price-chip">{listing.condition ?? "Used item"}</span>
        </div>
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-2">
        <form onSubmit={requestOtp} className="soft-panel rounded-[1.6rem] p-5">
          <div className="flex items-center gap-3">
            <span className="step-pill">01</span>
            <div>
              <p className="font-semibold">Request buyer OTP</p>
              <p className="text-sm text-[rgba(18,38,63,0.66)]">Local testing shows the debug code inline.</p>
            </div>
          </div>
          <input className="field mt-4" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="buyer@example.com" />
          <button className="button-primary mt-4 w-full" type="submit" disabled={!!busyAction}>
            {isBusy("request-otp") ? "Requesting..." : "Request OTP"}
          </button>
          {debugCode ? <p className="mt-3 text-sm text-[var(--color-coral)]">Debug OTP: {debugCode}</p> : null}
        </form>

        <form onSubmit={verifyOtp} className="soft-panel rounded-[1.6rem] p-5">
          <div className="flex items-center gap-3">
            <span className="step-pill">02</span>
            <div>
              <p className="font-semibold">Verify buyer token</p>
              <p className="text-sm text-[rgba(18,38,63,0.66)]">The buyer token is stored locally for repeated demo runs.</p>
            </div>
          </div>
          <input className="field mt-4" value={code} onChange={(event) => setCode(event.target.value)} placeholder="6-digit OTP" />
          <button className="button-primary mt-4 w-full" type="submit" disabled={!!busyAction}>
            {isBusy("verify-otp") ? "Verifying..." : "Verify"}
          </button>
        </form>
      </div>

      <div className="sky-panel mt-6 rounded-[1.7rem] p-5 text-sm">
        <p className="break-all text-[rgba(18,38,63,0.8)]">{token ? `Bearer ${token}` : "No buyer token yet."}</p>
        <p className="mt-2 text-[rgba(18,38,63,0.72)]">{status}</p>
        <button
          className="button-secondary mt-4"
          type="button"
          disabled={!!busyAction}
          onClick={() => {
            setToken("");
            setOrder(null);
            setDebugCode("");
            window.localStorage.removeItem(TOKEN_KEY);
            setStatus("Cleared local buyer token.");
          }}
        >
          Clear buyer token
        </button>
      </div>

      <div className="mt-6 grid gap-4">
        <button className="button-secondary" type="button" onClick={createOrder} disabled={!token || !!busyAction}>
          {isBusy("create-order") ? "Creating order..." : "3. Create order"}
        </button>
        <div className="grid gap-3 md:grid-cols-2">
          <input className="field" value={address.full_name} onChange={(event) => setAddress({ ...address, full_name: event.target.value })} placeholder="Full name" />
          <input className="field" value={address.line1} onChange={(event) => setAddress({ ...address, line1: event.target.value })} placeholder="Address line 1" />
          <input className="field" value={address.city} onChange={(event) => setAddress({ ...address, city: event.target.value })} placeholder="City" />
          <input className="field" value={address.postal_code} onChange={(event) => setAddress({ ...address, postal_code: event.target.value })} placeholder="Postal code" />
        </div>
        <button className="button-secondary" type="button" onClick={submitAddress} disabled={!order || !!busyAction}>
          {isBusy("submit-address") ? "Saving address..." : "4. Submit shipping address"}
        </button>
        <button className="button-primary" type="button" onClick={mockPay} disabled={!order || !!busyAction}>
          {isBusy("mock-pay") ? "Confirming payment..." : "5. Confirm mock payment"}
        </button>
      </div>

      {order ? (
        <div className="soft-panel mt-6 rounded-[1.5rem] p-5 text-sm">
          <p><strong>Order ID:</strong> {order.id}</p>
          <p className="mt-2"><strong>Status:</strong> {order.status}</p>
          <p className="mt-2"><strong>Buyer ID:</strong> {order.buyer_id}</p>
          <p className="mt-2"><strong>Seller ID:</strong> {order.seller_id}</p>
        </div>
      ) : null}
    </div>
  );
}
