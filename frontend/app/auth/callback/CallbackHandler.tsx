"use client";

/**
 * Where Google returns the user, and where the PKCE code becomes a session.
 *
 * The client is configured with `detectSessionInUrl`, so supabase-js performs
 * the code exchange itself as soon as it loads on a URL carrying `?code=`. This
 * component's job is to wait for that to finish and then say what happened —
 * because the two failure modes here are both silent by default:
 *
 * * the user declines consent at Google, and comes back with `?error=` and no
 *   session. Without handling, the page waits forever on a session that will
 *   never arrive.
 * * the redirect URL is missing from Supabase's allow list, which is the single
 *   most common misconfiguration and produces a callback with no code at all.
 *
 * Both are reported here with the specific cause, rather than a spinner.
 */

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { supabase } from "@/lib/supabase";

type State =
  | { kind: "working" }
  | { kind: "done" }
  | { kind: "failed"; title: string; detail: string };

/** Only same-site paths, so `?next=` cannot be used as an open redirect. */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/gecmis";
  return raw;
}

export function CallbackHandler() {
  const router = useRouter();
  const params = useSearchParams();
  const [state, setState] = useState<State>({ kind: "working" });

  useEffect(() => {
    const next = safeNext(params.get("next"));

    const providerError = params.get("error_description") ?? params.get("error");
    if (providerError) {
      setState({
        kind: "failed",
        title: "Giriş tamamlanmadı",
        detail:
          params.get("error") === "access_denied"
            ? "Google üzerinde izin verilmedi. Giriş yapmadan da analiz yapabilirsiniz."
            : providerError,
      });
      return;
    }

    if (!supabase) {
      setState({
        kind: "failed",
        title: "Giriş bu ortamda yapılandırılmamış",
        detail: "Kimlik sağlayıcı bu kuruluma bağlı değil.",
      });
      return;
    }

    let cancelled = false;

    // supabase-js exchanges the code on load; onAuthStateChange is how we learn
    // it finished. Polling getSession would race with the exchange.
    const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
      if (cancelled || !session) return;
      setState({ kind: "done" });
      router.replace(next);
    });

    void supabase.auth.getSession().then(({ data }) => {
      if (cancelled) return;
      if (data.session) {
        setState({ kind: "done" });
        router.replace(next);
      }
    });

    // If nothing has arrived by now, the exchange is not going to happen. The
    // usual cause is a redirect URL that Supabase does not recognise.
    const timeout = window.setTimeout(() => {
      if (cancelled) return;
      setState((current) =>
        current.kind === "working"
          ? {
              kind: "failed",
              title: "Oturum kurulamadı",
              detail:
                "Google'dan dönüş alındı ama oturum açılamadı. Bu genellikle " +
                "yönlendirme adresinin sunucuda tanımlı olmamasından kaynaklanır.",
            }
          : current,
      );
    }, 10_000);

    return () => {
      cancelled = true;
      window.clearTimeout(timeout);
      subscription.subscription.unsubscribe();
    };
  }, [params, router]);

  if (state.kind === "failed") {
    return (
      <section className="notice notice--unplaced">
        <h1 className="notice__title">{state.title}</h1>
        <p>{state.detail}</p>
        <p style={{ marginTop: "0.75rem" }}>
          <Link href="/giris">Tekrar deneyin</Link> ·{" "}
          <Link href="/analiz">Analize dön</Link>
        </p>
      </section>
    );
  }

  return <p>Giriş tamamlanıyor…</p>;
}
