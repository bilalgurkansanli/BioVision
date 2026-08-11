import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,

  // The API base URL and the Supabase anon key are the only values the browser
  // is allowed to see. Anything secret -- the service-role key, the Anthropic
  // key, the JWT secret -- lives on the VPS and is never read here. A build that
  // needed one of those would be a design error, not a configuration one.
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};

export default config;
