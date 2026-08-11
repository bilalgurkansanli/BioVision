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
  DomainsResponse,
  ErrorCode,
  RequestHistoryResponse,
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
