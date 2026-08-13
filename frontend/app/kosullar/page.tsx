import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Kullanım koşulları",
  description:
    "Bu sistemin ne olduğu, ne olmadığı ve sonuçlarına ne kadar güvenilebileceği. Hasar ekspertizi yerine geçmez.",
  alternates: { canonical: "/kosullar" },
};

export default function TermsPage() {
  return (
    <main className="page">
      <header className="hero">
        <h1 className="hero__title">Kullanım koşulları</h1>
        <p className="hero__subtitle">Son güncelleme: 14 Ağustos 2026</p>
      </header>

      <section className="notice notice--unplaced">
        <h2 className="notice__title">Bu bir ekspertiz raporu değildir</h2>
        <p>
          BioPolicy bir gösterim projesidir. Ürettiği hiçbir çıktı hasar
          ekspertizi, sigorta değerlendirmesi, onarım maliyeti tahmini ya da
          hukuki delil yerine geçmez. Bir hasar talebinde, alım satımda veya
          anlaşmazlıkta <strong>tek dayanak olarak kullanmayın.</strong>
        </p>
      </section>

      <section>
        <h2 className="notice__title">Sonuçlara ne kadar güvenilebilir</h2>
        <p>Sistem üç farklı şey söyleyebilir ve aralarındaki fark önemlidir:</p>
        <dl className="provenance__grid">
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
        <p>
          Ayrıca her güven skoru, <strong>kalibre edilmiş mi değil mi</strong>{" "}
          olduğunu yanında taşır. &ldquo;%93&rdquo; ile &ldquo;kalibre edilmemiş
          %93&rdquo; aynı şey değildir; ikincisi ham bir model çıktısıdır ve
          olasılık olarak okunmamalıdır.
        </p>
      </section>

      <section>
        <h2 className="notice__title">Ne yüklememelisiniz</h2>
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

      <section>
        <h2 className="notice__title">Kullanım sınırları</h2>
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

      <section>
        <h2 className="notice__title">Hizmet garantisi yok</h2>
        <p>
          Bu proje tek bir sunucuda, tek bir kişi tarafından çalıştırılıyor.
          Çalışma süresi taahhüdü, yedekleme garantisi ve destek yükümlülüğü
          yoktur. Kayıtlar 7 gün sonra silinir; saklamak istediğiniz bir sonuç
          varsa kendiniz kaydedin.
        </p>
      </section>

      <section>
        <h2 className="notice__title">Yazılımın lisansı</h2>
        <p>
          Kaynak kodu AGPL-3.0 ile açıktır — inceleyebilir, çalıştırabilir ve
          değiştirebilirsiniz. Ayrıntılar{" "}
          <Link href="/lisans">lisans ve kaynaklar</Link> sayfasında.
        </p>
      </section>
    </main>
  );
}
