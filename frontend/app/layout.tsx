import type { Metadata, Viewport } from "next";
import Link from "next/link";

import { SiteNav } from "@/components/SiteNav";
import { SITE_URL } from "@/lib/site";

import "./globals.css";

const TITLE = "BioPolicy — ne bilmediğini söyleyen hasar analizi";
const DESCRIPTION =
  "Hasar fotoğrafını sınıflandırır, o alan için eğitilmiş bir model varsa ölçer, " +
  "yoksa ölçmediğini açıkça söyler. Uydurulmuş bulgu yok, etiketsiz güven skoru yok.";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: TITLE,
    // Page titles read as "Gizlilik · BioPolicy" rather than repeating the
    // whole tagline, which would push the distinctive part out of the SERP.
    template: "%s · BioPolicy",
  },
  description: DESCRIPTION,
  applicationName: "BioPolicy",
  authors: [{ name: "Bilal Gürkan Şanlı", url: "https://bilalgurkansanli.com" }],
  creator: "Bilal Gürkan Şanlı",
  keywords: [
    "hasar analizi",
    "araç hasar tespiti",
    "yapay zeka hasar tespiti",
    "sigorta hasar değerlendirme",
    "görüntü işleme",
    "model kalibrasyonu",
  ],
  alternates: {
    canonical: "/",
    languages: { "tr-TR": "/" },
  },
  openGraph: {
    type: "website",
    locale: "tr_TR",
    url: SITE_URL,
    siteName: "BioPolicy",
    title: TITLE,
    description: DESCRIPTION,
    images: [
      {
        url: "/opengraph-image",
        width: 1200,
        height: 630,
        alt: "BioPolicy — ne bilmediğini söyleyen hasar analizi",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/opengraph-image"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large" },
  },
  category: "technology",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fbfaf8" },
    { media: "(prefers-color-scheme: dark)", color: "#14161a" },
  ],
  width: "device-width",
  initialScale: 1,
};

/**
 * Structured data.
 *
 * Describes the thing as a WebApplication and states the price, because the
 * alternative is search engines guessing. `featureList` deliberately includes
 * the refusal behaviour: it is the distinguishing feature, not a limitation to
 * be hidden from a crawler.
 */
const JSON_LD = {
  "@context": "https://schema.org",
  "@type": "WebApplication",
  name: "BioPolicy",
  url: SITE_URL,
  description: DESCRIPTION,
  applicationCategory: "MultimediaApplication",
  operatingSystem: "Web",
  inLanguage: "tr-TR",
  isAccessibleForFree: true,
  offers: { "@type": "Offer", price: "0", priceCurrency: "TRY" },
  author: {
    "@type": "Person",
    name: "Bilal Gürkan Şanlı",
    url: "https://bilalgurkansanli.com",
  },
  featureList: [
    "Hasar fotoğrafını alanına göre sınıflandırma",
    "Uzman modeli olan alanlarda maske tabanlı ölçüm",
    "Uzman modeli olmayan alanlarda bulgu üretmeyi reddetme",
    "Kalibre edilmiş ve edilmemiş güven skorlarını ayrı raporlama",
    "Yüz bulanıklaştırma ve konum verisi silme",
  ],
  license: "https://www.gnu.org/licenses/agpl-3.0.html",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>
        <script
          type="application/ld+json"
          // Static object serialised at build time; no user input reaches it.
          dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }}
        />
        <SiteNav />
        {children}
        <footer className="footer">
          <nav className="footer__links" aria-label="Alt bağlantılar">
            <Link href="/gizlilik">Gizlilik</Link>
            <Link href="/kosullar">Kullanım koşulları</Link>
            <Link href="/lisans">Lisans ve kaynaklar</Link>
            <a
              href="https://github.com/bilalgurkansanli/BioVision"
              rel="noopener noreferrer"
              target="_blank"
            >
              Kaynak kodu
            </a>
          </nav>
          <p>
            BioPolicy · AGPL-3.0 ·{" "}
            <a href="https://bilalgurkansanli.com" rel="author">
              Bilal Gürkan Şanlı
            </a>
          </p>
          <p className="footer__note">
            Ölçüm sonuçları yalnızca uzman modeli olan alanlar için üretilir.
            Diğer alanlarda sistem bulgu üretmez.
          </p>
        </footer>
      </body>
    </html>
  );
}
