"use client";

/**
 * The Supabase browser client.
 *
 * Only two values ever reach the browser: the project URL and the **anon** key.
 * Both are designed to be public — the anon key grants nothing on its own,
 * because every table is behind row-level security. The service-role key, the
 * JWT secret, and the Anthropic key live on the VPS and are never referenced
 * from this directory.
 *
 * When the project is not configured the client is `null` rather than a stub
 * that throws on use, so the UI can offer the demo without sign-in instead of
 * failing at the first click.
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const supabase: SupabaseClient | null =
  URL && ANON_KEY ? createClient(URL, ANON_KEY) : null;

export const authConfigured = supabase !== null;

export async function signInWithGoogle(): Promise<void> {
  if (!supabase) throw new Error("Giriş yapılandırılmamış.");

  await supabase.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: `${window.location.origin}/history` },
  });
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
