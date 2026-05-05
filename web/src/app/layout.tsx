import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent Marketplace",
  description: "Bright yellow AI-assisted classifieds marketplace built for crawlers, humans, and agents.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
  const backendRoot = apiBaseUrl.replace(/\/api\/v1$/, "");

  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full bg-[var(--color-cream)] text-[var(--color-ink)]">
        <div className="pointer-events-none fixed inset-0 -z-10 bg-[radial-gradient(circle_at_top_left,_rgba(255,216,77,0.72),_transparent_28%),radial-gradient(circle_at_top_right,_rgba(11,150,255,0.16),_transparent_26%),radial-gradient(circle_at_50%_120%,_rgba(255,216,77,0.22),_transparent_24%),linear-gradient(180deg,_rgba(255,247,176,0.78)_0%,_rgba(255,253,242,0.96)_42%,_rgba(255,243,198,0.88)_100%)]" />
        <header className="border-b border-[rgba(18,38,63,0.08)] bg-[rgba(255,253,242,0.72)] backdrop-blur-sm">
          <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
            <Link href="/" className="flex items-center gap-3">
              <span className="rounded-full bg-[var(--color-gold)] px-3 py-1 text-xs font-semibold tracking-[0.24em] text-[var(--color-ink)]">
                AGENT READY
              </span>
              <div>
                <span className="font-[family:var(--font-dm-serif)] text-2xl">Agent Marketplace</span>
                <p className="text-xs uppercase tracking-[0.2em] text-[rgba(18,38,63,0.56)]">Bright yellow classifieds MVP</p>
              </div>
            </Link>
            <nav className="flex items-center gap-5 text-sm font-medium">
              <Link href="/" className="hover:text-[var(--color-sea)]">Browse</Link>
              <Link href="/sell" className="hover:text-[var(--color-sea)]">Sell with AI</Link>
              <a href={`${backendRoot}/openapi.json`} className="hover:text-[var(--color-sea)]">OpenAPI</a>
            </nav>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-[rgba(18,38,63,0.08)] bg-[rgba(255,253,242,0.56)]">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-6 py-8 text-sm text-[rgba(18,38,63,0.74)] md:flex-row md:items-center md:justify-between">
            <p>Public inventory is intentionally crawlable. Writes, AI, and orders require auth.</p>
            <div className="flex gap-4">
              <a href="/llms.txt" className="hover:text-[var(--color-sea)]">llms.txt</a>
              <a href="/robots.txt" className="hover:text-[var(--color-sea)]">robots.txt</a>
              <a href="/sitemap.xml" className="hover:text-[var(--color-sea)]">sitemap.xml</a>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
