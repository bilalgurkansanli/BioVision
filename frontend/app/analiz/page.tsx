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
        {/* Measured, not guessed: the same wrecked car returns 1 finding in a
            scene shot and 4 when cropped to the car. The training set is all
            close-ups, so this is the framing the model was never shown. Telling
            people before they upload costs nothing; finding out afterwards costs
            them their result. README section 7.7. */}
        <p className="app__hint">
          <strong>Hasarı yakından çekin.</strong> Sistem geniş açı sahnelerde
          &mdash; aracın kare içinde küçük kaldığı fotoğraflarda &mdash; hasarın
          çoğunu kaçırıyor. Aynı hasarlı araç, sahne fotoğrafında 1 bulgu,
          araca yakınlaştırılmış halinde 4 bulgu veriyor.
        </p>
      </header>

      <Analyzer />
    </main>
  );
}
