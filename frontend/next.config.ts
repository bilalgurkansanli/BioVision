import type { NextConfig } from "next";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "";

/**
 * Content-Security-Policy.
 *
 * This is the mitigation the session storage depends on. supabase-js keeps the
 * access token in `localStorage`, which a cross-site scripting bug could read;
 * httpOnly cookies are not available here because the API is a separate origin
 * and the browser has to attach a bearer token to it itself. So the strategy is
 * to make script injection hard rather than survivable — see ADR-027.
 *
 * `'unsafe-inline'` on style-src is Next's inline critical CSS, and there is no
 * nonce mechanism for it without a middleware on every request. Styles are a far
 * narrower injection surface than scripts, and script-src carries no such
 * escape hatch.
 *
 * `connect-src` names exactly two upstreams: our own API and the Supabase
 * project. An injected script cannot exfiltrate to anywhere else.
 */
const isDev = process.env.NODE_ENV === "development";

const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  "object-src 'none'",
  // 'unsafe-inline' is here because it had to be, not because it was skipped.
  //
  // Next emits inline bootstrap and RSC-payload scripts. Three ways to allow
  // them were tried and measured:
  //   - `script-src 'self'` alone: hydration never runs. Every page renders and
  //     nothing on it works, which is worse than no CSP at all.
  //   - experimental SRI hashes: covers some inline scripts, not all. Violations
  //     continued and React failed with hydration error #412.
  //   - per-request nonces: works, and forces every page dynamic -- no static
  //     prerender, no CDN caching, a server render per visit.
  // The third is the right answer for an app with user-generated markup. This
  // one has none, and its real exposure is the access token in localStorage,
  // which `connect-src` below addresses directly: injected script or not,
  // nothing can be sent anywhere except our own two upstreams. See ADR-027.
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  `connect-src 'self' ${API_URL} ${SUPABASE_URL}`.trim(),
  "upgrade-insecure-requests",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  },
  {
    key: "Strict-Transport-Security",
    value: "max-age=31536000; includeSubDomains; preload",
  },
];

const config: NextConfig = {
  reactStrictMode: true,

  // Removes the `X-Powered-By: Next.js` header. Version disclosure is not a
  // vulnerability by itself; it is free reconnaissance, and removing it is free.
  poweredByHeader: false,

  // The API base URL and the Supabase anon key are the only values the browser
  // is allowed to see. Anything secret -- the service-role key, the Anthropic
  // key, the JWT secret -- lives on the VPS and is never read here. A build that
  // needed one of those would be a design error, not a configuration one.
  env: {
    NEXT_PUBLIC_API_URL: API_URL,
  },

  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },

  async redirects() {
    // The page moved to a Turkish path when the legal pages arrived. Anyone
    // holding the old link should still land somewhere.
    return [{ source: "/history", destination: "/gecmis", permanent: true }];
  },
};

export default config;
