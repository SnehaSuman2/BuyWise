/** API client for the BuyWise backend. Tokens live in localStorage; a 401 triggers one refresh attempt. */

import type {
  AgentResponse, AppMeta, CreateOrderResponse, Dashboard, OfferComparison, PlanInfo, PriceAlert, PriceHistoryData,
  ProductDetail, RecommendationSet, Retailer, SearchResponse, SubscriptionStatus, TokenResponse, TrustScoreData, User,
} from "./types";

export const API_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const SERVER_BASE = (process.env.API_INTERNAL_URL || API_BASE).replace(/\/$/, "");
const V1 = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const KEYS = { access: "buywise_access", refresh: "buywise_refresh", user: "buywise_user" } as const;

export const tokenStore = {
  get access() { return typeof window === "undefined" ? null : localStorage.getItem(KEYS.access); },
  get refresh() { return typeof window === "undefined" ? null : localStorage.getItem(KEYS.refresh); },
  get user(): User | null {
    if (typeof window === "undefined") return null;
    try { const raw = localStorage.getItem(KEYS.user); return raw ? (JSON.parse(raw) as User) : null; } catch { return null; }
  },
  set(t: TokenResponse) {
    localStorage.setItem(KEYS.access, t.access_token);
    localStorage.setItem(KEYS.refresh, t.refresh_token);
    localStorage.setItem(KEYS.user, JSON.stringify(t.user));
  },
  setUser(u: User) { localStorage.setItem(KEYS.user, JSON.stringify(u)); },
  clear() { Object.values(KEYS).forEach((k) => localStorage.removeItem(k)); },
};

let refreshing: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  if (refreshing) return refreshing;
  refreshing = (async () => {
    const refresh = tokenStore.refresh;
    if (!refresh) return false;
    try {
      const res = await fetch(`${API_BASE}${V1}/auth/refresh`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh_token: refresh }) });
      if (!res.ok) { tokenStore.clear(); return false; }
      tokenStore.set((await res.json()) as TokenResponse);
      return true;
    } catch { return false; } finally { refreshing = null; }
  })();
  return refreshing;
}

async function parseError(res: Response): Promise<ApiError> {
  let detail = `Request failed (${res.status})`;
  try {
    const data = await res.json();
    if (typeof data.detail === "string") detail = data.detail;
    else if (Array.isArray(data.detail)) detail = data.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join(", ") || detail;
    else if (data.error) detail = String(data.error);
  } catch { /* ignore */ }
  return new ApiError(detail, res.status);
}

/** Browser-side request with auth + refresh. */
export async function request<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers: Record<string, string> = { ...(options.headers as Record<string, string> | undefined) };
  if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const token = tokenStore.access;
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${V1}${path}`, { ...options, headers });
  } catch {
    throw new ApiError("Cannot reach the BuyWise API. Is the backend running?", 0);
  }
  if (res.status === 401 && retry && tokenStore.refresh && !path.startsWith("/auth/")) {
    if (await tryRefresh()) return request<T>(path, options, false);
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Server-side fetch (Next.js server components). No auth, never cached. */
export async function serverGet<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${SERVER_BASE}${V1}${path}`, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export const api = {
  meta: () => request<AppMeta>("/meta"),
  // auth
  register: (data: { email: string; username: string; password: string; display_name?: string }) => request<TokenResponse>("/auth/register", { method: "POST", body: JSON.stringify(data) }),
  login: (data: { email: string; password: string }) => request<TokenResponse>("/auth/login", { method: "POST", body: JSON.stringify(data) }),
  googleLogin: (id_token: string) => request<TokenResponse>("/auth/google", { method: "POST", body: JSON.stringify({ id_token }) }),
  logout: (refresh_token: string) => request<void>("/auth/logout", { method: "POST", body: JSON.stringify({ refresh_token }) }),
  logoutAll: () => request<void>("/auth/logout-all", { method: "POST" }),
  changePassword: (data: { current_password?: string; new_password: string }) => request<void>("/auth/password", { method: "POST", body: JSON.stringify(data) }),
  me: () => request<User>("/auth/me"),
  // search / products
  search: (data: { query?: string; url?: string; image_url?: string; image_base64?: string; min_price?: number; max_price?: number; sort_by?: string; page?: number; page_size?: number }) => request<SearchResponse>("/search", { method: "POST", body: JSON.stringify(data) }),
  product: (id: string) => request<ProductDetail>(`/products/${id}`),
  offers: (id: string, refresh = false) => request<OfferComparison>(`/products/${id}/offers${refresh ? "?refresh=true" : ""}`),
  history: (id: string, days = 90) => request<PriceHistoryData>(`/products/${id}/history?days=${days}`),
  productTrust: (id: string) => request<TrustScoreData[]>(`/products/${id}/trust`),
  recommendations: (id: string) => request<RecommendationSet>(`/products/${id}/recommendations`),
  retailer: (id: string) => request<Retailer>(`/retailers/${id}`),
  retailers: () => request<Retailer[]>("/retailers"),
  retailerTrust: (id: string) => request<TrustScoreData>(`/retailers/${id}/trust`),
  // agent
  agent: (query: string, product_id?: string) => request<AgentResponse>("/agent", { method: "POST", body: JSON.stringify({ query, product_id }) }),
  // alerts
  alerts: () => request<PriceAlert[]>("/alerts"),
  createAlert: (data: { product_id: string; alert_type: "target_price" | "percent_drop"; target_price?: number; drop_percent?: number }) => request<PriceAlert>("/alerts", { method: "POST", body: JSON.stringify(data) }),
  deleteAlert: (id: string) => request<void>(`/alerts/${id}`, { method: "DELETE" }),
  pauseAlert: (id: string) => request<PriceAlert>(`/alerts/${id}/pause`, { method: "POST" }),
  resumeAlert: (id: string) => request<PriceAlert>(`/alerts/${id}/resume`, { method: "POST" }),
  // account
  dashboard: () => request<Dashboard>("/dashboard"),
  updateAccount: (data: { display_name?: string; notification_preferences?: Record<string, boolean> }) => request<User>("/account", { method: "PATCH", body: JSON.stringify(data) }),
  deleteAccount: (data: { confirm: string; password?: string }) => request<void>("/account", { method: "DELETE", body: JSON.stringify(data) }),
  saveProduct: (product_id: string, note?: string) => request<{ id: string; already_saved: boolean }>("/saved-products", { method: "POST", body: JSON.stringify({ product_id, note }) }),
  unsaveProduct: (product_id: string) => request<void>(`/saved-products/${product_id}`, { method: "DELETE" }),
  savedProducts: () => request<Dashboard["saved_products"]>("/saved-products"),
  // billing
  plans: () => request<PlanInfo[]>("/subscription/plans"),
  subscription: () => request<SubscriptionStatus>("/subscription"),
  cancelSubscription: () => request<SubscriptionStatus>("/subscription/cancel", { method: "POST" }),
  createOrder: (plan: string) => request<CreateOrderResponse>("/payments/create", { method: "POST", body: JSON.stringify({ plan }) }),
  verifyPayment: (data: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) => request<SubscriptionStatus>("/payments/verify", { method: "POST", body: JSON.stringify(data) }),
};
