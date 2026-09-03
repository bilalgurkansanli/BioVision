/**
 * The API contract, mirrored in TypeScript.
 *
 * These correspond 1:1 to the pydantic models in `backend/src/biovision/schemas/`.
 * The authoritative document is `docs/openapi.json`, which CI keeps in step with
 * the Python models; this file is checked against it by `lib/contract.test-d.ts`
 * so the two cannot drift silently.
 */

// Mirrors backend DamageType. Alphabetical, and that order is load-bearing: the
// model emits integer ids against it. See ADR-026 for why these seven
// and not CarDD's six.
export type DamageType =
  | "dent"
  | "glass_shatter"
  | "lamp_broken"
  | "missing_part"
  | "punctured"
  | "scratch"
  | "torn";

/**
 * `none` is reachable only as a whole-photograph band, never on a finding — a
 * finding IS damage, and the API rejects the combination. It exists because the
 * band was a three-way choice with nowhere to put an intact car, so a showroom
 * photograph came back as "hafif".
 */
export type Severity = "none" | "minor" | "moderate" | "severe";

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

/**
 * The damaged area as one region — and, crucially, what it is a fraction OF.
 *
 * A user asked "42% of what?" and the honest answer was "of the photograph",
 * which made the number a measure of where they stood rather than of the damage.
 * `area_ratio_vehicle` is the fix and it is nullable on purpose: where no vehicle
 * could be located the UI must say so rather than silently showing the frame
 * figure under the same label.
 */
/** A third across the vehicle **as this photograph frames it** — not front/rear.
 * Side-on these are roughly bonnet, doors and boot; head-on they are the left,
 * middle and right of one bumper, and which you are looking at is a fact about
 * the camera rather than about the car. */
export type Band = "left" | "middle" | "right";

/** Upper or lower half of the vehicle. This one survives the viewpoint problem,
 * because gravity is in the photograph. */
export type Level = "upper" | "lower";

export interface ZoneShare {
  band: Band;
  level: Level;
  /** Damaged pixels over the VEHICLE's pixels in this zone, not the rectangle's. */
  share: number;
}

/**
 * Where the damage sits on the vehicle — and the claim it refuses to make.
 *
 * It never says "left front wing". A photograph does not say which side of a car
 * you are standing on, and resolving that needs the vehicle's orientation, which
 * needs a model nobody here has measured. So these are positions in the frame,
 * relative to the car's own footprint.
 */
export interface DamagePosition {
  zones: ZoneShare[];
  dominant: ZoneShare;
  /** Usually means the detector smeared rather than that the car is uniformly
   * wrecked, so it is said out loud instead of left to be noticed. */
  spans_whole_vehicle: boolean;
}

/**
 * Whether the vehicle fits inside the photograph.
 *
 * This is the completeness measurement and `vehicle_frame_share` is not: that
 * one is about distance. A car filling 84% of the frame while touching all four
 * edges is a photograph of a fragment.
 */
export interface FrameClipping {
  complete: boolean;
  /** Some of "top" | "bottom" | "left" | "right". Empty when complete. */
  edges: string[];
}

export interface DamageRegion {
  /** Framing-sensitive. Retains a median 0.23 of its value under a 100% pad. */
  area_ratio_image: number;
  /** Framing-stable (0.92 under the same pad), or null if no vehicle was found. */
  area_ratio_vehicle: number | null;
  /** How much of the frame the car fills. Near 1.0, the two ratios nearly agree. */
  vehicle_frame_share: number | null;
  /** Detections that contributed area — normally more than `findings`. */
  instances: number;
  /** Which edges the car runs past, or null if it was not located. */
  clipped: FrameClipping | null;
  /** Where on the car the damage is, or null if it was not located. */
  position: DamagePosition | null;
  /** Lower than the findings floor: area and identification are different questions. */
  confidence_floor: number;
  /** Always false. A measured pixel union from an uncalibrated segmenter. */
  calibrated: false;
}

export interface BandOutcome {
  band: Severity;
  count: number;
  share: number;
}

/**
 * What the severity band turned out to MEAN, counted on 248 held-out images.
 *
 * The confusion matrix read down its columns instead of across its rows: not "of
 * the severe cars, how many did we catch" but "of the cars we called severe, how
 * many were". The second is the question a reader holding a band actually has.
 */
