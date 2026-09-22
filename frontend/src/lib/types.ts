/** TypeScript types mirroring the BuyWise backend API (v2). */

export interface DataMeta {
  data_mode: "live" | "demo" | "mixed";
  is_demo: boolean;
  providers: string[];
  cached: boolean;
  warnings: string[];
}

export interface MatchInfo {
  match_type: "exact_match" | "same_product_different_variant" | "similar_product" | "unknown";
  confidence: number;
  label: string;
  reasons: string[];
}

export interface ProductSearchResult {
  id: string;
  name: string;
  brand?: string | null;
  category?: string | null;
  image?: string | null;
  lowest_price?: number | null;
  highest_price?: number | null;
  offer_count: number;
  retailers: string[];
  average_rating?: number | null;
  match?: MatchInfo | null;
  is_demo: boolean;
}

export interface SearchResponse {
  query?: string | null;
  query_type: "text" | "url" | "image";
  detected_retailer?: string | null;
  reference_product_id?: string | null;
  total_results: number;
  page: number;
  page_size: number;
  results: ProductSearchResult[];
  meta: DataMeta;
}

export interface ProductVariant {
  id: string;
  name?: string | null;
  storage?: string | null;
  ram?: string | null;
  color?: string | null;
  size?: string | null;
}

export interface ProductDetail {
  id: string;
  name: string;
  brand?: string | null;
  model?: string | null;
  category?: string | null;
  description?: string | null;
  gtin?: string | null;
  mpn?: string | null;
  asin?: string | null;
  attributes?: Record<string, unknown> | null;
  specifications?: Record<string, string> | null;
  images: string[];
  is_demo: boolean;
  created_at: string;
  variants: ProductVariant[];
  lowest_price?: number | null;
  highest_price?: number | null;
  offer_count: number;
  exact_offer_count: number;
  average_rating?: number | null;
  rating_count?: number | null;
  meta?: DataMeta | null;
}

export interface Retailer {
  id: string;
  name: string;
  slug: string;
  domain?: string | null;
  website_url?: string | null;
  logo_url?: string | null;
  description?: string | null;
  is_marketplace: boolean;
  is_curated: boolean;
  is_demo: boolean;
  policies?: Record<string, unknown> | null;
  trust_score?: number | null;
  risk_level?: string | null;
  total_offers?: number;
}

export interface Seller {
  id: string;
  name: string;
  rating?: number | null;
  rating_count?: number | null;
  is_demo: boolean;
}

export interface TruePriceBreakdown {
  listed_price: number;
  original_price?: number | null;
  discount_amount?: number | null;
  discount_percent?: number | null;
  shipping_price?: number | null;
  shipping_known: boolean;
  coupon_code?: string | null;
  coupon_amount?: number | null;
  estimated_final_price: number;
  final_price_known: boolean;
  notes: string[];
}

export interface TrustSummary {
  score?: number | null;
  risk_level: string;
  confidence_level: string;
  /** verified | unverified | flagged — how much BuyWise knows about this seller. */
  verification: "verified" | "unverified" | "flagged";
  is_demo: boolean;
}

export interface Offer {
  id: string;
  product_id: string;
  retailer: Retailer;
  seller?: Seller | null;
  title?: string | null;
  product_url?: string | null;
  go_url: string;
  currency: string;
  price: TruePriceBreakdown;
  availability: string;
  delivery_days?: number | null;
  delivery_text?: string | null;
  cod_available?: boolean | null;
  condition: string;
  rating?: number | null;
  rating_count?: number | null;
  match: MatchInfo;
  trust: TrustSummary;
  source_provider: string;
  source_engine?: string | null;
  observed_at: string;
  is_demo: boolean;
}

export type PickCategory = "BEST_OVERALL" | "CHEAPEST" | "SAFEST" | "BEST_VALUE" | "FASTEST";

export interface OfferPick {
  category: PickCategory;
  offer_id: string;
  retailer_name: string;
  estimated_final_price: number;
  trust_score?: number | null;
  reason: string;
  confidence: number;
}

