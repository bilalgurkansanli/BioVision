import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Gizlilik politikası",
  description:
    "Hangi verinin toplandığı, hangisinin toplanmadığı, ne kadar saklandığı ve nasıl silineceği. Fotoğrafın orijinali hiçbir zaman saklanmaz.",
  alternates: { canonical: "/gizlilik" },
};

/**
 * Written against the code, not from a template.
 *
 * Every claim here corresponds to something in the pipeline: the EXIF strip is
 * `pipeline/exif.py`, the face blur is `pipeline/redact.py`, the seven-day
 * deletion is a `pg_cron` job in `infra/supabase/migrations/0002_retention.sql`.
 * Where the system does *not* do something a reader might assume — plates are
 * not blurred — that is stated rather than omitted.
 */
export default function PrivacyPage() {
  return (
    <main className="page">
      <header className="hero">
        <h1 className="hero__title">Gizlilik politikası</h1>
        <p className="hero__subtitle">
          Son güncelleme: 14 Ağustos 2026
        </p>
        <p className="hero__body">
          Bu metin, sistemin gerçekte ne yaptığını anlatır. Her madde koddaki bir
          davranışa karşılık gelir; yapmadığımız şeyler de yazılıdır.
        </p>
      </header>

      <section>
        <h2 className="notice__title">Veri sorumlusu</h2>
        <p>
          Bilal Gürkan Şanlı. İletişim:{" "}
          <a href="https://bilalgurkansanli.com">bilalgurkansanli.com</a>. Bu, bir
          şirket ürünü değil, açık kaynaklı bir portföy projesidir.
        </p>
      </section>

      <section>
        <h2 className="notice__title">Yüklediğiniz fotoğrafa ne oluyor</h2>
        <p>
          Fotoğraf sunucuya ulaştığı anda, sırayla ve her seferinde aynı şekilde
          şunlardan geçer:
        </p>
        <ol>
          <li>Biçim, boyut ve bozukluk kontrolü.</li>
          <li>
            <strong>EXIF okunur</strong> — çekim tarihi, cihaz modeli ve konum
            verisinin <em>var olup olmadığı</em>. Koordinatların kendisi hiçbir
            zaman okunmaz, kaydedilmez, gösterilmez.
          </li>
          <li>Fotoğrafın yönü düzeltilir.</li>
          <li>Görselin parmak izi (algısal hash) çıkarılır.</li>
          <li>
            <strong>Yüzler bulanıklaştırılır</strong> — mozaik yöntemiyle, yani
            geri döndürülemez şekilde. Bulanıklaştırma filtresi değil, verinin
            yok edilmesi.
          </li>
          <li>
            <strong>Tüm EXIF silinir</strong> ve görsel 1280 piksele küçültülür.
          </li>
          <li>Modellere ancak bu hâli verilir.</li>
        </ol>
        <p>
          <strong>Yüklediğiniz orijinal dosya hiçbir yerde saklanmaz.</strong>{" "}
          Diske yazılan tek şey, yüzleri bulanıklaştırılmış ve EXIF&apos;i silinmiş
          küçültülmüş kopyadır — ve o da yalnızca giriş yaptıysanız.
        </p>
      </section>

      <section className="notice notice--unplaced">
        <h2 className="notice__title">Plakalar bulanıklaştırılmıyor</h2>
        <p>
          Yüzler için ölçülmüş bir dedektör kullanıyoruz. Plakalar için
          güvenilir ve izinli bir dedektör bulamadık, dolayısıyla{" "}
          <strong>plakalar bulanıklaştırılmıyor.</strong> Yaptığımızı iddia edip
          yapmamaktansa yapmadığımızı söylüyoruz. Plakası görünen bir fotoğraf
          yüklerken bunu bilin.
        </p>
      </section>

      <section>
        <h2 className="notice__title">Giriş yapmadan kullanırsanız</h2>
        <p>
          Hiçbir şey saklanmaz. Ne görsel, ne sonuç, ne kayıt. Sonuç size
          döndürülür ve unutulur. Bunun sebebi cömertlik değil tutarlılık:
          kimsenin erişemeyeceği bir kaydı tutmak, size ne gösterebileceğimiz ne
          de sildirebileceğimiz bir veri biriktirmek olurdu.
        </p>
      </section>

      <section>
        <h2 className="notice__title">Giriş yaparsanız</h2>
        <dl className="provenance__grid">
          <dt>Google&apos;dan alınan</dt>
          <dd>E-posta adresiniz ve bir kullanıcı kimliği. Profil fotoğrafı, kişi listesi veya başka hiçbir şey değil.</dd>

          <dt>Saklanan</dt>
          <dd>
            Analiz sonucu (alan, güven skoru, bulgular) ve yüzleri
            bulanıklaştırılmış görsel.
          </dd>

          <dt>Saklanmayan</dt>
          <dd>Orijinal dosya, EXIF verisi, konum koordinatları.</dd>

          <dt>Süre</dt>
          <dd>
            <strong>7 gün.</strong> Veritabanındaki zamanlanmış bir görev her gece
            süresi dolanları siler. Uygulama kapalıyken de çalışır.
          </dd>

          <dt>Kim erişebilir</dt>
          <dd>
            Yalnızca siz. Bu, uygulamadaki bir filtre değil — veritabanının satır
            düzeyi güvenlik kuralı. Uygulamada hata olsa bile veritabanı başka
            birinin satırını döndürmez.
          </dd>
        </dl>
      </section>

      <section>
        <h2 className="notice__title">Üçüncü taraflar</h2>
        <dl className="provenance__grid">
          <dt>Supabase</dt>
          <dd>Kimlik doğrulama, veritabanı ve dosya saklama.</dd>

          <dt>Google</dt>
          <dd>Yalnızca giriş yaparsanız, yalnızca kimlik doğrulama için.</dd>

          <dt>Anthropic</dt>
          <dd>
            Uzman modeli olmayan alanlarda serbest metin açıklama üretmek için —
            ve yalnızca giriş yapmış kullanıcılar için. Gönderilen görsel, yüzleri
            bulanıklaştırılmış ve EXIF&apos;i silinmiş olandır.
          </dd>

          <dt>Vercel</dt>
          <dd>Arayüzün barındırılması.</dd>
        </dl>
        <p>
          <strong>Analitik, reklam ve izleme çerezi yok.</strong> Sayfa görüntüleme
          sayacı, ısı haritası, üçüncü taraf pikseli de yok. Tarayıcınızda tutulan
          tek şey oturum bilgisidir ve o da çıkış yaptığınızda silinir.
        </p>
      </section>

      <section>
        <h2 className="notice__title">KVKK kapsamındaki haklarınız</h2>
        <p>
          6698 sayılı kanunun 11. maddesi uyarınca verilerinize erişme, düzeltme
          ve silme hakkınız var. Bu haklardan ikisi için başvuru yapmanıza gerek
          yok, çünkü doğrudan arayüzde duruyorlar:
        </p>
        <ul>
          <li>
            <strong>Erişim:</strong> <Link href="/gecmis">Geçmişim</Link>{" "}
            sayfası tuttuğumuz her kaydı gösterir.
          </li>
          <li>
            <strong>Silme:</strong> aynı sayfada tek tek veya tümünü birden
            silebilirsiniz. Silme, veritabanından gerçekten kaldırır.
          </li>
        </ul>
        <p>
          Diğer talepler için yukarıdaki iletişim adresini kullanın.
        </p>
      </section>

      <section>
        <h2 className="notice__title">Bu sayfa değişirse</h2>
        <p>
          Değişiklikler{" "}
          <a
            href="https://github.com/bilalgurkansanli/BioVision/commits/main"
            rel="noopener noreferrer"
            target="_blank"
          >
            genel commit geçmişinde
          </a>{" "}
          görünür. Bu metnin ne zaman ve neden değiştiğini kimseye sormanıza gerek
          kalmadan görebilirsiniz.
        </p>
      </section>
    </main>
  );
}
