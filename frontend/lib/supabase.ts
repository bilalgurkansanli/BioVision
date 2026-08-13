"use client";

/**
 * The Supabase browser client.
 *
 * Only two values ever reach the browser: the project URL and the **anon** key.
 * Both are designed to be public — the anon key grants nothing on its own,
 * because every table is behind row-level security, and that is not an
 * assumption: `backend/scripts/rls_check.py` asserts it against a real Postgres.
 *
 * When the project is not configured the client is `null` rather than a stub
 * that throws on use, so the UI can offer the demo without sign-in instead of
 * failing at the first click.
 *
 * **On where the session lives.** supabase-js keeps it in `localStorage`, which
 * means a cross-site scripting bug would expose the access token. The
 * alternative — httpOnly cookies — cannot work here without a proxy, because the
 * API is a different origin and the browser must attach a bearer token to it
 * itself. The mitigation is therefore to make XSS hard rather than survivable: a
 * strict Content-Security-Policy (see `next.config.ts`) and short-lived tokens
 * with rotation left on. There is exactly one `dangerouslySetInnerHTML` in the
 * app -- the JSON-LD block in `layout.tsx` -- and it serialises a module-level
 * constant that no request can influence. Recorded in `docs/DECISIONS.md`
 * ADR-027 rather than left as an unexamined default.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const PROJECT_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const supabase: SupabaseClient | null =
  PROJECT_URL && ANON_KEY
    ? createClient(PROJECT_URL, ANON_KEY, {
        auth: {
          // PKCE rather than the implicit flow: the access token never appears
          // in a URL fragment, so it cannot leak through the address bar,
          // browser history, or a Referer header.
          flowType: "pkce",
          detectSessionInUrl: true,
          persistSession: true,
          autoRefreshToken: true,
        },
      })
    : null;

export const authConfigured = supabase !== null;

/** Where Google returns the user. Must be in the Supabase redirect allow list. */
export function callbackUrl(next?: string): string {
  const url = new URL("/auth/callback", window.location.origin);
  if (next) url.searchParams.set("next", next);
  return url.toString();
}

export async function signInWithGoogle(next?: string): Promise<void> {
  if (!supabase) throw new Error("Giriş bu ortamda yapılandırılmamış.");

  const { error } = await supabase.auth.signInWithOAuth({
    provider: "google",
    options: {
      redirectTo: callbackUrl(next),
      queryParams: { access_type: "offline", prompt: "consent" },
    },
  });
  if (error) throw error;
}

export async function signOut(): Promise<void> {
  await supabase?.auth.signOut();
}

/** The current access token, or `null` when signed out. */
export async function currentAccessToken(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token ?? null;
}

/** The signed-in user's email, for showing who is signed in.
 *
 * Reads the stored session rather than calling `getUser()`. `getUser()` asks the
 * server, so when the project is unreachable it hangs -- and a sign-in page that
 * waits on that renders "checking your session" forever. Found by pointing the
 * app at a Supabase that was not running. The stored session is enough to answer
 * "who is signed in"; anything that needs the server to confirm it will fail
 * loudly at that point instead.
 */
export async function currentEmail(): Promise<string | null> {
  if (!supabase) return null;
  const { data } = await supabase.auth.getSession();
  return data.session?.user.email ?? null;
}
