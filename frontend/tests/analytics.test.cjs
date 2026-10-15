/* eslint-disable @typescript-eslint/no-require-imports -- Node test harness. */
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { USER_A, USER_B, ANON, user, response, tick, deferred, loader, runtime, ok, failure } = require('./helpers.cjs');
const { createAnalyticsClient } = loader().load('lib/product-analytics/client.ts');
const adapter = log => ({ track: (e, p) => log.push(['track', e, p]), identify: (id, p) => log.push(['identify', id, p]), reset: () => log.push(['reset']) });

for (const zone of ['US', 'EU']) {
  test(`production CSP allows configured ${zone} SDK transports without exposing project keys`, async () => {
    const env = { NODE_ENV: 'production', NEXT_PUBLIC_ANALYTICS_ENABLED: 'true', NEXT_PUBLIC_MIXPANEL_TOKEN: 'private-mixpanel-key', NEXT_PUBLIC_POSTHOG_KEY: 'private-posthog-key', NEXT_PUBLIC_AMPLITUDE_API_KEY: 'private-amplitude-key', NEXT_PUBLIC_AMPLITUDE_SERVER_ZONE: zone };
    const config = loader({ process: { env }, URL }).load('../next.config.ts').default;
    const policy = (await config.headers())[0].headers.find(h => h.key === 'Content-Security-Policy').value;
    assert.ok(policy.includes('https://api-js.mixpanel.com'));
    assert.ok(policy.includes('https://us.i.posthog.com'));
    assert.ok(policy.includes('https://us-assets.i.posthog.com'));
    assert.ok(policy.includes(zone === 'EU' ? 'https://api.eu.amplitude.com' : 'https://api2.amplitude.com'));
    assert.ok(!policy.includes('private'));
  });
}

test('disabled analytics adds no analytics hosts to the production CSP', async () => {
  const config = loader({ process: { env: { NODE_ENV: 'production', NEXT_PUBLIC_ANALYTICS_ENABLED: 'false', NEXT_PUBLIC_MIXPANEL_TOKEN: 'configured' } }, URL }).load('../next.config.ts').default;
  const policy = (await config.headers())[0].headers.find(h => h.key === 'Content-Security-Policy').value;
  assert.ok(!policy.includes('mixpanel.com'));
  assert.ok(!policy.includes('posthog.com'));
  assert.ok(!policy.includes('amplitude.com'));
});

for (const queryType of ['text', 'url', 'image']) {
  test(`production ${queryType} search reaches all SDKs without GA or raw search input`, async () => {
    const r = runtime();
    const legacy = r.load('lib/analytics.ts');
    r.analytics.reconcileAnonymous();
    legacy.track('search', { query_type: queryType, results: 4, data_mode: 'live', search_term: 'private-search-value', url: 'https://private.example' });
    await tick();
    assert.equal(r.tracks().length, 3);
    for (const event of r.tracks()) {
      assert.equal(event.event, 'search_results_viewed');
      assert.equal(event.properties.query_type, queryType);
      assert.equal(event.properties.result_count, 4);
      assert.equal(event.properties.is_demo, false);
      assert.ok(!JSON.stringify(event).includes('private'));
    }
  });
}

test('loading providers replay buffered events and identity operations in order; failed providers stay isolated', async () => {
  const slow = [], fast = [], delay = deferred();
  const client = createAnalyticsClient([() => delay.promise, async () => adapter(fast), async () => { throw Error('unavailable'); }]);
  client.track('search_submitted', { is_demo: true }); client.identify(USER_A, {});
  client.track('signed_up', { is_demo: false }); client.reset(); client.track('page_viewed', { path: '/' });
  await tick(); assert.equal(fast.length, 5); assert.equal(slow.length, 0);
  delay.resolve(adapter(slow)); await tick(); assert.deepEqual(slow, fast);
});

