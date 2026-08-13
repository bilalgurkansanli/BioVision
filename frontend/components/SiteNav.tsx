"use client";

/**
 * The header nav, which has to answer one question honestly: is anyone signed in?
 *
 * It renders the signed-out shape first and corrects itself once the session is
 * known, rather than hiding behind a spinner. The nav is not worth a layout
 * shift, and showing "Giriş yap" for a moment to someone already signed in is a
 * smaller wrong than showing nothing at all.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { authConfigured, currentEmail, supabase } from "@/lib/supabase";

export function SiteNav() {
  const pathname = usePathname();
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!supabase) return;

    void currentEmail().then(setEmail).catch(() => setEmail(null));

    const { data } = supabase.auth.onAuthStateChange((_event, session) => {
      setEmail(session?.user.email ?? null);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  const isCurrent = (href: string) => (pathname === href ? "page" : undefined);

  return (
    <nav className="nav" aria-label="Ana menü">
      <Link href="/" className="nav__brand" aria-current={isCurrent("/")}>
        BioPolicy
      </Link>

      {authConfigured ? (
        email ? (
          <Link href="/gecmis" aria-current={isCurrent("/gecmis")}>
            Geçmişim
          </Link>
        ) : (
          <Link href="/giris" aria-current={isCurrent("/giris")}>
            Giriş yap
          </Link>
        )
      ) : null}
    </nav>
  );
}