export interface SeverityReliability {
  predicted: Severity;
  support: number;
  outcomes: BandOutcome[];
  correct_share: number;
  /** How often the truth was WORSE. The estimator under-calls, so this is the costly side. */
  worse_share: number;
  evaluation_set: string;
  evaluation_note_tr: string;
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
  /** Present whenever a band is. The measured frequency behind the word. */
  overall_severity_reliability: SeverityReliability | null;
  /** Whether this *result* is a calibrated measurement. */
  calibrated: boolean;
  findings: Finding[];
  /** Null when no specialist ran or nothing was detected. */
  damage_region: DamageRegion | null;
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

/**
 * Something that follows from a determination, and whether it can be undone.
 *
 * `irreversible` and `line_specific` decide prominence, not wording. Crossing
 * 60% produces six of these and five are procedural; rendering all six under the
 * figure buried the one that is permanent — the record ends the değer kaybı
 * claim outright.
 */
export interface Consequence {
  key: string;
  text_tr: string;
  source: string;
  /** Cannot be undone. Never behind a disclosure. */
  irreversible: boolean;
  /** This IS the meaning of the line it hangs under, not something shared. */
  line_specific: boolean;
}

export interface ThresholdLine {
  key: "agir_hasar" | "tam_hasar";
  label_tr: string;
  ratio: number;
  amount_try: string;
  source: string;
  basis_tr: string;
  /**
   * Tam hasar needs an expert finding as well as the ratio; the two are
   * cumulative. Ağır hasar does NOT — m.5(1) is a bare 60% threshold, and the
   * two rules are not parallel.
   */
  requires_expert_finding: boolean;
  /**
   * What crossing THIS line does beyond the payment. The one that matters most
   * is not about money: at 60% the vehicle takes a record that permanently
   * forecloses değer kaybı.
   */
  consequences: Consequence[];
}

export interface WriteOffLines {
  vehicle_value_try: string;
  value_source: string;
  value_basis_tr: string;
  value_basis_source: string;
  /**
   * What this product says about its own denominator: the TSB list is a sector
   * service, and where a policy names no concrete reference the regulation
   * points at the eksper raporu's rayiç instead. The figure must not be shown
   * without it.
   */
  value_reference_default_tr: string;
  value_reference_default_source: string;
  lines: ThresholdLine[];
  /** What holds while the vehicle stays under both lines — the protections. */
  below_threshold_tr: Consequence[];
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

/**
 * One branch a claim can take. Carries an exact amount OR an interval, never
 * both — a point printed beside a range is read as the answer.
 */
export interface PayoutScenario {
  key: "tam_hasar" | "onarim";
  label_tr: string;
  amount_try: string | null;
  lower_try: string | null;
  upper_try: string | null;
  basis_tr: string;
  source: string;
  /** What would close the figure. Every entry needs a person or a document. */
  missing_tr: string[];
  /** Always false. Every figure here is a subtraction from a listed value. */
  is_estimate: false;
}

/**
 * The kasko premium ratio. Deliberately a different type from `PremiumImpact`,
 * because the two have different standing: trafik is a national table with an
 * article, this is the claimant's own policy or one named insurer's clause.
 */
export interface KaskoImpact {
  from_discount: number;
  to_discount: number;
  relative_increase: number;
  basis_tr: string;
  source: string;
  /** Always false. Kasko GŞ C.11 leaves the ladder to özel şartlar. */
  nationally_regulated: false;
  insurer: string | null;
  /** 1 means this is one insurer's clause, not a market rule. */
  sample_size: number | null;
  from_kademe: number | null;
  to_kademe: number | null;
  disclaimer_tr: string | null;
}

/** The ceiling on what the OTHER party's compulsory policy can pay for property. */
export interface TrafficLimit {
  property_per_vehicle_try: string;
  property_per_accident_try: string;
  in_force_from: string;
  source: string;
  official_gazette: string;
  applies_on_tr: string;
  note_tr: string;
  /** Value minus the cap, where the value exceeds it. A subtraction, not a forecast. */
  shortfall_try: string | null;
}

export interface CriticalPart {
  index: number;
  name_tr: string;
  visible_in_photo: boolean;
  ask_user: boolean;
  question_tr: string | null;
}

/** One answer the claimant could give, and the figure it would close. */
export interface OpenQuestion {
  key: string;
  question_tr: string;
  unlocks_tr: string;
  from_document: boolean;
}

export interface Gap {
  key: string;
  question_tr: string;
  reason_tr: string;
}

/** Everything the claim side can say about one photographed vehicle. */
export interface Assessment {
  valuation: Valuation | null;
  value_source: string;
  write_off: WriteOffLines | null;
  payout: PayoutScenario[];
  severity_reliability: SeverityReliability | null;
  /** How the claim runs whichever side of the lines it lands on. */
  procedure: Consequence[];
  traffic_limit: TrafficLimit | null;
  traffic_premium: PremiumImpact | null;
  kasko_premium: KaskoImpact | null;
  critical_part_questions: CriticalPart[];
  open_questions: OpenQuestion[];
  gaps: Gap[];
}

export interface AssessmentRequest {
  vehicle_value_try?: string;
  model_year?: number;
  brand_code?: number;
  type_code?: number;
  overall_severity?: Severity;
  deductible_try?: string;
  salvage_retained?: boolean;
  traffic_step?: number;
  traffic_injury?: boolean;
  kasko_kademe?: number;
  kasko_current_discount?: number;
  kasko_claims_this_period?: number;
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

/**
 * Whether the photographs of one claim told the same story.
 *
 * A confidence signal the model cannot produce about itself: a detector's score
 * says how sure it is about one box, and the severity band is uncalibrated.
 * Measured at 224 `all`, 23 `partial`, 3 `none` over 250 claims.
 */
export type PhotoAgreement = "all" | "partial" | "none";

export interface ClaimSummary {
  photo_count: number;
  photos_with_findings: number;
  agreement: PhotoAgreement;
  /** The union across photographs — a wider VIEW of the damage, not more damage. */
  damage_types: DamageType[];
  /** The WORST band across photographs, not the average. Null if none produced one. */
  overall_severity: Severity | null;
  /** Always false. A maximum of uncalibrated bands is not calibrated. */
  overall_severity_calibrated: boolean;
}

/** Per-photograph results kept in full: an assessor needs to know WHICH photograph. */
export interface ClaimResponse {
  summary: ClaimSummary;
  photos: AnalyzeResponse[];
}