test('existing loading event limit and property snapshots remain unchanged', async () => {
  const delay = deferred(), log = [];
  const client = createAnalyticsClient([() => delay.promise]);
  const properties = { product_id: 'p1' }; client.track('product_selected', properties); properties.product_id = 'p2';
  for (let i = 0; i < 200; i++) client.track('view', { i });
  client.identify(USER_A, {}); client.reset();
  delay.resolve(adapter(log)); await tick();
  assert.equal(log.length, 102); assert.equal(log[0][2].product_id, 'p1');
  assert.deepEqual(log.slice(-2).map(call => call[0]), ['identify', 'reset']);
});

test('a failed identity reconciliation disables that provider instead of sending events under its stale user', async () => {
  const good = [], bad = [];
  const client = createAnalyticsClient([async () => ({ ...adapter(bad), reconcileAnonymous() { throw Error('reset failed'); } }), async () => adapter(good)]);
  client.reconcileAnonymous(); client.track('page_viewed', { path: '/' }); await tick();
  assert.equal(bad.length, 0); assert.equal(good.length, 1);
});

for (const options of [{ enabled: false }, { keys: [] }, { browser: false }]) {
  test(`disabled/unconfigured/SSR does not attempt SDK imports: ${JSON.stringify(options)}`, async () => {
    const r = runtime(options);
    r.analytics.trackEvent('page_viewed', { path: '/' }); r.analytics.reconcileAnonymous();
    r.analytics.identifyUser(user()); r.analytics.resetAnalytics(); await tick();
    assert.equal(r.imports.filter(name => ['mixpanel-browser', 'posthog-js', '@amplitude/analytics-browser'].includes(name)).length, 0);
    assert.equal(r.tracks().length, 0);
  });
}
for (const provider of ['mixpanel', 'posthog', 'amplitude']) {
  test(`provider optionality and one initialization: ${provider}`, async () => {
    const r = runtime({ keys: [provider] }); r.analytics.reconcileAnonymous();
    r.analytics.trackEvent('page_viewed', { path: '/' }); r.analytics.trackEvent('page_viewed', { path: '/' }); await tick();
    assert.equal(r.states[provider].inits, 1); assert.equal(r.tracks().length, 2);
    assert.ok(r.tracks().every(event => event.provider === provider));
  });
}

test('custom schema/common properties are identical across providers and extra user text is rejected', async () => {
  const r = runtime(); r.analytics.reconcileAnonymous();
  r.analytics.trackEvent('search_submitted', { query_type: 'text', query_length: 42, is_demo: true, email: 'private@example.test', query: 'private prompt', password: 'secret', authorization: 'Bearer private-token', product_url: 'https://shop.example/private' });
  await tick(); const tracks = r.tracks(); assert.equal(tracks.length, 3);
  assert.deepEqual(tracks[0].properties, tracks[1].properties); assert.deepEqual(tracks[1].properties, tracks[2].properties);
  const properties = tracks[0].properties;
  assert.match(properties.event_id, /^[0-9a-f-]{36}$/); assert.ok(Date.parse(properties.occurred_at));
  assert.equal(properties.schema_version, 1); assert.equal(properties.environment, 'test'); assert.equal(properties.path, '/search');
  assert.ok(!JSON.stringify(tracks).includes('private')); assert.ok(!JSON.stringify(tracks).includes('secret'));
});

test('schema field values cannot smuggle arbitrary text or URL paths', async () => {
  const r = runtime(); r.analytics.reconcileAnonymous(); r.globals.window.location.pathname = '/product/private@example.test';
  r.analytics.trackEvent('product_viewed', { product_id: 'https://private.example', category: 'private user prompt', is_demo: true });
  await tick(); for (const event of r.tracks()) {
    assert.equal(event.properties.path, '/product/[id]'); assert.ok(!('product_id' in event.properties)); assert.ok(!('category' in event.properties));
  }
});

const sensitive = {
  email: 'private@example.test', password: 'private-password', authorization: 'Bearer private-jwt',
  $current_url: 'https://buywise.test/search?q=private-prompt&url=https://shop.test/private',
  $initial_current_url: 'https://buywise.test/search?q=private-query',
  $referrer: 'https://search.test/?q=private-query', $referring_domain: 'private.example',
  $initial_referrer: 'https://shop.test/private', $initial_referring_domain: 'private.example',
  mp_keyword: 'private-query', ph_keyword: 'private-query', utm_campaign: 'private-campaign', utm_term: 'private@example.test',
  $initial_utm_source: 'private-source', $session_entry_utm_term: 'private-prompt',
  unknown_future_field: { content: 'private-chat', token: 'private-token' },
};

