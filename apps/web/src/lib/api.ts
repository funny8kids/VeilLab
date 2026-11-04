import type {
  CompliancePolicy,
  DepositIntentRequest,
  DepositIntentResponse,
  HealthStatus,
  LocalDepositRequest,
  LocalDepositResponse,
  LocalWithdrawalRequest,
  LocalWithdrawalResponse,
  MockDepositRequest,
  MockDepositResponse,
  Pool,
  PoolRootResponse,
  ProofPathResponse,
  Relayer,
  WithdrawalQuoteRequest,
  WithdrawalQuoteResponse,
  WithdrawalSubmitRequest,
  WithdrawalSubmitResponse,
} from "../types";
import { assertNoNoteMaterial } from "./privacy";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const DEFAULT_TIMEOUT_MS = 7000;

/**
 * The optional bearer token is a build-time local development value. It is
 * never read from the URL, localStorage, a note field or user input. Do not
 * bake a real token into a public production build.
 */
function readApiToken(): string {
  const configured = import.meta.env.VITE_API_TOKEN;
  return typeof configured === "string" ? configured.trim() : "";
}

export function isApiTokenConfigured(): boolean {
  return readApiToken().length > 0;
}

export class ApiError extends Error {
  status: number;
  code?: string;
  requestId?: string;
  details?: Record<string, unknown>;

  constructor(
    status: number,
    message: string,
    options: {
      code?: string;
      requestId?: string;
      details?: Record<string, unknown>;
    } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = options.code;
    this.requestId = options.requestId;
    this.details = options.details;
  }
}

export function isTransportError(error: unknown): boolean {
  return !(error instanceof ApiError);
}

export function shouldFallbackToDemo(error: unknown): boolean {
  return isTransportError(error) || (error instanceof ApiError && error.status >= 500);
}

function parseBody(text: string): unknown {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = readApiToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      signal: controller.signal,
    });
    const text = await response.text();
    const body = parseBody(text);

    if (!response.ok) {
      const problem =
        body && typeof body === "object"
          ? (body as Record<string, unknown>)
          : null;
      const message =
        [problem?.detail, problem?.title, problem?.message].find(
          (value): value is string =>
            typeof value === "string" && value.trim().length > 0,
        ) ??
        (response.statusText || `Request failed (${response.status})`);
      const rawCode = problem?.code ?? problem?.error_code ?? problem?.error;
      const code = typeof rawCode === "string" ? rawCode : undefined;
      const requestId =
        typeof problem?.request_id === "string"
          ? problem.request_id
          : undefined;
      throw new ApiError(response.status, message, {
        code,
        requestId,
        details: problem ?? undefined,
      });
    }

    return body as T;
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  health(): Promise<HealthStatus> {
    return request<HealthStatus>("/api/v1/health");
  },

  async pools(): Promise<Pool[]> {
    const response = await request<{ items?: Pool[] } | Pool[]>("/api/v1/pools");
    return Array.isArray(response) ? response : (response.items ?? []);
  },

  async relayers(): Promise<Relayer[]> {
    const response = await request<{ items?: Relayer[] } | Relayer[]>(
      "/api/v1/relayers",
    );
    return Array.isArray(response) ? response : (response.items ?? []);
  },

  policy(): Promise<CompliancePolicy> {
    return request<CompliancePolicy>("/api/v1/compliance/policy");
  },

  poolRoot(poolId: string): Promise<PoolRootResponse> {
    return request<PoolRootResponse>(
      `/api/v1/pools/${encodeURIComponent(poolId)}/root`,
    );
  },

  createDepositIntent(
    payload: DepositIntentRequest,
    idempotencyKey: string,
  ): Promise<DepositIntentResponse> {
    assertNoNoteMaterial(payload);
    return request<DepositIntentResponse>(
      "/api/v1/deposits/intent",
      {
        method: "POST",
        body: JSON.stringify(payload),
        headers: { "Idempotency-Key": idempotencyKey },
      },
      10000,
    );
  },

  async recordMockDeposit(
    payload: MockDepositRequest,
    idempotencyKey: string,
  ): Promise<MockDepositResponse> {
    assertNoNoteMaterial(payload);
    const init: RequestInit = {
      method: "POST",
      body: JSON.stringify(payload),
      headers: { "Idempotency-Key": idempotencyKey },
    };
    try {
      const response = await request<MockDepositResponse | null>(
        "/api/v1/mock/deposits",
        init,
        10000,
      );
      return response ?? {};
    } catch (error) {
      // Support both route spellings documented by the API team.
      if (error instanceof ApiError && (error.status === 404 || error.status === 405)) {
        const response = await request<MockDepositResponse | null>(
          "/api/v1/deposits/mock",
          init,
          10000,
        );
        return response ?? {};
      }
      throw error;
    }
  },

  async recordLocalDeposit(
    payload: LocalDepositRequest,
    idempotencyKey: string,
  ): Promise<LocalDepositResponse> {
    assertNoNoteMaterial(payload);
    const response = await request<LocalDepositResponse | null>(
      "/api/v1/local/deposits",
      {
        method: "POST",
        body: JSON.stringify(payload),
        headers: { "Idempotency-Key": idempotencyKey },
      },
      30000,
    );
    return response ?? {};
  },

  proofPath(
    poolId: string,
    commitment: string,
  ): Promise<ProofPathResponse> {
    // Public Merkle path proxy. Both components are encoded so a pool id or
    // commitment can never change the request path structure.
    return request<ProofPathResponse>(
      `/api/v1/pools/${encodeURIComponent(poolId)}/path/${encodeURIComponent(
        commitment,
      )}`,
      {},
      15000,
    );
  },

  submitLocalWithdrawal(
    payload: LocalWithdrawalRequest,
  ): Promise<LocalWithdrawalResponse> {
    // Whitelisted public proof/signals only; the note and witness stay local.
    assertNoNoteMaterial(payload);
    return request<LocalWithdrawalResponse>(
      "/api/v1/local/withdrawals",
      { method: "POST", body: JSON.stringify(payload) },
      60000,
    );
  },

  createWithdrawalQuote(
    payload: WithdrawalQuoteRequest,
  ): Promise<WithdrawalQuoteResponse> {
    assertNoNoteMaterial(payload);
    return request<WithdrawalQuoteResponse>(
      "/api/v1/withdrawals/quote",
      { method: "POST", body: JSON.stringify(payload) },
      10000,
    );
  },

  submitWithdrawal(
    payload: WithdrawalSubmitRequest,
    idempotencyKey: string,
  ): Promise<WithdrawalSubmitResponse> {
    assertNoNoteMaterial(payload);
    return request<WithdrawalSubmitResponse>(
      "/api/v1/withdrawals/submit",
      {
        method: "POST",
        body: JSON.stringify(payload),
        headers: { "Idempotency-Key": idempotencyKey },
      },
      12000,
    );
  },
};