export interface OfferComparison {
  product_id: string;
  product_name: string;
  total_offers: number;
  exact_offers: number;
  offers: Offer[];
  picks: OfferPick[];
  lowest_final_price?: number | null;
  /** True when the server sent only the cheapest offer because the viewer is not on Pro. */
  locked?: boolean;
  hidden_offers?: number;
  hidden_retailers?: number;
  meta: DataMeta;
}

export interface PricePoint {
  date: string;
  price: number;
}

export interface PriceStats {
  current_price: number;
  observations: number;
  span_days: number;
  average_7d?: number | null;
  average_30d?: number | null;
  average_90d?: number | null;
  historical_low?: number | null;
  historical_high?: number | null;
  percent_vs_average?: number | null;
  percent_vs_low?: number | null;
  trend: string;
  volatility?: number | null;
}

export interface PriceSignal {
  action: "BUY_NOW" | "WAIT" | "NEUTRAL" | "INSUFFICIENT_DATA";
  status: "GOOD_DEAL" | "AVERAGE_PRICE" | "HIGH_PRICE" | "UNKNOWN";
  confidence: number;
  confidence_level: string;
  reasoning: string;
  target_price?: number | null;
  evidence: string[];
}

export interface PriceHistoryData {
  product_id: string;
  product_name: string;
  days_requested: number;
  days_available: number;
  history: PricePoint[];
  stats?: PriceStats | null;
  signal: PriceSignal;
  message?: string | null;
  meta: DataMeta;
}

export interface EvidenceExample {
  claim?: string | null;
  url?: string | null;
  source?: string | null;
  sentiment?: number | null;
}

export interface TrustFactor {
  key: string;
  label: string;
  score?: number | null;
  evidence_count: number;
  examples: EvidenceExample[];
}

export interface TrustEvidence {
  id: string;
  source: string;
  source_type: string;
  url?: string | null;
  title?: string | null;
  snippet?: string | null;
  published_at?: string | null;
  topic: string;
  sentiment: number;
  severity: number;
  confidence: number;
  extracted_claim?: string | null;
  collected_at: string;
  is_demo: boolean;
}

export interface TrustScoreData {
  retailer_id?: string | null;
  seller_id?: string | null;
  subject_name: string;
  subject_type: string;
  score?: number | null;
  risk_level: string;
  confidence: number;
  confidence_level: string;
  explanation: string;
  factors: TrustFactor[];
  concerns: TrustFactor[];
  component_scores: Record<string, number | null>;
  evidence_count: number;
  evidence: TrustEvidence[];
  methodology_version: string;
  calculated_at: string;
  meta: DataMeta;
}

export interface ReviewTheme {
  theme: string;
  count: number;
  sentiment: "positive" | "negative" | "mixed" | "neutral";
  examples: string[];
}

export interface ReviewAnalysis {
  product_id: string;
  total_reviews: number;
  average_rating?: number | null;
  positive_themes: ReviewTheme[];
  negative_themes: ReviewTheme[];
  summary?: string | null;
  confidence?: number | null;
  available: boolean;
  message?: string | null;
  meta: DataMeta;
}

export interface Recommendation {
  category: PickCategory;
  product_id: string;
  product_name: string;
  offer_id: string;
  retailer_id: string;
  retailer_name: string;
  seller_name?: string | null;
  price: number;
  final_price_known: boolean;
  trust_score?: number | null;
  trust_risk: string;
  price_status: string;
  price_action: string;
  match_label: string;
  match_confidence: number;
  reason: string;
  confidence: number;
  go_url: string;
  product_url?: string | null;
}

export interface RecommendationSet {
  product_id: string;
  product_name: string;
  recommendations: Recommendation[];
  locked?: boolean;
  ai_explanation?: string | null;
  ai_provider?: string | null;
  meta: DataMeta;
}

export interface AgentIntent {
  kind: string;
  product_query?: string | null;
  budget_max?: number | null;
  brands: string[];
  compare_items: string[];
  retailer?: string | null;
  priority?: string | null;
}

