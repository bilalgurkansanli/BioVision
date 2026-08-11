import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "BioVision — ne bilmediğini söyleyen hasar analizi",
  description:
    "Hasar fotoğrafını sınıflandırır, uzman modeli varsa ölçer, yoksa bunu açıkça söyler.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>
        <nav className="nav">
          <Link href="/" className="nav__brand">
            BioVision
          </Link>
          <Link href="/history">Geçmişim</Link>
        </nav>
        {children}
        <footer className="footer">
          <p>
            BioVision · AGPL-3.0 ·{" "}
            <a href="https://bilalgurkansanli.com">Bilal Gürkan Şanlı</a>
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
