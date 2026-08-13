import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Sayfa bulunamadı",
  robots: { index: false, follow: true },
};

export default function NotFound() {
  return (
    <main className="page">
      <section className="notice notice--unplaced">
        <h1 className="notice__title">Bu sayfa yok</h1>
        <p>
          Aradığınız adres bize ulaşmadı. Yanlış yazılmış olabilir, ya da bir
          zamanlar var olup kaldırılmış olabilir.
        </p>
      </section>
      <p>
        <Link href="/">Analize dön</Link>
      </p>
    </main>
  );
}
