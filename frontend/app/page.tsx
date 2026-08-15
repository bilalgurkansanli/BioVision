import Link from "next/link";

import { Demo } from "@/components/Demo";

/**
 * The landing page.
 *
 * Server-rendered apart from `Demo`, which needs state to switch between the
 * three outcomes. The live domain list is still deliberately absent: it is the
 * one piece of content that could go stale or fail, it already sits at the top
 * of `/analiz` where a user is about to act on it, and a hardcoded "1 / 4" here
 * would be exactly the kind of unmeasured number this project refuses to
 * publish. The demo carries the same information honestly, by saying which of
 * the three shapes the system can produce today.
 */

const PIPELINE = [
  {
    name: "Doğrulama",
    note: "Tür, boyut ve bozukluk kontrolü. Hareketli görseller reddedilir.",
  },
  {
    name: "Temizlik",
    note: "EXIF silinir, yüzler mozaikle yok edilir — bulanıklaştırılmaz.",
  },
  {
    name: "Kapı",
    note: "Bu gerçekten bir hasar fotoğrafı mı? Değilse burada durur.",
  },
  {
    name: "Yönlendirme",
    note: "Hangi alan — ve bu güven skoru kalibre edilmiş mi?",
  },
  {
    name: "Cevap",
    note: "Uzman model varsa ölçüm, yoksa açık bir ret.",
  },
];

const PROVEN = [
  "Arkasında model olmayan bir bulgu üretilemez — hem pydantic doğrulayıcısı hem Postgres CHECK kısıtı engeller",
  "Yeni bir alan eklemek kod değişikliği gerektirmez; YAML'a bir kayıt yetiyor",
  "Zayıf bir yönlendirme kararı uzman modeli hiçbir zaman çalıştırmaz",
  "Anonim trafik ücretli açıklama bütçesini harcayamaz",
  "Aynı görsel ücretli API'ye yalnızca bir kez gider",
  "Saklanan görselde EXIF verisi bulunmaz",
  "Mozaik detayı yok eder, yumuşatmaz — bloğun her pikseli birebir aynıdır",
  "Çapraz kullanıcı okumasını uygulama değil, veritabanının kendisi reddeder",
];

const OPEN = [
  "Yönlendirici doğruluğu ve kalibrasyon hatası — etiketli bir değerlendirme seti gerekiyor",
  "Araç modelinde sınıf başına mAP — VehiDE üzerinde bir eğitim koşusu gerekiyor",
  "Yüz bulanıklaştırmada kaçırma oranı — 30-50 etiketli fotoğraf gerekiyor",
  "VPS gecikmesi ve istek başına gerçek maliyet — bir dağıtım gerekiyor",
];

export default function Home() {
  return (
    <main className="landing">
      <div className="hero-wrap">
        <section className="shell hero">
          <p className="hero__eyebrow">
            <span className="hero__eyebrow-dot" aria-hidden="true" />
            Açık kaynak · AGPL-3.0
          </p>

          <h1 className="hero__headline">
            Ne bilmediğini <em>söyleyen</em> hasar analizi
          </h1>

          <p className="hero__lead">
            Bir hasar fotoğrafı yükleyin. Sistem önce fotoğrafın hangi alana ait
            olduğunu belirler; o alan için eğitilmiş bir uzman modeli varsa ölçüm
            yapar. Yoksa tahmin yürütmez — bunu açıkça söyler.
          </p>

          <div className="hero__actions">
            <Link className="btn btn--primary" href="/analiz">
              Fotoğraf yükleyip deneyin
            </Link>
            <a
              className="btn btn--ghost"
              href="https://github.com/bilalgurkansanli/BioVision"
              rel="noopener noreferrer"
              target="_blank"
            >
              Kaynak kodu
            </a>
          </div>

          <p className="hero__note">
            Giriş gerekmez · yüzler bulanıklaştırılır · orijinal dosya saklanmaz
          </p>
        </section>
      </div>

      <section className="section section--tinted">
        <div className="shell">
          <div className="section__head">
            <p className="section__eyebrow">Örnek</p>
            <h2 className="section__title">
              Bir fotoğraf üç cevaptan birini alır
            </h2>
            <p className="section__lead">
              Bunlar aynı şablonun üzerine takılmış üç rozet değil. Üçü de farklı
              görünür, çünkü üçü de farklı şeyler söylüyor. Ölçüm yapılmadığını
              küçük gri bir dipnota sıkıştırmak, kendinden emin görünen bir
              sonucun yanına asterisk koymaktan farksız olurdu. Aşağıdaki kart,
              uygulamanın kullandığı bileşenin ta kendisi — bir taklidi değil.
            </p>
          </div>

          <Demo />
        </div>
      </section>

      <section className="section">
        <div className="shell">
          <div className="section__head">
            <p className="section__eyebrow">İşleyiş</p>
            <h2 className="section__title">Bir fotoğrafa ne oluyor</h2>
            <p className="section__lead">
              Her adım sonuca bir şey ekler ya da onu durdurur. Hiçbiri atlanmaz,
              ve her adımın ne yaptığı sonuçtaki &laquo;bu sonuç nasıl
              üretildi&raquo; bölümünde tek tek yazar.
            </p>
          </div>

          <ol className="flow">
            {PIPELINE.map((step, index) => (
              <li key={step.name} className="flow__step">
                <span className="flow__marker" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="flow__body">
                  <h3 className="flow__name">{step.name}</h3>
                  <p className="flow__note">{step.note}</p>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="section">
        <div className="shell">
          <div className="section__head">
            <p className="section__eyebrow">Kanıt</p>
            <h2 className="section__title">Kanıtlanan ve henüz kanıtlanmayan</h2>
            <p className="section__lead">
              Bu ayrımı yapmak projenin tamamının konusu, o yüzden projenin kendi
              tanıtım sayfasında da yapılıyor. Sağdaki liste tahminle
              doldurulmuyor: boş bir hücre sıfır demek değil, &laquo;henüz
              ölçülmedi&raquo; demek.
            </p>
          </div>

          <div className="evidence">
            <div className="evidence__column evidence__column--proven">
              <h3 className="evidence__heading">
                Kanıtlanmış
                <span className="evidence__count">{PROVEN.length}</span>
              </h3>
              <p className="evidence__note">Her biri depodaki bir testle bağlı.</p>
              <ul className="evidence__list">
                {PROVEN.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>

            <div className="evidence__column evidence__column--open">
              <h3 className="evidence__heading">
                Henüz ölçülmemiş
                <span className="evidence__count">{OPEN.length}</span>
              </h3>
              <p className="evidence__note">
                Ölçülene kadar burada, sayı olarak değil eksik olarak duruyor.
              </p>
              <ul className="evidence__list">
                {OPEN.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="shell">
          <div className="closing">
            <h2 className="closing__title">
              Bir fotoğrafla <em>deneyin</em>
            </h2>
            <p className="closing__body">
              Araç, bina ya da telefon ekranı — hangisini yüklerseniz yükleyin,
              sistem ne yaptığını ve ne yapmadığını söyleyecek. Giriş yapmadan da
              tam olarak çalışır; aradaki tek fark kayıt tutulmamasıdır.
            </p>
            <Link className="btn btn--primary" href="/analiz">
              Analize başlayın
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
