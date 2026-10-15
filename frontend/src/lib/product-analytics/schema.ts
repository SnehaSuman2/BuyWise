export type EventProperties = {
  page_viewed: { path: string };
  search_submitted: { query_type: "text" | "url"; query_length: number; is_demo: boolean };
  search_results_viewed: { result_count: number; query_type: "text" | "url" | "browse" | "image"; is_demo: boolean };
  product_selected: { product_id: string; category: string; source: "search" | "agent"; is_demo: boolean };
  product_viewed: { product_id: string; category: string; is_demo: boolean };
  retailer_clicked: { product_id: string; retailer_id: string; offer_id: string; price: number; currency: string; source: "recommendation" | "comparison"; is_demo: boolean };
  product_section_clicked: { product_id: string; section: string; is_demo: boolean };
  agent_search_submitted: { query_length: number; is_demo: boolean };
  agent_results_viewed: { result_count: number; is_demo: boolean };
  auth_submitted: { method: "login" | "register"; is_demo: boolean };
  signed_up: { is_demo: false };
  logged_in: { is_demo: false };
  logged_out: Record<string, never>;
  alert_created: { product_id: string; target_price: number; currency: string; is_demo: false };
  alert_deleted: { alert_id: string; is_demo: boolean };
};