export interface AgentResponse {
  query: string;
  intent: AgentIntent;
  answer: string;
  products: { product: ProductSearchResult; recommendations?: RecommendationSet | null }[];
  trust?: TrustScoreData | null;
  price_signal?: PriceSignal | null;
  ai_provider: string;
  meta: DataMeta;
}

export type ReportType = "purchase" | "delivery" | "return" | "refund" | "authenticity" | "seller";

export interface CommunityReport {
  id: string;
  username?: string | null;
  product_id?: string | null;
  retailer_id?: string | null;
  seller_id?: string | null;
  report_type: ReportType;
  title?: string | null;
  body: string;
  rating?: number | null;
  verification_status: "unverified" | "pending" | "verified" | "rejected";
  moderation_status: "pending" | "approved" | "rejected" | "hidden";
  flag_count: number;
  helpful_count: number;
  is_demo: boolean;
  created_at: string;
}

export interface CommunityReportCreate {
  product_id?: string;
  retailer_id?: string;
  seller_id?: string;
  report_type: ReportType;
  title?: string;
  body: string;
  rating?: number;
  order_reference?: string;
}

export interface PriceAlert {
  id: string;
  product_id: string;
  product_name?: string | null;
  product_image?: string | null;
  alert_type: "target_price" | "percent_drop";
  target_price?: number | null;
  drop_percent?: number | null;
  baseline_price?: number | null;
  currency: string;
  current_lowest_price?: number | null;
  is_active: boolean;
  is_triggered: boolean;
  triggered_at?: string | null;
  trigger_count: number;
  last_checked_at?: string | null;
  notification_method: string;
  created_at: string;
}

export interface User {
  id: string;
  email: string;
  username: string;
  display_name?: string | null;
  avatar_url?: string | null;
  auth_provider: string;
  is_active: boolean;
  is_verified: boolean;
  role: string;
  plan: "free" | "pro";
  notification_preferences?: Record<string, boolean> | null;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface AppMeta {
  app: string;
  version: string;
  data_mode: "live" | "demo";
  demo_mode: boolean;
  ai_mode: "live" | "demo";
  payments_enabled: boolean;
  google_auth_enabled: boolean;
  image_search_enabled: boolean;
  trust_sources: string[];
  razorpay_key_id?: string | null;
}

export interface PlanInfo {
  id: string;
  name: string;
  price_inr: number;
  period_days: number;
  features: string[];
  /** Worked out server-side; the page never does arithmetic on prices. */
  monthly_equivalent_inr?: number | null;
  savings_percent?: number | null;
  is_best_value: boolean;
}

export interface SubscriptionStatus {
  plan: string;
  status: string;
  is_pro: boolean;
  current_period_end?: string | null;
  cancel_at_period_end: boolean;
  limits: Record<string, number>;
  usage: Record<string, number>;
  features?: Record<string, boolean>;
  payments_enabled: boolean;
}

export interface Dashboard {
  user: User & { notification_preferences: Record<string, boolean> };
  subscription: SubscriptionStatus;
  saved_products: { id: string; product_id: string; name: string; image?: string | null; brand?: string | null; note?: string | null; lowest_price?: number | null; is_demo: boolean; saved_at: string }[];
  alerts: { id: string; product_id: string; product_name?: string | null; alert_type: string; target_price?: number | null; drop_percent?: number | null; current_lowest_price?: number | null; is_active: boolean; is_triggered: boolean; triggered_at?: string | null }[];
  price_drops: { alert_id: string; product_id: string; product_name?: string | null; current_lowest_price?: number | null; triggered_at?: string | null }[];
  recent_searches: { id: string; query?: string | null; type?: string | null; results?: number | null; at: string }[];
  notifications: { id: string; kind: string; subject: string; status: string; created_at: string; read_at?: string | null }[];
  payments: { id: string; plan: string; amount: number; currency: string; status: string; paid_at?: string | null; created_at: string; order_id: string }[];
}

export interface CreateOrderResponse {
  order_id: string;
  amount: number;
  currency: string;
  key_id: string;
  plan: string;
  name: string;
  description: string;
  prefill: { email?: string; name?: string };
}
