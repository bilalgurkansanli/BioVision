"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { authConfigured, currentEmail, signInWithGoogle, signOut } from "@/lib/supabase";

export function SignInPanel() {
  const [email, setEmail] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    currentEmail()
      .then(setEmail)
      .catch(() => setEmail(null))
      .finally(() => setReady(true));
  }, []);

  // Not an error state, so it is not styled as one: the deployment simply has
  // no identity provider attached, and analysis is unaffected.
  if (!authConfigured) {
    return (
      <section className="notice notice--unplaced">
        <h2 className="notice__title">Bu ortamda giriş yapılandırılmamış</h2>
        <p>
          Kimlik sağlayıcı bu kuruluma bağlı değil. Bunu bir hata olarak
          göstermek yerine söylüyoruz: analiz çalışıyor, giriş çalışmıyor.
        </p>
        <p style={{ marginTop: "0.75rem" }}>
          <Link href="/analiz">Analize dön</Link>
        </p>
      </section>
    );
  }

  if (!ready) {
    return (
      <section className="auth__card">
        <p className="dropzone__hint" style={{ margin: 0 }}>
          Oturum kontrol ediliyor…
        </p>
      </section>
    );
  }

  if (email) {
    return (
      <section className="auth__card">
        <p className="auth__signed-in">
          <span className="auth__email">{email}</span> olarak giriş yaptınız.
        </p>
        <Link className="btn btn--primary" href="/gecmis">
          Geçmişinize gidin
        </Link>
        <button
          type="button"
          className="btn btn--quiet"
          onClick={() => {
            void signOut().then(() => setEmail(null));
          }}
        >
          Çıkış yap
        </button>
      </section>
    );
  }

  return (
    <section className="auth__card">
      <button
        type="button"
        className="btn btn--primary"
        disabled={busy}
        onClick={() => {
          setBusy(true);
          setError(null);
          signInWithGoogle("/gecmis").catch((caught: unknown) => {
            setError(
              caught instanceof Error
                ? caught.message
                : "Giriş başlatılamadı. Lütfen tekrar deneyin.",
            );
            setBusy(false);
          });
        }}
      >
        {busy ? "Google'a yönlendiriliyorsunuz…" : "Google ile giriş yap"}
      </button>

      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}

      <p className="auth__terms">
        Giriş yaparak <Link href="/kosullar">kullanım koşullarını</Link> ve{" "}
        <Link href="/gizlilik">gizlilik politikasını</Link> kabul etmiş
        olursunuz.
      </p>
    </section>
  );
}
