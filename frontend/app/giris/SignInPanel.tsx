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

  if (!authConfigured) {
    return (
      <section className="notice notice--unplaced">
        <h2 className="notice__title">Bu ortamda giriş yapılandırılmamış</h2>
        <p>
          Kimlik sağlayıcı bu kuruluma bağlı değil. Bunu bir hata olarak
          göstermek yerine söylüyoruz: analiz çalışıyor, giriş çalışmıyor.
        </p>
        <p style={{ marginTop: "0.75rem" }}>
          <Link href="/">Analize dön</Link>
        </p>
      </section>
    );
  }

  if (!ready) {
    return <p className="dropzone__hint">Oturum kontrol ediliyor…</p>;
  }

  if (email) {
    return (
      <section className="dropzone">
        <p className="result__lead">
          <strong>{email}</strong> olarak giriş yaptınız.
        </p>
        <p className="dropzone__hint">
          <Link href="/gecmis">Geçmişinize gidin</Link>
        </p>
        <p style={{ marginTop: "1rem" }}>
          <button
            type="button"
            className="history__delete"
            onClick={() => {
              void signOut().then(() => setEmail(null));
            }}
          >
            Çıkış yap
          </button>
        </p>
      </section>
    );
  }

  return (
    <section className="dropzone">
      <button
        type="button"
        className="dropzone__button"
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

      <p className="dropzone__privacy">
        Giriş yaparak{" "}
        <Link href="/kosullar">kullanım koşullarını</Link> ve{" "}
        <Link href="/gizlilik">gizlilik politikasını</Link> kabul etmiş
        olursunuz.
      </p>

      {error ? (
        <p className="alert" style={{ marginTop: "1rem" }} role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
