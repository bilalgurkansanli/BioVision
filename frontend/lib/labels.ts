/**
 * Turkish labels for the API's stable identifiers.
 *
 * These lived inside ResultCard, which meant the history list rendered the raw
 * key: a stored analysis showed "vehicle" where the result card for the same
 * analysis showed "Araç". Anything that displays a domain or a damage type
 * reads them from here.
 *
 * `/v1/domains` returns its own `label` for each domain and that one wins where
 * it is available — it comes from `domains.yaml`, so a domain added there needs
 * no frontend change. This map covers the places that only have the key: the
 * analyse response, and stored history rows.
 */

import type { DamageType, Severity } from "./types";

const DOMAIN: Record<string, string> = {
  vehicle: "Araç",
  building: "Bina",
  phone_screen: "Telefon ekranı",
  other: "Diğer",
  unknown: "Belirlenemedi",
};

const DAMAGE: Record<DamageType, string> = {
  dent: "göçük",
  glass_shatter: "cam kırığı",
  lamp_broken: "far kırığı",
  missing_part: "eksik parça",
  punctured: "delik",
  scratch: "çizik",
  torn: "yırtık",
};

const SEVERITY: Record<Severity, string> = {
  // Not "yok". The band says the photograph shows no damage, which is a
  // different claim from the car having none -- a panel out of frame is still a
  // panel nobody looked at.
  none: "hasarsız görünüyor",
  minor: "hafif",
  moderate: "orta",
  severe: "ağır",
};

/**
 * Unknown keys fall through to the key itself rather than to a placeholder. A
 * domain added to `domains.yaml` before this map catches up should read
 * `phone_screen` — ugly, but true — rather than "Bilinmeyen", which would be a
 * claim that the system failed to place it.
 */
export const domainLabel = (key: string): string => DOMAIN[key] ?? key;

export const damageLabel = (type: DamageType): string => DAMAGE[type] ?? type;

export const severityLabel = (severity: Severity): string => SEVERITY[severity];
