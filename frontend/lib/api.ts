/**
 * The typed API client.
 *
 * Error handling is the substance here. The API returns one envelope for every
 * failure, and each code means something specific the user can act on — so the
 * client turns codes into sentences rather than surfacing "Request failed with
 * status 422", which tells a user nothing.
 */

import type {
  AnalyzeResponse,
  ApiErrorBody,
  Assessment,
  AssessmentRequest,
  ClaimResponse,
  CorrectionAccepted,
  CorrectionRequest,
  DomainsResponse,
  ErrorCode,
  PremiumImpact,
  RequestHistoryResponse,
  Valuation,
  ValueListMeta,
  VehicleTypeOption,
  WriteOffLines,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Human sentences, in Turkish, for every documented failure. */
const MESSAGES: Record<ErrorCode, string> = {
  file_too_large: "Fotoğraf 10 MB sınırını aşıyor. Daha küçük bir dosya deneyin.",
  unsupported_media_type:
    "Bu dosya türü desteklenmiyor. JPEG, PNG, WebP veya HEIC yükleyin.",
  animated_image: "Hareketli görseller desteklenmiyor. Sabit bir fotoğraf yükleyin.",
  corrupt_image: "Dosya okunamadı. Eksik veya bozuk olabilir.",
  image_too_small:
    "Fotoğraf çok küçük. Kısa kenarı en az 200 piksel olmalı.",
  out_of_distribution:
    "Bu bir hasar veya nesne fotoğrafına benzemiyor. Hasarlı parçanın fotoğrafını yükleyin.",
  unauthenticated: "Bu işlem için giriş yapmanız gerekiyor.",
  not_found: "Böyle bir analiz bulunamadı.",
  rate_limited: "Günlük istek sınırına ulaştınız. Yarın tekrar deneyin.",
  not_implemented: "Bu özellik henüz hazır değil.",
  service_degraded:
    "Açıklama bütçesi bu ay için doldu. Uzman modeli olan alanlar etkilenmedi.",
};

export class ApiError extends Error {
  constructor(
    readonly code: ErrorCode | "network" | "unknown",
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | null = null;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    // A non-JSON body means the proxy or the platform answered, not the API.
  }

  const code = body?.error?.code;
  if (code && code in MESSAGES) {
    // Prefer our own sentence over the server's: the API writes for developers,
    // this writes for the person holding the phone.
    return new ApiError(code, MESSAGES[code], response.status);
  }

  return new ApiError(
    "unknown",
    body?.error?.message ?? `Beklenmeyen bir hata oluştu (${response.status}).`,
    response.status,
  );
}

function authHeaders(accessToken?: string): HeadersInit {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

export async function analyze(
  file: File,
  options: { accessToken?: string; language?: string } = {},
): Promise<AnalyzeResponse> {
  const form = new FormData();
  form.append("image", file);

  let response: Response;
  try {
    response = await fetch(`${API_URL}/v1/analyze`, {
      method: "POST",
      body: form,
      headers: {
        ...authHeaders(options.accessToken),
        "Accept-Language": options.language ?? "tr",
      },
    });
  } catch {
    throw new ApiError("network", "Sunucuya ulaşılamadı. Bağlantınızı kontrol edin.");
  }

  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as AnalyzeResponse;
}

/**
 * Several photographs of one vehicle, analysed as a single claim.
 *
 * Measured before it was built: over 250 real multi-photograph claims the union
 * across a claim's photographs surfaces 2.04 damage types against 1.57 from any
 * single one, and the photographs disagree in 9% of claims. README 7.12.
 *
 * Counts as one request against the daily quota, not one per photograph --
 * charging per photograph would make photographing the whole car the expensive
 * choice.
 */
export async function analyzeClaim(
  files: File[],
  options: { accessToken?: string; language?: string } = {},
): Promise<ClaimResponse> {
  const form = new FormData();
  for (const file of files) form.append("images", file);

  let response: Response;
  try {
    response = await fetch(`${API_URL}/v1/claims/photos`, {
      method: "POST",
      body: form,
      headers: {
        ...authHeaders(options.accessToken),
        "Accept-Language": options.language ?? "tr",
      },
    });
  } catch {
    throw new ApiError("network", "Sunucuya ulaşılamadı. Bağlantınızı kontrol edin.");
  }

  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as ClaimResponse;
}

export async function fetchDomains(): Promise<DomainsResponse> {
  const response = await fetch(`${API_URL}/v1/domains`, { cache: "no-store" });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as DomainsResponse;
}

export async function fetchHistory(accessToken: string): Promise<RequestHistoryResponse> {
  const response = await fetch(`${API_URL}/v1/requests`, {
    headers: authHeaders(accessToken),
    cache: "no-store",
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as RequestHistoryResponse;
}

/**
 * Tell the system what it got wrong about one analysis.
 *
 * Requires a token, and that is a limitation rather than a preference: anonymous
 * analyses are never stored, so there is no row to attach a correction to and no
 * photograph it could be about.
 */
export async function fileCorrection(
  analysisId: string,
  correction: CorrectionRequest,
  accessToken: string,
): Promise<CorrectionAccepted> {
  const response = await fetch(`${API_URL}/v1/requests/${analysisId}/corrections`, {
    method: "POST",
    headers: { ...authHeaders(accessToken), "Content-Type": "application/json" },
    body: JSON.stringify(correction),
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as CorrectionAccepted;
}

export async function deleteAnalysis(id: string, accessToken: string): Promise<void> {
  const response = await fetch(`${API_URL}/v1/requests/${id}`, {
    method: "DELETE",
    headers: authHeaders(accessToken),
  });
  if (!response.ok) throw await toApiError(response);
}

export async function deleteAllAnalyses(accessToken: string): Promise<number> {
  const response = await fetch(`${API_URL}/v1/requests`, {
    method: "DELETE",
    headers: authHeaders(accessToken),
  });
  if (!response.ok) throw await toApiError(response);
  const body = (await response.json()) as { deleted: number };
  return body.deleted;
}

/**
 * Where the write-off lines fall for one vehicle.
 *
 * The value is a string rather than a number all the way through: these are
 * money, the backend computes them as Decimal, and a JSON round-trip through a
 * JS float is exactly how a threshold arrives one lira off.
 */
export async function fetchWriteOffLines(
  vehicleValueTry: string,
  valueSource = "kullanıcı girdisi",
): Promise<WriteOffLines> {
  const query = new URLSearchParams({
    vehicle_value_try: vehicleValueTry,
    value_source: valueSource,
  });
  const response = await fetch(`${API_URL}/v1/claims/write-off-lines?${query}`, {
    cache: "no-store",
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as WriteOffLines;
}

/**
 * The whole claim picture for one photographed vehicle.
 *
 * One request rather than four, because the relationships between the figures
 * are the product: a payout means nothing without the value it subtracts from,
 * and a severity band misleads without the frequency behind it. Every field of
 * the body is optional and each one closes a different figure — a request with
 * nothing in it still returns the rule sheet and the list of questions.
 */
export async function fetchAssessment(body: AssessmentRequest): Promise<Assessment> {
  const response = await fetch(`${API_URL}/v1/claims/assessment`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    // Undefined keys would serialise as absent anyway, but stripping them keeps
    // the request readable in the network tab, which is where a "why is this
    // field null" question gets answered.
    body: JSON.stringify(
      Object.fromEntries(Object.entries(body).filter(([, value]) => value !== undefined)),
    ),
    cache: "no-store",
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as Assessment;
}

/** What one claim payment does to a trafik sigortası step. */
export async function fetchPremiumImpact(
  currentStep: number,
  injury = false,
): Promise<PremiumImpact> {
  const query = new URLSearchParams({
    current_step: String(currentStep),
    injury: String(injury),
  });
  const response = await fetch(`${API_URL}/v1/claims/premium-impact?${query}`, {
    cache: "no-store",
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as PremiumImpact;
}

/** Which TSB revision is mirrored, and what it covers. Never throws on absence. */
export async function fetchValueListMeta(): Promise<ValueListMeta> {
  const response = await fetch(`${API_URL}/v1/claims/vehicle/list`, { cache: "no-store" });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as ValueListMeta;
}

export async function fetchVehicleYears(): Promise<number[]> {
  const response = await fetch(`${API_URL}/v1/claims/vehicle/years`, { cache: "no-store" });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as number[];
}

export async function fetchVehicleBrands(modelYear: number): Promise<string[]> {
  const query = new URLSearchParams({ model_year: String(modelYear) });
  const response = await fetch(`${API_URL}/v1/claims/vehicle/brands?${query}`, {
    cache: "no-store",
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as string[];
}

export async function fetchVehicleTypes(
  modelYear: number,
  brand: string,
): Promise<VehicleTypeOption[]> {
  const query = new URLSearchParams({ model_year: String(modelYear), brand });
  const response = await fetch(`${API_URL}/v1/claims/vehicle/types?${query}`, {
    cache: "no-store",
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as VehicleTypeOption[];
}

/**
 * The listed value for one trim.
 *
 * 404 means this trim has no row for that model year — a real answer, since the
 * adjacent year is a different car and the API will not substitute one.
 */
export async function fetchVehicleValue(
  modelYear: number,
  brandCode: number,
  typeCode: number,
): Promise<Valuation> {
  const query = new URLSearchParams({
    model_year: String(modelYear),
    brand_code: String(brandCode),
    type_code: String(typeCode),
  });
  const response = await fetch(`${API_URL}/v1/claims/vehicle/value?${query}`, {
    cache: "no-store",
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as Valuation;
}
