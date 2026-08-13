import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

/**
 * Only the pages worth ranking.
 *
 * `/giris`, `/gecmis` and `/auth/callback` are deliberately absent: a sign-in
 * form has nothing to rank for, a personal history page is private by
 * definition, and an OAuth callback is machinery. Listing them would spend
 * crawl budget on pages that can only dilute the ones that matter.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date("2026-08-14");

  return [
    { url: SITE_URL, lastModified: now, changeFrequency: "weekly", priority: 1 },
    {
      url: `${SITE_URL}/gizlilik`,
      lastModified: now,
      changeFrequency: "yearly",
      priority: 0.5,
    },
    {
      url: `${SITE_URL}/kosullar`,
      lastModified: now,
      changeFrequency: "yearly",
      priority: 0.5,
    },
    {
      url: `${SITE_URL}/lisans`,
      lastModified: now,
      changeFrequency: "yearly",
      priority: 0.3,
    },
  ];
}