test('PostHog realistic envelope filters properties, top-level/nested person and initial-person properties', async () => {
  const r = runtime(); r.analytics.reconcileAnonymous(); await tick();
  const event = {
    uuid: ANON, event: '$identify', timestamp: new Date(), leaked_envelope_field: 'private',
    properties: { ...sensitive, distinct_id: USER_A, $device_id: ANON, $process_person_profile: true, $browser: 'Chrome', $screen_width: 1440,
      $set: { ...sensitive, role: 'user' }, $set_once: { ...sensitive, signup_date: '2026-10-15' } },
    $set: { ...sensitive, role: 'user', is_verified: true }, $set_once: { ...sensitive, signup_date: '2026-10-15' },
  };
  const safe = r.configs.posthog.before_send(event);
  assert.ok(!JSON.stringify(safe).includes('private'));
  assert.equal(safe.$set.role, 'user'); assert.equal(safe.$set_once.signup_date, '2026-10-15');
  assert.equal(safe.properties.$set.role, 'user'); assert.equal(safe.properties.$browser, 'Chrome'); assert.equal(safe.properties.$screen_width, 1440);
  assert.equal(safe.properties.distinct_id, USER_A); assert.equal(safe.properties.$process_person_profile, true);
  assert.equal(r.configs.posthog.save_referrer, false); assert.equal(r.configs.posthog.save_campaign_params, false);
});

test('PostHog custom properties are restricted to that event schema, and automatic events are dropped', async () => {
  const r = runtime(); r.analytics.reconcileAnonymous(); await tick();
  const safe = r.configs.posthog.before_send({ uuid: ANON, event: 'search_submitted', properties: { ...sensitive, query_length: 9, query_type: 'text', is_demo: true, product_id: 'p1' } });
  assert.equal(safe.properties.query_length, 9); assert.ok(!('product_id' in safe.properties)); assert.ok(!JSON.stringify(safe).includes('private'));
  assert.equal(r.configs.posthog.before_send({ uuid: ANON, event: '$autocapture', properties: sensitive }), null);
});

test('Mixpanel filters attribution and arbitrary metadata on normal, internal skip-hooks identify, and people paths', async () => {
  const r = runtime(); r.analytics.reconcileAnonymous(); await tick(); const config = r.configs.mixpanel;
  assert.equal(config.track_marketing, false); assert.equal(config.store_google, false); assert.equal(config.save_referrer, false);
  assert.equal(config.batch_requests, false); // Orphaned SDK batches bypass before-send hooks.
  const event = { event: 'search_submitted', properties: { ...sensitive, token: 'public-mixpanel-key', distinct_id: ANON, query_length: 5, query_type: 'text', is_demo: true, $browser: 'Chrome' } };
  const safe = config.hooks.before_send_events(event);
  assert.ok(!JSON.stringify(safe).includes('private')); assert.equal(safe.properties.$browser, 'Chrome'); assert.equal(safe.properties.token, 'public-mixpanel-key');
  const identify = config.hooks.on_track('$identify', { ...sensitive, distinct_id: USER_A, $anon_distinct_id: ANON });
  assert.ok(!JSON.stringify(identify).includes('private')); assert.equal(identify[1].$anon_distinct_id, ANON);
  const people = config.hooks.before_send_people({ $distinct_id: USER_A, ...sensitive, $set: { ...sensitive, role: 'user', $browser: 'Chrome' }, $set_once: sensitive });
  assert.ok(!JSON.stringify(people).includes('private')); assert.equal(people.$set.role, 'user');
});

