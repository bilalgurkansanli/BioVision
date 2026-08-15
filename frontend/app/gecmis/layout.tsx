import type { Metadata } from "next";

/**
 * Exists only to carry metadata.
 *
 * `page.tsx` is a client component, and a client component cannot export
 * `metadata` — so the history page was shipping the site-wide default title and
 * no robots directive at all. The sitemap already leaves this page out on the
 * grounds that a personal history is private by definition; without a noindex
 * here that was a preference, not an instruction, and a crawler following the
 * nav link would have indexed the signed-out shell.
 */
export const metadata: Metadata = {
  title: "Geçmişim",
  robots: { index: false, follow: false },
};

export default function HistoryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
