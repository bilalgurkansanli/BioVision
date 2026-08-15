import type { Metadata } from "next";
import Link from "next/link";

import { DocLinks } from "@/components/DocLinks";

export const metadata: Metadata = {
  title: "Kullanım koşulları",
  description:
    "Bu sistemin ne olduğu, ne olmadığı ve sonuçlarına ne kadar güvenilebileceği. Hasar ekspertizi yerine geçmez.",
  alternates: { canonical: "/kosullar" },
};

export default function TermsPage() {
  return (
    <main className="doc">
      <header className="doc__header">
        <p className="doc__kicker">Belge</p>
        <h1 className="doc__title">Kullanım koşulları</h1>
        <p className="doc__meta">Son güncelleme: 14 Ağustos 2026</p>
      </header>

      <section className="doc__section notice notice--unplaced">
        <h2>Bu bir ekspertiz raporu değildir</h2>
        <p>
          BioVision bir gösterim projesidir. Ürettiği hiçbir çıktı hasar
          ekspertizi, sigorta değerlendirmesi, onarım maliyeti tahmini ya da
          hukuki delil yerine geçmez. Bir hasar talebinde, alım satımda veya
          anlaşmazlıkta <strong>tek dayanak olarak kullanmayın.</strong>
        </p>
      </section>

      <section className="doc__section">
        <h2>Sonuçlara ne kadar güvenilebilir</h2>
        <p>Sistem üç farklı şey söyleyebilir ve aralarındaki fark önemlidir:</p>
        <dl className="facts">
          <dt>Ölçüldü</dt>
          <dd>
            O alan için eğitilmiş bir model bulguları üretti. Bulgular gerçek bir
            ölçümdür — ama modelin sınıf bazlı başarımı{" "}
            <a
              href="https://github.com/bilalgurkansanli/BioVision#73-vehicle-specialist--per-class-performance-vehide-test-split"
              rel="noopener noreferrer"
              target="_blank"
            >
              README&apos;de yayınlanır
            </a>
            , zayıf sınıflar dahil.
          </dd>

          <dt>Tarif edildi</dt>
          <dd>
            O alan için eğitilmiş modelimiz yok. Bir görsel dil modeli fotoğrafı
            kelimelerle anlatır. <strong>Bu bir ölçüm değildir</strong> ve sistem
            bu durumda hiçbir bulgu üretmez.
          </dd>

          <dt>Yerleştirilemedi</dt>
          <dd>
            Fotoğrafın hangi alana ait olduğunu yeterli güvenle belirleyemedik ve
            tahmin yürütmüyoruz.
          </dd>
        </dl>
        <p style={{ marginTop: "1rem" }}>
          Ayrıca her güven skoru, <strong>kalibre edilmiş mi değil mi</strong>{" "}
          olduğunu yanında taşır. &ldquo;%93&rdquo; ile &ldquo;kalibre edilmemiş
          %93&rdquo; aynı şey değildir; ikincisi ham bir model çıktısıdır ve
          olasılık olarak okunmamalıdır.
        </p>
      </section>

      <section className="doc__section">
        <h2>Ne yüklememelisiniz</h2>
        <ul>
          <li>Size ait olmayan veya paylaşma hakkınız bulunmayan fotoğraflar.</li>
          <li>
            Kimlik belgesi, banka kartı, evrak — bu sistem hasar fotoğrafı için
            yapılmıştır ve bunları zaten reddeder.
          </li>
          <li>
            Başkalarının yüzünün ana konu olduğu fotoğraflar. Yüzleri
            bulanıklaştırıyoruz, ama bu bir izin yerine geçmez.
          </li>
        </ul>
        <p>
          Plakaların bulanıklaştırılmadığını hatırlatırız — ayrıntısı{" "}
          <Link href="/gizlilik">gizlilik politikasında</Link>.
        </p>
      </section>

      <section className="doc__section">
        <h2>Kullanım sınırları</h2>
        <p>
          Anonim kullanımda günlük 20, giriş yapmış kullanıcılarda günlük 100
          analiz sınırı vardır. Bunlar sunucuyu korumak içindir; aşıldığında
          sistem açıkça söyler.
        </p>
        <p>
          Görsel dil modeli için aylık sabit bir bütçe tavanı vardır. Tavan
          dolduğunda sistem <strong>tarif üretmeyi durdurur</strong> ve bunu
          söyler — sessizce daha kötü bir sonuç döndürmez.
        </p>
      </section>

      <section className="doc__section">
        <h2>Hizmet garantisi yok</h2>
        <p>
          Bu proje tek bir sunucuda, tek bir kişi tarafından çalıştırılıyor.
          Çalışma süresi taahhüdü, yedekleme garantisi ve destek yükümlülüğü
          yoktur. Kayıtlar 7 gün sonra silinir; saklamak istediğiniz bir sonuç
          varsa kendiniz kaydedin.
        </p>
      </section>

      <section className="doc__section">
        <h2>Yazılımın lisansı</h2>
        <p>
          Kaynak kodu AGPL-3.0 ile açıktır — inceleyebilir, çalıştırabilir ve
          değiştirebilirsiniz. Ayrıntılar{" "}
          <Link href="/lisans">lisans ve kaynaklar</Link> sayfasında.
        </p>
      </section>

      <DocLinks current="/kosullar" />
    </main>
  );
}
