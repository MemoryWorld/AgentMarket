"use client";

import { FormEvent, useEffect, useEffectEvent, useState } from "react";

import { apiUrl, formatPrice } from "@/lib/api";
import {
  ActionReceipt,
  AgentGrant,
  AgentGrantCreateResponse,
  ApprovalDecision,
  ApprovalRequest,
  Draft,
  ListingSummary,
  MessageThread,
  Offer,
  Order,
  SearchResponse,
  ThreadDetail,
  User,
  Wallet,
} from "@/lib/types";

const TOKEN_KEY = "agent-marketplace-access-token";
const DEFAULT_GRANT_SCOPES = [
  "listings:write",
  "orders:write",
  "messages:read",
  "messages:write",
  "offers:read",
  "offers:write",
  "approvals:read",
  "approvals:write",
  "receipts:read",
];

async function readJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    ...init,
    cache: "no-store",
  });
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

function createIdempotencyKey(prefix: string): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}`;
}

function formatTime(value?: string | null): string {
  if (!value) return "n/a";
  return new Intl.DateTimeFormat("en-AU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function compactToken(value: string): string {
  if (!value) return "Not connected.";
  if (value.length <= 32) return value;
  return `${value.slice(0, 18)}…${value.slice(-10)}`;
}

function readStoredToken(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(TOKEN_KEY) ?? "";
}

function statusBadge(status: string): string {
  if (status === "pending") return "bg-[rgba(255,216,77,0.42)]";
  if (status === "approved" || status === "executed" || status === "sent" || status === "accepted" || status === "succeeded") {
    return "bg-[rgba(11,150,255,0.16)]";
  }
  if (status === "rejected" || status === "failed" || status === "revoked" || status === "cancelled") {
    return "bg-[rgba(255,144,34,0.2)]";
  }
  return "bg-white/70";
}

export function ControlRoom() {
  const [token, setToken] = useState(readStoredToken);
  const [tokenInput, setTokenInput] = useState(readStoredToken);
  const [status, setStatus] = useState("Load your seller access token to manage agent approvals.");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [me, setMe] = useState<User | null>(null);
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [grants, setGrants] = useState<AgentGrant[]>([]);
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([]);
  const [receipts, setReceipts] = useState<ActionReceipt[]>([]);
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [liveListings, setLiveListings] = useState<ListingSummary[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [threads, setThreads] = useState<MessageThread[]>([]);
  const [activeThreadId, setActiveThreadId] = useState("");
  const [activeThread, setActiveThread] = useState<ThreadDetail | null>(null);
  const [latestGrantToken, setLatestGrantToken] = useState("");
  const [grantName, setGrantName] = useState("Codex Seller Operator");
  const [agentFamily, setAgentFamily] = useState("codex");
  const [selectedDraftId, setSelectedDraftId] = useState("");
  const [repricingListingId, setRepricingListingId] = useState("");
  const [repricingPrice, setRepricingPrice] = useState("");
  const [selectedOrderId, setSelectedOrderId] = useState("");
  const [fulfillmentStatus, setFulfillmentStatus] = useState("shipped");
  const [fulfillmentCarrier, setFulfillmentCarrier] = useState("");
  const [fulfillmentTracking, setFulfillmentTracking] = useState("");
  const [newThreadListingId, setNewThreadListingId] = useState("");
  const [participantUserId, setParticipantUserId] = useState("");
  const [threadSubject, setThreadSubject] = useState("");
  const [messageBody, setMessageBody] = useState("");
  const [offerAmount, setOfferAmount] = useState("");
  const [offerNote, setOfferNote] = useState("");
  const [counterAmounts, setCounterAmounts] = useState<Record<string, string>>({});
  const [counterNotes, setCounterNotes] = useState<Record<string, string>>({});

  function resetWorkspace() {
    setMe(null);
    setWallet(null);
    setGrants([]);
    setApprovals([]);
    setReceipts([]);
    setDrafts([]);
    setLiveListings([]);
    setOrders([]);
    setThreads([]);
    setActiveThreadId("");
    setActiveThread(null);
  }

  function getListingTitle(listingId: string): string {
    return liveListings.find((listing) => listing.id === listingId)?.title ?? `Listing ${listingId.slice(0, 8)}`;
  }

  function syncSelection<T extends { id: string }>(items: T[], current: string): string {
    if (current && items.some((item) => item.id === current)) {
      return current;
    }
    return items[0]?.id ?? "";
  }

  async function refreshThreadDetail(accessToken = token, threadId = activeThreadId) {
    if (!accessToken || !threadId) {
      setActiveThread(null);
      return;
    }
    const detail = await readJson<ThreadDetail>(apiUrl(`/threads/${threadId}`), {
      headers: tokenHeaders(accessToken),
    });
    setActiveThread(detail);
    setActiveThreadId(detail.id);
  }

  async function refreshWorkspace(accessToken = token, preferredThreadId?: string) {
    if (!accessToken) {
      return;
    }

    const headers = tokenHeaders(accessToken);
    const nextMe = await readJson<User>(apiUrl("/auth/me"), { headers });
    const [
      nextWallet,
      nextGrants,
      nextApprovals,
      nextReceipts,
      nextDrafts,
      nextOrders,
      nextThreads,
      listingSearch,
    ] = await Promise.all([
      readJson<Wallet>(apiUrl("/wallet"), { headers }),
      readJson<AgentGrant[]>(apiUrl("/agent-grants"), { headers }),
      readJson<ApprovalRequest[]>(apiUrl("/approval-requests"), { headers }),
      readJson<ActionReceipt[]>(apiUrl("/action-receipts"), { headers }),
      readJson<Draft[]>(apiUrl("/draft-listings"), { headers }),
      readJson<Order[]>(apiUrl("/orders?role=seller"), { headers }),
      readJson<MessageThread[]>(apiUrl("/threads"), { headers }),
      readJson<SearchResponse>(apiUrl(`/listings?seller_id=${nextMe.id}&limit=24`)),
    ]);

    setMe(nextMe);
    setWallet(nextWallet);
    setGrants(nextGrants);
    setApprovals(nextApprovals);
    setReceipts(nextReceipts);
    setDrafts(nextDrafts);
    setOrders(nextOrders);
    setThreads(nextThreads);
    setLiveListings(listingSearch.items);

    const nextDraftId = syncSelection(nextDrafts, selectedDraftId);
    const nextListingId = syncSelection(listingSearch.items, repricingListingId);
    const nextOrderId = syncSelection(nextOrders, selectedOrderId);

    setSelectedDraftId(nextDraftId);
    setRepricingListingId(nextListingId);
    setNewThreadListingId((current) => {
      if (current && listingSearch.items.some((listing) => listing.id === current)) {
        return current;
      }
      return listingSearch.items[0]?.id ?? "";
    });
    setRepricingPrice((current) => {
      if (current) return current;
      const selected = listingSearch.items.find((listing) => listing.id === nextListingId);
      return selected ? String(selected.asking_price_cents) : "";
    });
    setSelectedOrderId(nextOrderId);

    const nextThreadId = preferredThreadId && nextThreads.some((thread) => thread.id === preferredThreadId)
      ? preferredThreadId
      : syncSelection(nextThreads, activeThreadId);

    if (nextThreadId) {
      await refreshThreadDetail(accessToken, nextThreadId);
    } else {
      setActiveThreadId("");
      setActiveThread(null);
    }
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

  const syncWorkspace = useEffectEvent(async (accessToken: string) => {
    try {
      await refreshWorkspace(accessToken);
      setStatus("Seller control room synced.");
    } catch (error) {
      setStatus(getErrorMessage(error));
    }
  });

  useEffect(() => {
    if (!token) {
      window.localStorage.removeItem(TOKEN_KEY);
      return;
    }

    window.localStorage.setItem(TOKEN_KEY, token);

    queueMicrotask(() => {
      void syncWorkspace(token);
    });
  }, [token]);

  function connectToken(event: FormEvent) {
    event.preventDefault();
    const nextToken = tokenInput.trim();
    if (!nextToken) {
      setStatus("Paste a seller bearer token first.");
      return;
    }
    setLatestGrantToken("");
    setToken(nextToken);
    setStatus("Connecting token...");
  }

  function clearToken() {
    setToken("");
    setTokenInput("");
    setLatestGrantToken("");
    resetWorkspace();
    setStatus("Cleared local token and workspace state.");
  }

  function createGrant(event: FormEvent) {
    event.preventDefault();
    void runBusyAction("create-grant", async () => {
      if (!token) {
        throw new Error("Connect a seller token before creating an agent grant.");
      }
      const grant = await readJson<AgentGrantCreateResponse>(apiUrl("/agent-grants"), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: grantName,
          agent_family: agentFamily,
          scopes: DEFAULT_GRANT_SCOPES,
          approval_mode: "prepare_then_confirm",
        }),
      });
      setLatestGrantToken(grant.token);
      await refreshWorkspace(token);
      setStatus(`Created ${grant.agent_family} grant. Save the PAT now; it is only shown once.`);
    });
  }

  function revokeGrant(grantId: string) {
    void runBusyAction(`revoke-${grantId}`, async () => {
      if (!token) {
        throw new Error("Connect a seller token before revoking an agent grant.");
      }
      await readJson<AgentGrant>(apiUrl(`/agent-grants/${grantId}/revoke`), {
        method: "POST",
        headers: tokenHeaders(token),
      });
      await refreshWorkspace(token);
      setStatus("Agent grant revoked.");
    });
  }

  function preparePublish() {
    void runBusyAction("prepare-publish", async () => {
      if (!token || !selectedDraftId) {
        throw new Error("Choose a reviewed draft first.");
      }
      await readJson<ApprovalRequest>(apiUrl("/approval-requests"), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          action_type: "publish_listing",
          draft_id: selectedDraftId,
          idempotency_key: createIdempotencyKey("publish"),
        }),
      });
      await refreshWorkspace(token);
      setStatus("Prepared publish request for seller approval.");
    });
  }

  function prepareReprice() {
    void runBusyAction("prepare-reprice", async () => {
      if (!token || !repricingListingId) {
        throw new Error("Choose a live listing first.");
      }
      const nextPrice = Number.parseInt(repricingPrice, 10);
      if (Number.isNaN(nextPrice) || nextPrice < 0) {
        throw new Error("Enter a valid price in cents.");
      }
      await readJson<ApprovalRequest>(apiUrl("/approval-requests"), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          action_type: "reprice_listing",
          listing_id: repricingListingId,
          new_price_cents: nextPrice,
          idempotency_key: createIdempotencyKey("reprice"),
        }),
      });
      await refreshWorkspace(token);
      setStatus("Prepared repricing request for seller approval.");
    });
  }

  function prepareCancelOrder() {
    void runBusyAction("prepare-cancel-order", async () => {
      if (!token || !selectedOrderId) {
        throw new Error("Choose an order first.");
      }
      await readJson<ApprovalRequest>(apiUrl("/approval-requests"), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          action_type: "cancel_order",
          order_id: selectedOrderId,
          idempotency_key: createIdempotencyKey("cancel-order"),
        }),
      });
      await refreshWorkspace(token);
      setStatus("Prepared cancellation request for seller approval.");
    });
  }

  function prepareFulfillment() {
    void runBusyAction("prepare-fulfillment", async () => {
      if (!token || !selectedOrderId) {
        throw new Error("Choose an order first.");
      }
      await readJson<ApprovalRequest>(apiUrl("/approval-requests"), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          action_type: "update_fulfillment",
          order_id: selectedOrderId,
          status: fulfillmentStatus,
          carrier: fulfillmentCarrier || null,
          tracking_number: fulfillmentTracking || null,
          idempotency_key: createIdempotencyKey("fulfillment"),
        }),
      });
      await refreshWorkspace(token);
      setStatus("Prepared fulfillment update for seller approval.");
    });
  }

  function createThread(event: FormEvent) {
    event.preventDefault();
    void runBusyAction("create-thread", async () => {
      if (!token || !newThreadListingId) {
        throw new Error("Choose a listing before creating a thread.");
      }
      const thread = await readJson<MessageThread>(apiUrl("/threads"), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          listing_id: newThreadListingId,
          participant_user_id: participantUserId.trim() || null,
          subject: threadSubject.trim() || null,
        }),
      });
      setParticipantUserId("");
      setThreadSubject("");
      await refreshWorkspace(token, thread.id);
      setStatus("Thread ready for seller-agent collaboration.");
    });
  }

  function sendMessageDraft(event: FormEvent) {
    event.preventDefault();
    void runBusyAction("send-message-draft", async () => {
      if (!token || !activeThreadId) {
        throw new Error("Choose a thread before drafting a message.");
      }
      if (!messageBody.trim()) {
        throw new Error("Write the message body first.");
      }
      await readJson(apiUrl(`/threads/${activeThreadId}/messages`), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          body: messageBody.trim(),
          idempotency_key: createIdempotencyKey("message"),
        }),
      });
      setMessageBody("");
      await refreshWorkspace(token, activeThreadId);
      setStatus("Message draft queued for seller approval.");
    });
  }

  function createOffer(event: FormEvent) {
    event.preventDefault();
    void runBusyAction("create-offer", async () => {
      if (!token || !activeThreadId) {
        throw new Error("Choose a thread before creating an offer.");
      }
      const amount = Number.parseInt(offerAmount, 10);
      if (Number.isNaN(amount) || amount <= 0) {
        throw new Error("Enter a valid offer amount in cents.");
      }
      await readJson<Offer>(apiUrl("/offers"), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          thread_id: activeThreadId,
          amount_cents: amount,
          note: offerNote.trim() || null,
          idempotency_key: createIdempotencyKey("offer"),
        }),
      });
      setOfferAmount("");
      setOfferNote("");
      await refreshWorkspace(token, activeThreadId);
      setStatus("Offer draft queued for approval.");
    });
  }

  function decideOffer(offerId: string, action: "accept" | "reject") {
    void runBusyAction(`${action}-offer-${offerId}`, async () => {
      if (!token) {
        throw new Error("Connect a token before preparing an offer decision.");
      }
      await readJson<Offer>(apiUrl(`/offers/${offerId}/${action}`), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          idempotency_key: createIdempotencyKey(`${action}-offer`),
        }),
      });
      await refreshWorkspace(token, activeThreadId);
      setStatus(`Offer ${action} request queued for approval.`);
    });
  }

  function counterOffer(offerId: string) {
    void runBusyAction(`counter-offer-${offerId}`, async () => {
      if (!token) {
        throw new Error("Connect a token before countering an offer.");
      }
      const amount = Number.parseInt(counterAmounts[offerId] ?? "", 10);
      if (Number.isNaN(amount) || amount <= 0) {
        throw new Error("Enter a valid counter amount in cents.");
      }
      await readJson<Offer>(apiUrl(`/offers/${offerId}/counter`), {
        method: "POST",
        headers: {
          ...tokenHeaders(token),
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          amount_cents: amount,
          note: (counterNotes[offerId] ?? "").trim() || null,
          idempotency_key: createIdempotencyKey("counter-offer"),
        }),
      });
      setCounterAmounts((current) => ({ ...current, [offerId]: "" }));
      setCounterNotes((current) => ({ ...current, [offerId]: "" }));
      await refreshWorkspace(token, activeThreadId);
      setStatus("Counter-offer queued for approval.");
    });
  }

  function decideApproval(approvalId: string, action: "approve" | "reject") {
    void runBusyAction(`${action}-approval-${approvalId}`, async () => {
      if (!token) {
        throw new Error("Connect a seller token before deciding approvals.");
      }
      let decision: ApprovalDecision;
      try {
        decision = await readJson<ApprovalDecision>(apiUrl(`/approval-requests/${approvalId}/${action}`), {
          method: "POST",
          headers: tokenHeaders(token),
        });
      } catch (error) {
        // Failed execution can still create a receipt and change approval state.
        // Preserve the action error if refreshing the workspace also fails.
        await refreshWorkspace(token, activeThreadId).catch(() => undefined);
        throw error;
      }
      await refreshWorkspace(token, activeThreadId);
      setStatus(
        action === "approve"
          ? `Approval executed with receipt ${decision.receipt?.status ?? "n/a"}.`
          : `Approval rejected with receipt ${decision.receipt?.status ?? "n/a"}.`,
      );
    });
  }

  const pendingApprovals = approvals.filter((approval) => approval.status === "pending");
  const recentReceipts = receipts.slice(0, 8);

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10">
      <section className="surface-card relative overflow-hidden rounded-[2.4rem] p-7 md:p-8">
        <div className="pointer-events-none absolute right-[-4rem] top-[-4rem] h-48 w-48 rounded-full bg-[rgba(255,216,77,0.38)] blur-3xl" />
        <div className="relative">
          <div className="flex flex-wrap items-start justify-between gap-5">
            <div className="max-w-3xl">
              <p className="eyebrow text-[var(--color-sea)]">Seller Control Room</p>
              <h1 className="display-title mt-3 text-5xl text-[var(--color-ink)] md:text-6xl">Prepare with agents. Confirm as the seller. Track each result.</h1>
              <p className="mt-4 text-base leading-8 text-[rgba(18,38,63,0.76)]">
                Review publishing, price, message, offer, and fulfillment changes proposed by your agents.
                Sign in as the seller to approve or reject each request and inspect its execution receipt.
              </p>
            </div>
            <div className="sun-panel max-w-md rounded-[1.8rem] p-5">
              <p className="eyebrow text-[rgba(18,38,63,0.7)]">Workspace status</p>
              <p className="mt-3 break-all text-sm leading-7 text-[rgba(18,38,63,0.82)]">{compactToken(token)}</p>
              <p className="mt-3 text-sm text-[rgba(18,38,63,0.76)]">{status}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <span className="price-chip">Pending approvals: {pendingApprovals.length}</span>
                <span className="price-chip">Threads: {threads.length}</span>
                <span className="price-chip">Credits: {wallet?.balance_credits ?? 0}</span>
              </div>
            </div>
          </div>

          <div className="mt-8 grid gap-6 lg:grid-cols-[0.92fr_1.08fr]">
            <form onSubmit={connectToken} className="soft-panel rounded-[1.8rem] p-5">
              <div className="flex items-center gap-3">
                <span className="step-pill">01</span>
                <div>
                  <p className="font-semibold">Load seller token</p>
                  <p className="text-sm text-[rgba(18,38,63,0.66)]">Use your seller sign-in token from the Sell page. Personal access tokens cannot approve requests or issue agent credentials.</p>
                </div>
              </div>
              <textarea
                className="field mt-4 min-h-28"
                value={tokenInput}
                onChange={(event) => setTokenInput(event.target.value)}
                placeholder="Paste seller sign-in token"
              />
              <div className="mt-4 flex flex-wrap gap-3">
                <button className="button-primary" type="submit" disabled={!!busyAction}>
                  Connect token
                </button>
                <button className="button-secondary" type="button" onClick={clearToken} disabled={!!busyAction}>
                  Clear token
                </button>
                <button
                  className="button-secondary"
                  type="button"
                  disabled={!token || !!busyAction}
                  onClick={() =>
                    void runBusyAction("refresh-workspace", async () => {
                      await refreshWorkspace(token, activeThreadId);
                      setStatus("Control room refreshed.");
                    })
                  }
                >
                  {isBusy("refresh-workspace") ? "Refreshing..." : "Refresh"}
                </button>
              </div>
            </form>

            <div className="sky-panel rounded-[1.8rem] p-5">
              <p className="eyebrow text-[var(--color-sea)]">Seller identity</p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <div className="rounded-[1.4rem] bg-white/76 p-4">
                  <p className="text-sm text-[rgba(18,38,63,0.6)]">Seller</p>
                  <p className="mt-2 text-lg font-semibold">{me?.display_name ?? "Not connected"}</p>
                  <p className="mt-1 break-all text-sm text-[rgba(18,38,63,0.68)]">{me?.email ?? "No token loaded"}</p>
                </div>
                <div className="rounded-[1.4rem] bg-white/76 p-4">
                  <p className="text-sm text-[rgba(18,38,63,0.6)]">Inventory</p>
                  <p className="mt-2 text-lg font-semibold">{liveListings.length} live listings</p>
                  <p className="mt-1 text-sm text-[rgba(18,38,63,0.68)]">{orders.length} seller orders • {drafts.length} drafts</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="mt-8 grid gap-8 xl:grid-cols-[0.98fr_1.02fr]">
        <div className="space-y-8">
          <div className="surface-card rounded-[2rem] p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="eyebrow text-[var(--color-coral)]">Approval Inbox</p>
                <h2 className="display-title mt-2 text-4xl">Seller-visible action queue.</h2>
              </div>
              <div className="soft-panel rounded-[1.3rem] px-4 py-3 text-sm font-semibold">
                {pendingApprovals.length} pending
              </div>
            </div>

            <div className="mt-5 space-y-4">
              {approvals.length ? approvals.map((approval) => (
                <article key={approval.id} className="soft-panel rounded-[1.6rem] p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap gap-2">
                        <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${statusBadge(approval.status)}`}>
                          {approval.status}
                        </span>
                        <span className="rounded-full bg-white/72 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]">
                          {approval.action_type}
                        </span>
                      </div>
                      <p className="mt-3 text-lg font-semibold">{approval.summary}</p>
                      <p className="mt-2 text-sm text-[rgba(18,38,63,0.68)]">
                        {approval.resource_type} • {approval.resource_id ?? "n/a"} • created {formatTime(approval.created_at)}
                      </p>
                    </div>
                    {approval.status === "pending" ? (
                      <div className="flex gap-2">
                        <button
                          className="button-primary"
                          type="button"
                          onClick={() => decideApproval(approval.id, "approve")}
                          disabled={!!busyAction}
                        >
                          {isBusy(`approve-approval-${approval.id}`) ? "Approving..." : "Approve"}
                        </button>
                        <button
                          className="button-secondary"
                          type="button"
                          onClick={() => decideApproval(approval.id, "reject")}
                          disabled={!!busyAction}
                        >
                          {isBusy(`reject-approval-${approval.id}`) ? "Rejecting..." : "Reject"}
                        </button>
                      </div>
                    ) : null}
                  </div>
                  <pre className="mt-4 overflow-x-auto rounded-[1.2rem] bg-[rgba(18,38,63,0.04)] p-4 text-xs leading-6 text-[rgba(18,38,63,0.8)]">
                    {formatJson(approval.diff_payload)}
                  </pre>
                </article>
              )) : (
                <div className="rounded-[1.6rem] border border-dashed border-[rgba(18,38,63,0.16)] p-8 text-sm text-[rgba(18,38,63,0.66)]">
                  No approvals yet. Let an agent prepare a message, offer, publish, repricing, or fulfillment action first.
                </div>
              )}
            </div>
          </div>

          <div className="surface-card rounded-[2rem] p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="eyebrow text-[var(--color-sea)]">Threads</p>
                <h2 className="display-title mt-2 text-4xl">Buyer conversations and offers.</h2>
              </div>
              <div className="soft-panel rounded-[1.3rem] px-4 py-3 text-sm font-semibold">
                {threads.length} active threads
              </div>
            </div>

            <form onSubmit={createThread} className="sun-panel mt-5 rounded-[1.7rem] p-5">
              <p className="font-semibold">Create a seller thread</p>
              <p className="mt-2 text-sm leading-6 text-[rgba(18,38,63,0.72)]">
                This is optional. In real flow, buyers often create the thread first. If the seller starts it, provide the buyer user id explicitly.
              </p>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <select className="field" value={newThreadListingId} onChange={(event) => setNewThreadListingId(event.target.value)}>
                  <option value="">Choose listing</option>
                  {liveListings.map((listing) => (
                    <option key={listing.id} value={listing.id}>
                      {listing.title}
                    </option>
                  ))}
                </select>
                <input
                  className="field"
                  value={participantUserId}
                  onChange={(event) => setParticipantUserId(event.target.value)}
                  placeholder="Buyer user id"
                />
              </div>
              <input className="field mt-3" value={threadSubject} onChange={(event) => setThreadSubject(event.target.value)} placeholder="Subject" />
              <button className="button-primary mt-4" type="submit" disabled={!token || !!busyAction}>
                {isBusy("create-thread") ? "Creating..." : "Create thread"}
              </button>
            </form>

            <div className="mt-5 flex flex-wrap gap-2">
              {threads.map((thread) => (
                <button
                  key={thread.id}
                  type="button"
                  className={`rounded-full px-4 py-2 text-sm font-semibold ${activeThreadId === thread.id ? "bg-[var(--color-ink)] text-white" : "bg-white/80 text-[var(--color-ink)]"}`}
                  onClick={() =>
                    void runBusyAction(`open-thread-${thread.id}`, async () => {
                      await refreshThreadDetail(token, thread.id);
                      setStatus(`Opened thread ${thread.id.slice(0, 8)}.`);
                    })
                  }
                >
                  {thread.subject ?? getListingTitle(thread.listing_id)}
                </button>
              ))}
            </div>

            {activeThread ? (
              <div className="mt-6 space-y-5">
                <div className="sky-panel rounded-[1.6rem] p-5">
                  <div className="flex flex-wrap items-start justify-between gap-4">
                    <div>
                      <p className="text-xl font-semibold">{activeThread.subject ?? getListingTitle(activeThread.listing_id)}</p>
                      <p className="mt-2 text-sm leading-6 text-[rgba(18,38,63,0.7)]">
                        Listing: {getListingTitle(activeThread.listing_id)} • Buyer: {activeThread.buyer_id} • Seller: {activeThread.seller_id}
                      </p>
                    </div>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${statusBadge(activeThread.status)}`}>
                      {activeThread.status}
                    </span>
                  </div>
                </div>

                <div className="grid gap-5 lg:grid-cols-2">
                  <form onSubmit={sendMessageDraft} className="soft-panel rounded-[1.6rem] p-5">
                    <p className="font-semibold">Draft outbound message</p>
                    <textarea
                      className="field mt-4 min-h-32"
                      value={messageBody}
                      onChange={(event) => setMessageBody(event.target.value)}
                      placeholder="Write the seller response that should go into approval."
                    />
                    <button className="button-primary mt-4" type="submit" disabled={!token || !!busyAction}>
                      {isBusy("send-message-draft") ? "Queueing..." : "Queue message approval"}
                    </button>
                  </form>

                  <form onSubmit={createOffer} className="soft-panel rounded-[1.6rem] p-5">
                    <p className="font-semibold">Draft seller offer</p>
                    <input
                      className="field mt-4"
                      value={offerAmount}
                      onChange={(event) => setOfferAmount(event.target.value)}
                      placeholder="Amount cents"
                    />
                    <textarea
                      className="field mt-3 min-h-24"
                      value={offerNote}
                      onChange={(event) => setOfferNote(event.target.value)}
                      placeholder="Optional note"
                    />
                    <button className="button-primary mt-4" type="submit" disabled={!token || !!busyAction}>
                      {isBusy("create-offer") ? "Queueing..." : "Queue offer approval"}
                    </button>
                  </form>
                </div>

                <div className="grid gap-5 lg:grid-cols-2">
                  <div className="space-y-4">
                    <p className="text-lg font-semibold">Messages</p>
                    {activeThread.messages.length ? activeThread.messages.map((message) => (
                      <article key={message.id} className="soft-panel rounded-[1.4rem] p-4">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <p className="text-sm font-semibold">{message.sender_id === me?.id ? "Seller" : "Buyer"}</p>
                          <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${statusBadge(message.status)}`}>
                            {message.status}
                          </span>
                        </div>
                        <p className="mt-3 text-sm leading-7 text-[rgba(18,38,63,0.82)]">{message.body}</p>
                        <p className="mt-3 text-xs text-[rgba(18,38,63,0.58)]">{formatTime(message.created_at)}</p>
                      </article>
                    )) : (
                      <div className="rounded-[1.4rem] border border-dashed border-[rgba(18,38,63,0.16)] p-6 text-sm text-[rgba(18,38,63,0.66)]">
                        No messages in this thread yet.
                      </div>
                    )}
                  </div>

                  <div className="space-y-4">
                    <p className="text-lg font-semibold">Offers</p>
                    {activeThread.offers.length ? activeThread.offers.map((offer) => {
                      const createdBySeller = offer.created_by_user_id === me?.id;
                      const terminal = ["accepted", "rejected", "cancelled"].includes(offer.status);
                      return (
                        <article key={offer.id} className="soft-panel rounded-[1.4rem] p-4">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                              <p className="font-semibold">{formatPrice(offer.amount_cents, offer.currency_code)}</p>
                              <p className="mt-1 text-xs text-[rgba(18,38,63,0.58)]">
                                {createdBySeller ? "Created by seller" : "Created by buyer"} • {formatTime(offer.created_at)}
                              </p>
                            </div>
                            <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${statusBadge(offer.status)}`}>
                              {offer.status}
                            </span>
                          </div>
                          {offer.note ? <p className="mt-3 text-sm leading-7 text-[rgba(18,38,63,0.78)]">{offer.note}</p> : null}
                          {!terminal && !createdBySeller ? (
                            <div className="mt-4 space-y-3">
                              <div className="flex flex-wrap gap-2">
                                <button
                                  className="button-primary"
                                  type="button"
                                  onClick={() => decideOffer(offer.id, "accept")}
                                  disabled={!!busyAction}
                                >
                                  {isBusy(`accept-offer-${offer.id}`) ? "Queueing..." : "Queue accept"}
                                </button>
                                <button
                                  className="button-secondary"
                                  type="button"
                                  onClick={() => decideOffer(offer.id, "reject")}
                                  disabled={!!busyAction}
                                >
                                  {isBusy(`reject-offer-${offer.id}`) ? "Queueing..." : "Queue reject"}
                                </button>
                              </div>
                              <div className="grid gap-3">
                                <input
                                  className="field"
                                  value={counterAmounts[offer.id] ?? ""}
                                  onChange={(event) => setCounterAmounts((current) => ({ ...current, [offer.id]: event.target.value }))}
                                  placeholder="Counter amount cents"
                                />
                                <textarea
                                  className="field min-h-24"
                                  value={counterNotes[offer.id] ?? ""}
                                  onChange={(event) => setCounterNotes((current) => ({ ...current, [offer.id]: event.target.value }))}
                                  placeholder="Counter note"
                                />
                                <button
                                  className="button-secondary"
                                  type="button"
                                  onClick={() => counterOffer(offer.id)}
                                  disabled={!!busyAction}
                                >
                                  {isBusy(`counter-offer-${offer.id}`) ? "Queueing..." : "Queue counter-offer"}
                                </button>
                              </div>
                            </div>
                          ) : null}
                        </article>
                      );
                    }) : (
                      <div className="rounded-[1.4rem] border border-dashed border-[rgba(18,38,63,0.16)] p-6 text-sm text-[rgba(18,38,63,0.66)]">
                        No offers on this thread yet.
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-6 rounded-[1.6rem] border border-dashed border-[rgba(18,38,63,0.16)] p-8 text-sm text-[rgba(18,38,63,0.66)]">
                No thread selected. Open an existing conversation or create one with a buyer user id.
              </div>
            )}
          </div>
        </div>

        <div className="space-y-8">
          <div className="surface-card rounded-[2rem] p-6">
            <p className="eyebrow text-[var(--color-coral)]">Agent Grants</p>
            <h2 className="display-title mt-2 text-4xl">Issue PATs per agent family.</h2>
            <form onSubmit={createGrant} className="sun-panel mt-5 rounded-[1.7rem] p-5">
              <div className="grid gap-3 md:grid-cols-2">
                <input className="field" value={grantName} onChange={(event) => setGrantName(event.target.value)} placeholder="Grant name" />
                <select className="field" value={agentFamily} onChange={(event) => setAgentFamily(event.target.value)}>
                  <option value="codex">Codex</option>
                  <option value="claudecode">Claude Code</option>
                  <option value="openclaw">OpenClaw</option>
                  <option value="hermes">Hermes</option>
                </select>
              </div>
              <p className="mt-4 text-sm leading-6 text-[rgba(18,38,63,0.72)]">
                Default scopes: {DEFAULT_GRANT_SCOPES.join(", ")}
              </p>
              <button className="button-primary mt-4" type="submit" disabled={!token || !!busyAction}>
                {isBusy("create-grant") ? "Issuing..." : "Create agent grant"}
              </button>
            </form>

            {latestGrantToken ? (
              <div className="sky-panel mt-5 rounded-[1.6rem] p-5">
                <p className="font-semibold">One-time PAT reveal</p>
                <textarea className="field mt-4 min-h-28" readOnly value={latestGrantToken} />
              </div>
            ) : null}

            <div className="mt-5 space-y-4">
              {grants.map((grant) => (
                <article key={grant.id} className="soft-panel rounded-[1.5rem] p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap gap-2">
                        <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${statusBadge(grant.status)}`}>
                          {grant.status}
                        </span>
                        <span className="rounded-full bg-white/72 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]">
                          {grant.agent_family}
                        </span>
                      </div>
                      <p className="mt-3 font-semibold">{grant.name}</p>
                      <p className="mt-2 text-sm text-[rgba(18,38,63,0.68)]">{grant.scopes.join(", ")}</p>
                      <p className="mt-2 text-xs text-[rgba(18,38,63,0.58)]">Created {formatTime(grant.created_at)}</p>
                    </div>
                    {grant.status !== "revoked" ? (
                      <button className="button-secondary" type="button" onClick={() => revokeGrant(grant.id)} disabled={!!busyAction}>
                        {isBusy(`revoke-${grant.id}`) ? "Revoking..." : "Revoke"}
                      </button>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          </div>

          <div className="surface-card rounded-[2rem] p-6">
            <p className="eyebrow text-[var(--color-sea)]">Seller Actions</p>
            <h2 className="display-title mt-2 text-4xl">Prepare non-conversation mutations.</h2>
            <div className="mt-5 space-y-5">
              <div className="soft-panel rounded-[1.6rem] p-5">
                <p className="font-semibold">Prepare publish</p>
                <select className="field mt-4" value={selectedDraftId} onChange={(event) => setSelectedDraftId(event.target.value)}>
                  <option value="">Choose reviewed draft</option>
                  {drafts.map((draft) => (
                    <option key={draft.id} value={draft.id}>
                      {draft.title ?? draft.product_name ?? draft.id}
                    </option>
                  ))}
                </select>
                <button className="button-primary mt-4" type="button" onClick={preparePublish} disabled={!token || !!busyAction}>
                  {isBusy("prepare-publish") ? "Preparing..." : "Queue publish approval"}
                </button>
              </div>

              <div className="soft-panel rounded-[1.6rem] p-5">
                <p className="font-semibold">Prepare repricing</p>
                <select
                  className="field mt-4"
                  value={repricingListingId}
                  onChange={(event) => {
                    const nextId = event.target.value;
                    setRepricingListingId(nextId);
                    const listing = liveListings.find((item) => item.id === nextId);
                    setRepricingPrice(listing ? String(listing.asking_price_cents) : "");
                  }}
                >
                  <option value="">Choose live listing</option>
                  {liveListings.map((listing) => (
                    <option key={listing.id} value={listing.id}>
                      {listing.title} • {formatPrice(listing.asking_price_cents, listing.currency_code)}
                    </option>
                  ))}
                </select>
                <input className="field mt-3" value={repricingPrice} onChange={(event) => setRepricingPrice(event.target.value)} placeholder="New price cents" />
                <button className="button-primary mt-4" type="button" onClick={prepareReprice} disabled={!token || !!busyAction}>
                  {isBusy("prepare-reprice") ? "Preparing..." : "Queue repricing approval"}
                </button>
              </div>

              <div className="soft-panel rounded-[1.6rem] p-5">
                <p className="font-semibold">Prepare fulfillment update</p>
                <select className="field mt-4" value={selectedOrderId} onChange={(event) => setSelectedOrderId(event.target.value)}>
                  <option value="">Choose seller order</option>
                  {orders.map((order) => (
                    <option key={order.id} value={order.id}>
                      {order.id.slice(0, 8)} • {order.status} • {getListingTitle(order.listing_id)}
                    </option>
                  ))}
                </select>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <select className="field" value={fulfillmentStatus} onChange={(event) => setFulfillmentStatus(event.target.value)}>
                    <option value="paid">paid</option>
                    <option value="shipped">shipped</option>
                    <option value="delivered">delivered</option>
                    <option value="cancelled">cancelled</option>
                  </select>
                  <input className="field" value={fulfillmentCarrier} onChange={(event) => setFulfillmentCarrier(event.target.value)} placeholder="Carrier" />
                </div>
                <input className="field mt-3" value={fulfillmentTracking} onChange={(event) => setFulfillmentTracking(event.target.value)} placeholder="Tracking number" />
                <div className="mt-4 flex flex-wrap gap-3">
                  <button className="button-primary" type="button" onClick={prepareFulfillment} disabled={!token || !!busyAction}>
                    {isBusy("prepare-fulfillment") ? "Preparing..." : "Queue fulfillment approval"}
                  </button>
                  <button className="button-secondary" type="button" onClick={prepareCancelOrder} disabled={!token || !!busyAction}>
                    {isBusy("prepare-cancel-order") ? "Preparing..." : "Queue cancel approval"}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div className="surface-card rounded-[2rem] p-6">
            <p className="eyebrow text-[var(--color-coral)]">Action Receipts</p>
            <h2 className="display-title mt-2 text-4xl">Execution history.</h2>
            <div className="mt-5 space-y-4">
              {recentReceipts.length ? recentReceipts.map((receipt) => (
                <article key={receipt.id} className="soft-panel rounded-[1.5rem] p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="font-semibold">{receipt.action_type}</p>
                      <p className="mt-2 text-sm text-[rgba(18,38,63,0.68)]">
                        {receipt.resource_type} • {receipt.resource_id ?? "n/a"} • {formatTime(receipt.created_at)}
                      </p>
                    </div>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${statusBadge(receipt.status)}`}>
                      {receipt.status}
                    </span>
                  </div>
                  <pre className="mt-4 overflow-x-auto rounded-[1.2rem] bg-[rgba(18,38,63,0.04)] p-4 text-xs leading-6 text-[rgba(18,38,63,0.8)]">
                    {formatJson(receipt.result_payload)}
                  </pre>
                  {receipt.error_message ? (
                    <p className="mt-3 break-words text-sm text-[var(--color-coral)]">
                      Failure: {receipt.error_message}
                    </p>
                  ) : null}
                </article>
              )) : (
                <div className="rounded-[1.5rem] border border-dashed border-[rgba(18,38,63,0.16)] p-8 text-sm text-[rgba(18,38,63,0.66)]">
                  No receipts yet. Approve at least one action and the execution record will land here.
                </div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
