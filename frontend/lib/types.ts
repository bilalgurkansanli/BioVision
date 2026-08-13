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

export function classify(response: AnalyzeResponse): ResultKind {
  if (response.specialist_model !== null) return "measured";
  if (response.warning === "low_domain_confidence") return "unplaced";
  return "described";
}
