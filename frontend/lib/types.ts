/**
 * The API contract, mirrored in TypeScript.
 *
 * These correspond 1:1 to the pydantic models in `backend/src/biovision/schemas/`.
 * The authoritative document is `docs/openapi.json`, which CI keeps in step with
 * the Python models; this file is checked against it by `lib/contract.test-d.ts`
 * so the two cannot drift silently.
 */

// Mirrors backend DamageType. Alphabetical, and that order is load-bearing: the
// model emits integer ids against it. See ADR-026 for why these seven and not
// CarDD's six.
export type DamageType =
  | "dent"
  | "glass_shatter"
  | "lamp_broken"
  | "missing_part"
  | "punctured"
  | "scratch"
  | "torn";

export type Severity = "minor" | "moderate" | "severe";

export type WarningCode =
  | "no_specialist_model_for_domain"
  | "low_domain_confidence"
  | "vlm_unavailable"
  | "duplicate_submission";

export type ErrorCode =
  | "file_too_large"
  | "unsupported_media_type"
  | "animated_image"
  | "corrupt_image"
  | "image_too_small"
  | "out_of_distribution"
  | "unauthenticated"
  | "not_found"
  | "rate_limited"
  | "not_implemented"
  | "service_degraded";

export interface Finding {
  type: DamageType;
  score: number;
  /** [x1, y1, x2, y2] in pixels of the stored (resized) image. */
  bbox: [number, number, number, number];
  area_ratio: number;
  severity: Severity;
  /** Always false. Severity is an uncalibrated heuristic; the UI must say so. */
  severity_calibrated: false;
  /**
   * Measured recall for this damage class, or null where unmeasured. `score` is
   * how sure the model is about this box; this is how much the class tends to be
   * missed. A lone finding on a wrecked car can mean light damage — or a class
   * with recall 0.25. The UI has to show both or it misleads.
   */
  class_recall: number | null;
  /** False where the class misses more than it finds (recall < 0.40). */
  class_reliable: boolean | null;
}

export interface Integrity {
  exif_datetime: string | null;
  /** Presence only. Coordinates are never stored or returned. */
  exif_gps_present: boolean;
  device: string | null;
  duplicate_of: string | null;
}

export interface Privacy {
  faces_blurred: number;
  plates_blurred: number;
  /** `null` means that class was NOT redacted — a different claim from zero found. */
  face_detector: string | null;
  plate_detector: string | null;
}

export interface TimingMs {
  preprocess: number | null;
  gate: number | null;
  router: number | null;
  specialist: number | null;
  vlm: number | null;
  total: number;
}

export interface AnalyzeResponse {
  request_id: string;
  domain: string;
  domain_confidence: number;
  /** Whether the confidence itself was temperature-scaled. */
  domain_confidence_calibrated: boolean;
  /** `null` means no trained model exists for this domain. */
  specialist_model: string | null;
  /**
   * How bad the damage is over the whole photograph, judged separately from the
   * findings — a total is not a sum of parts. Zero-shot and uncalibrated: 64.5%
   * over 248 held-out images, `severe` recalled at 51%. The UI must say so.
   */
  overall_severity: Severity | null;
  overall_severity_confidence: number | null;
  /** Always false. No fitted temperature stands behind these bands. */
  overall_severity_calibrated: false;
  /** Whether this *result* is a calibrated measurement. */
  calibrated: boolean;
  findings: Finding[];
  vlm_description: string | null;
  warning: WarningCode | null;
  integrity: Integrity;
  privacy: Privacy;
  timing_ms: TimingMs;
}

export interface ApiErrorBody {
  error: {
    code: ErrorCode;
    message: string;
    request_id: string | null;
  };
}

export interface DomainInfo {
  key: string;
  label: string;
  has_specialist: boolean;
  specialist_model: string | null;
  calibrated: boolean;
}

export interface DomainsResponse {
  domains: DomainInfo[];
  count: number;
  with_specialist: number;
}

export interface HistoryItem {
  id: string;
  created_at: string;
  domain: string;
  domain_confidence: number;
  specialist_model: string | null;
  calibrated: boolean;
  findings: Finding[];
  vlm_description: string | null;
  warning: WarningCode | null;
}

export interface RequestHistoryResponse {
  items: HistoryItem[];
  count: number;
  retention_days: number;
}

/**
 * Which of the three shapes a response is.
 *
 * The UI branches on this rather than on `specialist_model !== null` scattered
 * across components: one place decides what kind of answer this is, so a new
 * shape cannot be half-handled.
 */
export type ResultKind = "measured" | "described" | "unplaced";

/**
 * Takes the two fields the decision actually depends on rather than a whole
 * response, so a stored `HistoryItem` goes through the same function as a live
 * `AnalyzeResponse`. The history list used to re-implement this ternary, which
 * is exactly the "half-handled new shape" this function exists to prevent.
 */
export function classify(
  response: Pick<AnalyzeResponse, "specialist_model" | "warning">,
): ResultKind {
  if (response.specialist_model !== null) return "measured";
  if (response.warning === "low_domain_confidence") return "unplaced";
  return "described";
}

// --- claim outcome -------------------------------------------------------
//
// These carry no `calibrated` flag because there is nothing to calibrate: every
// field is a regulation or arithmetic over one. A rule is not more or less
// accurate — it either cites its article or it does not ship.

export interface ThresholdLine {
  key: "agir_hasar" | "tam_hasar";
  label_tr: string;
  ratio: number;
  amount_try: string;
  source: string;
  basis_tr: string;
  /** Tam hasar needs an expert finding as well as the ratio; the two are cumulative. */
  requires_expert_finding: boolean;
}

export interface WriteOffLines {
  vehicle_value_try: string;
  value_source: string;
  value_basis_tr: string;
  value_basis_source: string;
  lines: ThresholdLine[];
  corrections: { text_tr: string; source: string }[];
  determined_by_tr: string;
  determined_by_source: string;
}

export interface PremiumImpact {
  from_step: number;
  to_step: number;
  relative_increase: number;
  /** Five from the top step, not one — Geçici m.11(14). */
  recovery_years: number;
  /** Always true. Ek-2 caps the premium; it does not set it. */
  is_ceiling: true;
  source: string;
}

export interface VehicleTypeOption {
  brand_code: number;
  type_code: number;
  brand_name: string;
  type_name: string;
}

export interface Valuation {
  vehicle: VehicleTypeOption;
  model_year: number;
  amount_try: string;
  source_label: string;
  source_url: string;
  revision: string;
  fetched_at: string;
  /** Travels with the figure: list averages, no mileage or condition adjustment. */
  caveat_tr: string;
  /** Always false. This is a list value, not an appraisal of this vehicle. */
  is_individual_appraisal: false;
}

export interface ValueListMeta {
  available: boolean;
  revision: string | null;
  month_label: string | null;
  oldest_model_year: number | null;
  newest_model_year: number | null;
  fetched_at: string | null;
  caveat_tr: string | null;
  /** Set when the mirror is missing, so the form can explain rather than just ask. */
  unavailable_reason_tr: string | null;
}
