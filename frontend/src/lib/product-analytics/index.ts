import { createAnalyticsClient, type AnalyticsAdapter, type Properties } from "./client";
import type { EventProperties } from "./schema";
import { amplitudeEnvelope, amplitudeEventStorage, customProperties, isCustomEvent, isUuid, mixpanelEnvelope, mixpanelPeople, personProperties, posthogEnvelope, safePath } from "./privacy";

function providerFactories(): Array<() => Promise<AnalyticsAdapter>> {
  const factories: Array<() => Promise<AnalyticsAdapter>> = [];
  if (process.env.NEXT_PUBLIC_MIXPANEL_TOKEN) factories.push(async () => {
    const { default: mixpanel } = await import("mixpanel-browser");
    const key = process.env.NEXT_PUBLIC_MIXPANEL_TOKEN!;
    // on_track also filters SDK-internal identify events that use skip_hooks.
    // before_send_people is supported by the installed SDK's transport/batcher,
    // although its published hooks interface omits that key.
    const filterTrack = (event: string, properties: Record<string, unknown>): [string, Record<string, unknown>] | undefined => {
      const safe = mixpanelEnvelope({ event, properties }, key);
      return safe ? [safe.event, safe.properties] : undefined;
    };
    const hooks = {
      // The installed multi-argument hook runner aborts on undefined, whereas
      // null only replaces its first argument. Its published return type omits
      // undefined. An SDK-level regression test covers this fail-closed path.
      on_track: filterTrack as (event: string, properties: Record<string, unknown>) => [string, Record<string, unknown>] | null,
      before_send_events: (event: unknown) => mixpanelEnvelope(event, key),
      before_send_people: (people: unknown) => mixpanelPeople(people, key),
    };
    mixpanel.init(key, {
      api_host: process.env.NEXT_PUBLIC_MIXPANEL_API_HOST || "https://api-js.mixpanel.com",
      autocapture: false, track_pageview: false, record_sessions_percent: 0,
      // Orphaned persisted batches can bypass SDK hooks. Keep identity persistence,
      // but send through the filtered immediate path; our loading buffer is unchanged.
      batch_requests: false,
      record_heatmap_data: false, remote_settings_mode: "disabled",
      persistence: "localStorage", save_referrer: false,
      // Runtime-supported attribution switches omitted from the SDK's Config type.
      ...{ track_marketing: false, store_google: false }, stop_utm_persistence: true,
      hooks,
    });
    console.info("[analytics] mixpanel initialized");
    return {
      track: (event, properties) => { mixpanel.track(event, properties); },
      identify: (id, properties) => {
        const previous = mixpanel.get_property("$user_id");
        if (previous && previous !== id) mixpanel.reset();
        mixpanel.identify(id);
        mixpanel.people.set(personProperties(properties));
      },
      reset: () => mixpanel.reset(),
      reconcileAnonymous: () => { if (mixpanel.get_property("$user_id")) mixpanel.reset(); },
    };
  });
  if (process.env.NEXT_PUBLIC_POSTHOG_KEY) factories.push(async () => {
    const { default: posthog } = await import("posthog-js");
    const key = process.env.NEXT_PUBLIC_POSTHOG_KEY!;
    posthog.init(key, {
      api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST || "https://us.i.posthog.com",
      autocapture: false, capture_pageview: false, capture_pageleave: false,
      capture_dead_clicks: false, capture_exceptions: false, rageclick: false,
      disable_session_recording: true, disable_surveys: true,
      disable_product_tours: true, disable_conversations: true, disable_web_experiments: true,
      disable_external_dependency_loading: true, advanced_disable_feature_flags: true,
      save_referrer: false, save_campaign_params: false, disable_capture_url_hashes: true,
      person_profiles: "identified_only",
      before_send: (event) => posthogEnvelope(event, key),
    });
    console.info("[analytics] posthog initialized");
    return {
      track: (event, properties) => { posthog.capture(event, properties); },
      identify: (id, properties) => {
        const previous = posthog.get_property("$user_id");
        if (previous && previous !== id) posthog.reset();
        posthog.identify(id, personProperties(properties));
      },
      reset: () => posthog.reset(),
      reconcileAnonymous: () => { if (posthog.get_property("$user_id") || posthog.get_property("$user_state") === "identified") posthog.reset(); },
    };
  });
  if (process.env.NEXT_PUBLIC_AMPLITUDE_API_KEY) factories.push(async () => {
    const amplitude = await import("@amplitude/analytics-browser");
    await amplitude.init(process.env.NEXT_PUBLIC_AMPLITUDE_API_KEY!, {
      autocapture: false, defaultTracking: false,
      fetchRemoteConfig: false, remoteConfig: { fetchRemoteConfig: false },
      enableDiagnostics: false,
      storageProvider: amplitudeEventStorage(),
      serverZone: process.env.NEXT_PUBLIC_AMPLITUDE_SERVER_ZONE === "EU" ? "EU" : "US",
    }).promise;
    await amplitude.add({
      name: "buywise-outbound-privacy", type: "enrichment",
      setup: async (config) => {
        // Fail closed if the installed SDK ever stops honoring these options.
        if (config.autocapture !== false || config.defaultTracking !== false || config.fetchRemoteConfig !== false) {
          throw new Error("Unsafe Amplitude capture configuration");
        }
      },
      execute: async (event) => amplitudeEnvelope(event),
    }).promise;
    console.info("[analytics] amplitude initialized");
    return {
      track: (event, properties) => { amplitude.track(event, properties); },
      identify: (id, properties) => {
        const previous = amplitude.getUserId();
        if (previous && previous !== id) amplitude.reset();
        amplitude.setUserId(id);
        const identify = new amplitude.Identify();
        for (const [key, value] of Object.entries(personProperties(properties))) identify.set(key, value as string | boolean);
        amplitude.identify(identify);
      },
      reset: () => amplitude.reset(),
      reconcileAnonymous: () => { if (amplitude.getUserId()) amplitude.reset(); },
    };
  });
  return factories;
}