test('Amplitude disables remote config/diagnostics and verifies effective capture flags', async () => {
  const r = runtime(); r.analytics.reconcileAnonymous(); await tick();
  const config = r.configs.amplitude;
  assert.equal(config.autocapture, false); assert.equal(config.defaultTracking, false);
  assert.equal(config.fetchRemoteConfig, false); assert.equal(config.remoteConfig.fetchRemoteConfig, false); assert.equal(config.enableDiagnostics, false);
  await assert.rejects(r.plugin().setup({ ...config, autocapture: { formInteractions: true, pageUrlEnrichment: true } }), /Unsafe Amplitude/);
  assert.equal(await r.plugin().execute({ event_type: '[Amplitude] Form Submitted', event_properties: sensitive }), null);
});

test('Amplitude sanitizes custom, native, and person payloads, including persisted retry events', async () => {
  const r = runtime(); r.analytics.reconcileAnonymous(); await tick();
  const raw = { event_type: 'search_submitted', user_id: USER_A, device_id: ANON, user_agent: 'private-agent', extra: sensitive,
    event_properties: { ...sensitive, query_length: 9, query_type: 'text', is_demo: true },
    user_properties: { $set: { ...sensitive, role: 'user' }, $setOnce: { ...sensitive, signup_date: '2026-10-15' } } };
  const safe = await r.plugin().execute(raw); assert.ok(!JSON.stringify(safe).includes('private'));
  assert.equal(safe.user_id, USER_A); assert.equal(safe.user_properties.$set.role, 'user');
  r.storage.setItem('AMP_unsent_test', JSON.stringify([raw, { event_type: '$autocapture', event_properties: sensitive }]));
  const stored = await r.configs.amplitude.storageProvider.get('AMP_unsent_test');
  assert.equal(stored.length, 1); assert.ok(!JSON.stringify(stored).includes('private'));
  await r.configs.amplitude.storageProvider.set('AMP_unsent_test', [raw]);
  assert.ok(!r.storage.getItem('AMP_unsent_test').includes('private'));
});

test('installed Amplitude SDK honors the remote/capture lockdown without fetching remote settings', async () => {
  const sdk = require('@amplitude/analytics-browser'); const instance = sdk.createInstance();
  const r = runtime(); r.analytics.reconcileAnonymous(); await tick();
  const originalFetch = globalThis.fetch; let fetches = 0, observed;
  globalThis.fetch = async () => { fetches++; throw Error('No network allowed in this test'); };
  try {
    await instance.init('public-sdk-regression-key', { ...r.configs.amplitude, optOut: true, identityStorage: 'none', logLevel: 0 }).promise;
    await instance.add({ name: 'verify-effective-lockdown', type: 'enrichment', setup: async config => {
      observed = config; await r.plugin().setup(config);
    }, execute: async event => event }).promise;
    assert.equal(observed.autocapture, false); assert.equal(observed.defaultTracking, false);
    assert.equal(observed.remoteConfig.fetchRemoteConfig, false); assert.equal(fetches, 0);
  } finally {
    globalThis.fetch = originalFetch;
    await instance.remove('amplitude').promise;
  }
});

test('installed Mixpanel SDK filters internal skip-hooks events and actual people envelopes before transport', async () => {
  const mixpanel = require('mixpanel-browser');
  const r = runtime(); r.analytics.reconcileAnonymous(); await tick();
  const instance = mixpanel.init('public-mixpanel-key', { ...r.configs.mixpanel, api_payload_format: 'json' }, 'buywise_p0_regression');
  const outbound = [];
  instance._send_request = (_url, body) => { outbound.push(JSON.parse(body.data)); return true; };
  instance.register({ ...sensitive });
  instance.identify(USER_A); // The real SDK uses skip_hooks for its internal identify.
  instance.people.set({ ...sensitive, role: 'user' });
  instance.track('search_submitted', { ...sensitive, query_length: 7, query_type: 'text', is_demo: true });
  const before = outbound.length;
  instance.track('$unapproved_internal_event', { ...sensitive }, { skip_hooks: true });
  assert.equal(outbound.length, before);
  assert.ok(outbound.some(event => event.event === '$identify'));
  assert.ok(outbound.some(event => event.$set?.role === 'user'));
  assert.ok(!JSON.stringify(outbound).includes('private'));
});
