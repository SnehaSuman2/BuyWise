import type { EventProperties } from "./schema";

type RecordValue = Record<string, unknown>;
type Validator = (value: unknown) => boolean;
type Rules = Record<string, Validator>;
const bool: Validator = (v) => typeof v === "boolean";
const number: Validator = (v) => typeof v === "number" && Number.isFinite(v);
const count: Validator = (v) => number(v) && Number.isInteger(v) && (v as number) >= 0;
const oneOf = (...values: string[]): Validator => (v) => typeof v === "string" && values.includes(v);
const matching = (pattern: RegExp): Validator => (v) => typeof v === "string" && pattern.test(v);
export const isUuid = matching(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i);
const opaqueId: Validator = (v) => isUuid(v) || matching(/^(?:\$device:)?[0-9a-f-]{16,128}$/i)(v);
const entityId: Validator = (v) => isUuid(v) || matching(/^[proa]\d{1,12}$/)(v) || v === "unknown";
const category = oneOf("Headphones", "Keyboards", "Laptops", "Smartphones", "Smartwatches", "TVs", "unknown");
const date = matching(/^\d{4}-\d{2}-\d{2}$/);
const timestamp = matching(/^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/);

/** Paths are controlled route names or validated entity IDs, never arbitrary URL text. */
export function safePath(value: unknown): string {
  if (typeof value !== "string") return "/unknown";
  const path = value.split(/[?#]/, 1)[0];
  if (["/", "/search", "/agent", "/alerts", "/auth/login", "/auth/register"].includes(path)) return path;
  const match = /^\/(product|retailer)\/([^/]+)$/.exec(path);
  if (match) return `/${match[1]}/${entityId(match[2]) && match[2] !== "unknown" ? match[2] : "[id]"}`;
  return "/unknown";
}

const common: Rules = {
  event_id: (v) => isUuid(v) || matching(/^\d{13}-[a-z0-9]{1,16}$/)(v),
  occurred_at: timestamp,
  environment: oneOf("development", "production", "test"),
  path: (v) => typeof v === "string" && safePath(v) === v,
  schema_version: (v) => v === 1,
};
const eventRules = {
  page_viewed: { path: common.path },
  search_submitted: { query_type: oneOf("text", "url"), query_length: count, is_demo: bool },
  search_results_viewed: { result_count: count, query_type: oneOf("text", "url", "browse", "image"), is_demo: bool },
  product_selected: { product_id: entityId, category, source: oneOf("search", "agent"), is_demo: bool },
  product_viewed: { product_id: entityId, category, is_demo: bool },
  retailer_clicked: { product_id: entityId, retailer_id: entityId, offer_id: entityId, price: number, currency: oneOf("INR", "USD", "EUR", "GBP"), source: oneOf("recommendation", "comparison"), is_demo: bool },
  product_section_clicked: { product_id: entityId, section: oneOf("Recommendations", "Price Comparison", "Reviews", "Trust"), is_demo: bool },
  agent_search_submitted: { query_length: count, is_demo: bool },
  agent_results_viewed: { result_count: count, is_demo: bool },
  auth_submitted: { method: oneOf("login", "register"), is_demo: bool },
  signed_up: { is_demo: (v: unknown) => v === false },
  logged_in: { is_demo: (v: unknown) => v === false },
  logged_out: {},
  alert_created: { product_id: entityId, target_price: number, currency: oneOf("INR", "USD", "EUR", "GBP"), is_demo: (v: unknown) => v === false },
  alert_deleted: { alert_id: entityId, is_demo: bool },
} satisfies { [E in keyof EventProperties]: { [K in keyof EventProperties[E]]: Validator } };

function record(value: unknown): RecordValue {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as RecordValue : {};
}
function pick(value: unknown, rules: Rules): RecordValue {
  const input = record(value);
  return Object.fromEntries(Object.entries(rules).filter(([key, validate]) => Object.hasOwn(input, key) && validate(input[key])).map(([key]) => [key, input[key]]));
}
export function isCustomEvent(event: string): event is keyof EventProperties {
  return Object.hasOwn(eventRules, event);
}
export function customProperties(event: string, value: unknown): RecordValue {
  return isCustomEvent(event) ? pick(value, { ...eventRules[event], ...common }) : {};
}
export function personProperties(value: unknown): RecordValue {
  return pick(value, { signup_date: date, role: oneOf("user", "admin", "moderator", "unknown"), is_verified: bool });
}

// Keep useful, bounded browser/device metadata. Raw user agents, URLs, attribution,
// free-form labels, arbitrary nested objects, and unknown future SDK fields are excluded.
const browser = oneOf("Chrome", "Chrome iOS", "Safari", "Mobile Safari", "Firefox", "Firefox iOS", "Microsoft Edge", "Edge", "Opera", "Opera Mini", "Samsung Internet", "Internet Explorer", "Android Mobile", "Other", "Unknown");
const os = oneOf("Windows", "Mac OS X", "macOS", "Mac OS", "Linux", "Android", "iOS", "Chrome OS", "Other", "Unknown");
const device = oneOf("Desktop", "Mobile", "Tablet", "desktop", "mobile", "tablet", "iPhone", "iPad", "Android", "Android Phone", "Android Tablet", "Other", "Unknown");
const version = matching(/^\d+(?:\.\d+){0,4}$/);
const native: Rules = {
  distinct_id: opaqueId, $distinct_id: opaqueId, $device_id: opaqueId, $user_id: isUuid,
  $anon_distinct_id: opaqueId, $had_persisted_distinct_id: bool,
  $browser: browser, $browser_version: (v) => number(v) || version(v),
  $os: os, $os_version: version, $device: device, $device_type: device,
  $screen_height: count, $screen_width: count, $viewport_height: count, $viewport_width: count,
  $lib: oneOf("web", "posthog-js"), mp_lib: oneOf("web"), $lib_version: version,
  $session_id: opaqueId, $window_id: opaqueId, $insert_id: opaqueId,
  $process_person_profile: bool, $is_identified: bool, time: number,
};
function sdkProperties(event: string, value: unknown, projectKey: string): RecordValue {
  const input = record(value);
  return {
    ...pick(input, native),
    ...customProperties(event, input),
    ...(input.token === projectKey ? { token: projectKey } : {}),
  };
}

export function posthogEnvelope<T extends { event: string; properties: RecordValue; uuid: string; timestamp?: Date }>(event: T, projectKey: string) {
  if (!isUuid(event.uuid)) return null;
  if (!isCustomEvent(event.event) && !["$identify", "$set"].includes(event.event)) return null;
  const raw = record(event);
  const properties = sdkProperties(event.event, event.properties, projectKey);
  const nested = record(event.properties);
  if (nested.$set) properties.$set = personProperties(nested.$set);
  if (nested.$set_once) properties.$set_once = personProperties(nested.$set_once);
  return {
    event: event.event,
    uuid: event.uuid,
    timestamp: Object.prototype.toString.call(event.timestamp) === "[object Date]" && Number.isFinite(Number(event.timestamp)) ? event.timestamp : undefined,
    properties,
    ...(raw.$set ? { $set: personProperties(raw.$set) } : {}),
    ...(raw.$set_once ? { $set_once: personProperties(raw.$set_once) } : {}),
  };
}

export function mixpanelEnvelope(value: unknown, projectKey: string) {
  const input = record(value);
  const event = input.event;
  if (typeof event !== "string" || (!isCustomEvent(event) && event !== "$identify")) return null;
  return { event, properties: sdkProperties(event, input.properties, projectKey) };
}
export function mixpanelPeople(value: unknown, projectKey: string) {
  const input = record(value);
  const identity = pick(input, native);
  if (!identity.$distinct_id) return null;
  return {
    ...identity, $token: projectKey,
    ...(input.$set ? { $set: { ...pick(input.$set, native), ...personProperties(input.$set) } } : {}),
    ...(input.$set_once ? { $set_once: personProperties(input.$set_once) } : {}),
  };
}

/** Last enrichment boundary: permit only custom events and safe identity updates. */
export function amplitudeEnvelope<T extends { event_type: string }>(value: T) {
  if (!isCustomEvent(value.event_type) && value.event_type !== "$identify") return null;
  const input = record(value);
  const envelope = pick(input, {
    user_id: isUuid, device_id: opaqueId, session_id: number, event_id: count,
    insert_id: opaqueId, time: number, platform: oneOf("Web"),
    library: matching(/^amplitude-(?:ts|js)\/\d+(?:\.\d+){1,3}$/),
    os_name: os, os_version: version, device_model: device,
    language: matching(/^[a-z]{2,3}(?:[-_][A-Z]{2})?$/),
    ip: (v) => v === "$remote",
  });
  return {
    ...envelope,
    event_type: value.event_type,
    event_properties: customProperties(value.event_type, input.event_properties),
    ...(input.user_properties ? { user_properties: {
      $set: personProperties(record(input.user_properties).$set),
      $setOnce: personProperties(record(input.user_properties).$setOnce),
    } } : {}),
  };
}

/** Persisted retries bypass enrichment in this SDK, so filter them at storage too. */
export function amplitudeEventStorage() {
  const memory = new Map<string, Array<NonNullable<ReturnType<typeof amplitudeEnvelope>>>>();
  const ownedKeys = new Set<string>();
  const filter = (value: unknown) => Array.isArray(value) ? value.flatMap((item) => {
    const event = record(item);
    if (typeof event.event_type !== "string") return [];
    const safe = amplitudeEnvelope({ ...event, event_type: event.event_type });
    return safe ? [safe] : [];
  }) : [];
  const read = async (key: string) => {
    ownedKeys.add(key);
    try {
      const stored = localStorage.getItem(key);
      if (stored) return filter(JSON.parse(stored));
    } catch { /* Use the safe in-memory queue when storage is unavailable. */ }
    return memory.get(key);
  };
  return {
    isEnabled: async () => true,
    get: read,
    getRaw: async (key: string) => JSON.stringify(await read(key)),
    set: async (key: string, value: Array<{ event_type: string }>) => {
      ownedKeys.add(key);
      const safe = filter(value);
      memory.set(key, safe);
      try { localStorage.setItem(key, JSON.stringify(safe)); } catch { /* Memory fallback. */ }
    },
    remove: async (key: string) => {
      memory.delete(key);
      try { localStorage.removeItem(key); } catch { /* Memory fallback. */ }
    },
    reset: async () => {
      memory.clear();
      for (const key of ownedKeys) {
        try { localStorage.removeItem(key); } catch { /* Memory fallback. */ }
      }
      ownedKeys.clear();
    },
  };
}
