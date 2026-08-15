"use client";

/**
 * The header nav, which has to answer one question honestly: who is signed in?
 *
 * It renders the signed-out shape first and corrects itself once the session is
 * known, rather than hiding behind a spinner. The nav is not worth a layout
 * shift, and showing "Giriş yap" for a moment to someone already signed in is a
 * smaller wrong than showing nothing at all.
 *
 * The address is shown in full rather than abbreviated to an initial or a
 * first name. On a site that stores analyses against an account, "which account
 * am I looking at" has one correct answer and it is the whole address —
 * particularly for anyone with more than one Google account signed in, where a
 * single letter avatar is exactly as ambiguous as no answer.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { authConfigured, currentEmail, signOut, supabase } from "@/lib/supabase";

export function SiteNav() {
  const pathname = usePathname();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!supabase) return;

    void currentEmail()
      .then(setEmail)
      .catch(() => setEmail(null));

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user.email ?? null);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  const isCurrent = (href: string) => (pathname === href ? "page" : undefined);

  return (
    <nav className="nav" aria-label="Ana menü">
      <div className="nav__inner">
        <Link href="/" className="nav__brand" aria-current={isCurrent("/")}>
          {/* A filled mark rather than a tinted letter: the accent is only
              legible as a fill, so a yellow half-wordmark would disappear the
              moment the light theme applies. */}
          <span className="nav__mark" aria-hidden="true" />
          BioVision
        </Link>

        {authConfigured && email ? (
          <>
            <Link
              href="/gecmis"
              className="nav__link"
              aria-current={isCurrent("/gecmis")}
            >
              Geçmişim
            </Link>

            <span className="nav__account" title={`${email} olarak giriş yapıldı`}>
              <span className="nav__account-dot" aria-hidden="true" />
              <span className="nav__account-email">{email}</span>
            </span>

            <button
              type="button"
              className="nav__signout"
              onClick={() => {
                void signOut().then(() => setEmail(null));
              }}
            >
              Çıkış
            </button>
          </>
        ) : authConfigured ? (
          <Link href="/giris" className="nav__link" aria-current={isCurrent("/giris")}>
            Giriş yap
          </Link>
        ) : null}

        {/* The one action worth promoting from every page. It is hidden on the
            analyser itself, where it would only link to the current page. */}
        {pathname !== "/analiz" && (
          <Link href="/analiz" className="nav__cta">
            Analiz et
          </Link>
        )}
      </div>
    </nav>
  );
}
