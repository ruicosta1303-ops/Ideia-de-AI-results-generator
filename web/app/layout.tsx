import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { SyntheticBanner } from "@/components/SyntheticBanner";
import "./globals.css";

export const metadata: Metadata = {
  title: "Match Model — football probabilities",
  description:
    "Statistical match probabilities for European football leagues, with transparent evaluation. Estimates, not guarantees.",
};

const nav = [
  { href: "/", label: "Fixtures" },
  { href: "/compare", label: "Compare" },
  { href: "/validation", label: "Model performance" },
  { href: "/about", label: "Method & data" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col font-sans">
        <Suspense fallback={null}>
          <SyntheticBanner />
        </Suspense>
        <header className="border-b border-border bg-surface-1">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
            <Link href="/" className="text-base font-semibold tracking-tight">
              Match<span className="text-home">Model</span>
            </Link>
            <nav className="flex flex-wrap gap-4 text-sm text-secondary">
              {nav.map((n) => (
                <Link key={n.href} href={n.href} className="hover:text-primary">
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
        <footer className="border-t border-border px-4 py-4 text-center text-xs text-muted">
          Probabilities are statistical estimates with real uncertainty — never guarantees. Not betting advice.
        </footer>
      </body>
    </html>
  );
}
