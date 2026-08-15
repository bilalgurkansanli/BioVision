import type { Metadata } from "next";

import { Analyzer } from "./Analyzer";

export const metadata: Metadata = {
  title: "Fotoğraf analizi",
  description:
    "Hasar fotoğrafınızı yükleyin. Sistem alanı belirler, o alan için eğitilmiş " +
    "bir model varsa ölçer, yoksa ölçmediğini açıkça söyler. Giriş gerekmez.",
  alternates: { canonical: "/analiz" },
};

export default function AnalyzePage() {
  return (
    <main className="app">
      <header>
        <h1 className="app__title">Fotoğraf analizi</h1>
        <p className="app__lead">
          Bir hasar fotoğrafı yükleyin. Sonuç üç şekilden birinde döner: ölçüm,
          açık bir &laquo;bu alan için modelimiz yok&raquo;, ya da
          &laquo;bu fotoğrafı yerleştiremedik&raquo;.
        </p>
      </header>

      <Analyzer />
    </main>
  );
}
