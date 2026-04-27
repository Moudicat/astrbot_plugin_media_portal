import { useAuthStore } from "@/stores/auth";

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  form?: FormData | null;
  auth?: boolean;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(message: string, status = 0, detail: unknown = null) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

export async function request<T = any>(url: string, opts: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, form = null, auth = true, headers = {}, signal } = opts;

  const finalHeaders: Record<string, string> = { ...headers };
  if (auth) {
    const authStore = useAuthStore();
    if (authStore.token) {
      finalHeaders.Authorization = `Bearer ${authStore.token}`;
    }
  }

  const init: RequestInit = { method, headers: finalHeaders, signal };
  if (form) {
    init.body = form;
  } else if (body !== undefined && body !== null) {
    finalHeaders["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  const response = await fetch(url, init);
  const contentType = response.headers.get("content-type") || "";
  let payload: any = null;
  if (contentType.includes("application/json")) {
    payload = await response.json();
  } else {
    payload = await response.text();
  }

  if (!response.ok) {
    const detailPayload =
      (payload && (payload as any).detail !== undefined ? (payload as any).detail : undefined) ??
      (typeof payload === "string" && payload ? payload : "请求失败");
    const detailText =
      typeof detailPayload === "string"
        ? detailPayload
        : typeof (detailPayload as any)?.message === "string"
          ? String((detailPayload as any).message)
          : "请求失败";
    if (response.status === 401) {
      try {
        const authStore = useAuthStore();
        if (authStore.isAuthenticated) {
          authStore.logout(false);
        }
      } catch (_e) {
        // pinia store 未就绪时忽略
      }
    }
    throw new ApiError(detailText, response.status, detailPayload);
  }
  return payload as T;
}

export function buildQuery(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    search.set(key, String(value));
  }
  const str = search.toString();
  return str ? `?${str}` : "";
}