let client: ReturnType<typeof createAnalyticsClient> | undefined;
let ready = false;
let reconciled = false;
let pending: Array<{ event: string; properties: Properties }> = [];
export function isAnalyticsEnabled() {
  return typeof window !== "undefined" && process.env.NEXT_PUBLIC_ANALYTICS_ENABLED === "true";
}
function getClient() {
  if (!isAnalyticsEnabled()) return;
  return client ??= createAnalyticsClient(providerFactories());
}
function releaseEvents() {
  ready = true;
  reconciled = true;
  const events = pending;
  pending = [];
  for (const item of events) {
    getClient()?.track(item.event, item.properties);
    console.info(`[analytics] event dispatched: ${item.event}`);
  }
}
export function holdAnalyticsEvents(discardPending = true) {
  ready = false;
  if (discardPending) pending = [];
}
export function reconcileAnonymous() {
  getClient()?.reconcileAnonymous();
  releaseEvents();
}
export function trackEvent<E extends keyof EventProperties>(event: E, properties: EventProperties[E]) {
  if (!isAnalyticsEnabled() || !isCustomEvent(event)) return;
  const safe = customProperties(event, {
    ...properties,
    event_id: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    occurred_at: new Date().toISOString(), environment: process.env.NODE_ENV,
    path: safePath(window.location.pathname), schema_version: 1,
  }) as Properties;
  if (ready) {
    getClient()?.track(event, safe);
    console.info(`[analytics] event dispatched: ${event}`);
  }
  else if (pending.length < 100) pending.push({ event, properties: safe });
}
export function identifyUser(user: { id: string; created_at: string; role: string; is_verified: boolean }) {
  if (!isUuid(user.id)) { reconcileAnonymous(); return; }
  getClient()?.identify(user.id, personProperties({
    signup_date: user.created_at.slice(0, 10), role: user.role, is_verified: user.is_verified,
  }) as Properties);
  releaseEvents();
}
export function resetAnalytics() {
  getClient()?.reset();
  releaseEvents();
}
export function logoutAnalytics() {
  pending = [];
  // An unresolved initial session must not attribute logout to persisted SDK state.
  if (!reconciled) getClient()?.reconcileAnonymous();
  ready = true;
  trackEvent("logged_out", {});
  resetAnalytics();
}
