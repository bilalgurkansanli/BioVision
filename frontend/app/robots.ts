import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        // Nothing under these can be useful in an index, and `/gecmis` would be
        // an empty page to a crawler anyway -- it needs a session to show
        // anything. Excluding them is about crawl budget, not secrecy: the
        // privacy of history is enforced by row-level security, not robots.txt.
        disallow: ["/giris", "/gecmis", "/auth/"],
      },
    ],
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
