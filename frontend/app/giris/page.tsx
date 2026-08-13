import type { Metadata } from "next";

import { SignInPanel } from "./SignInPanel";

export const metadata: Metadata = {
  title: "Giriş yap",
  description:
    "Google hesabınızla giriş yapın ve analiz geçmişinizi görün. Giriş yapmadan da analiz yapabilirsiniz; sadece kayıt tutulmaz.",
  alternates: { canonical: "/giris" },
  // A sign-in page has nothing to rank for and would only compete with the
  // pages that do. Following the links is still useful.
  robots: { index: false, follow: true },
};

export default function SignInPage() {
  return (
    <main className="page">
      <header className="hero">
        <h1 className="hero__title">Giriş yap</h1>
        <p className="hero__subtitle">
          Geçmişinizi görmek için. Analiz için gerekli değil.
        </p>
      </header>

      <SignInPanel />

      <section className="notice notice--no-specialist">
        <h2 className="notice__title">Giriş yapmadan da kullanabilirsiniz</h2>
        <p>
          Analiz, giriş yapmadan tam olarak çalışır. Aradaki tek fark kayıt: giriş
          yapmadan gönderilen fotoğraflar <strong>hiçbir yerde saklanmaz</strong>,
          çünkü sizden başka kimsenin erişemeyeceği bir kaydı tutmanın bir anlamı
          olmazdı — ne size gösterebilirdik ne de silmenizi sağlayabilirdik.
        </p>
      </section>

      <section>
        <h2 className="domains__title">Giriş yaptığınızda ne oluyor</h2>
        <dl className="provenance__grid">
          <dt>Google&apos;dan alınan</dt>
          <dd>E-posta adresiniz ve bir kullanıcı kimliği. Başka bir şey değil.</dd>

          <dt>Saklanan</dt>
          <dd>
            Analiz sonuçlarınız ve <strong>yüzleri bulanıklaştırılmış</strong>{" "}
            görsel — orijinal dosya değil.
          </dd>

          <dt>Saklanma süresi</dt>
          <dd>7 gün. Sonra veritabanı kendisi siler.</dd>

          <dt>Erişim</dt>
          <dd>
            Yalnızca siz. Bu, uygulamadaki bir kontrol değil, veritabanının
            kendi kuralı.
          </dd>
        </dl>
      </section>
    </main>
  );
}
