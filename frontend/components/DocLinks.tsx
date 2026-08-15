import Link from "next/link";

/**
 * Cross-links between the three documents.
 *
 * They are one set — the terms point at the privacy policy, the privacy policy
 * points at the licence — but a reader who lands on one from a search result
 * previously had to go back to the footer to find the other two. The current
 * page is omitted rather than rendered as a dead link.
 */

const DOCS = [
  { href: "/gizlilik", label: "Gizlilik politikası" },
  { href: "/kosullar", label: "Kullanım koşulları" },
  { href: "/lisans", label: "Lisans ve kaynaklar" },
] as const;

export function DocLinks({ current }: { current: (typeof DOCS)[number]["href"] }) {
  return (
    <nav className="doc__siblings" aria-label="Diğer belgeler">
      {DOCS.filter((doc) => doc.href !== current).map((doc) => (
        <Link key={doc.href} href={doc.href}>
          {doc.label}
        </Link>
      ))}
      <Link href="/analiz">Analize dön</Link>
    </nav>
  );
}
