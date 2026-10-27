/* eslint-disable @typescript-eslint/no-require-imports -- Node test harness. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { USER_A, USER_B, ANON, user, tick, loader, runtime } = require('./helpers.cjs');

const retailerUrl = 'https://retailer.example/private-product?token=private-token';
const expected = { product_id: USER_A, retailer_id: USER_B, offer_id: ANON, price: 24999, currency: 'INR', source: 'comparison' };
const jsx = (type, props) => ({ type, props });
function visitLinks(node) {
  if (Array.isArray(node)) return node.flatMap(visitLinks);
  if (!node || typeof node !== 'object') return [];
  return [
    ...(node.type === 'a' && node.props.href === retailerUrl ? [node] : []),
    ...visitLinks(node.props?.children),
  ];
}

for (const component of ['OffersTable', 'FamilyPanel']) {
  for (const is_demo of [false, true]) {
    test(`${component} retailer click emits retailer_clicked once to every provider (${is_demo ? 'demo' : 'live'})`, async () => {
      const r = runtime();
      r.analytics.identifyUser(user());
      const ga = [];
      r.globals.window.gtag = (...args) => ga.push(args);
      r.globals.process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID = 'G-TEST';
      const bridge = r.load('lib/analytics.ts');
      const Component = loader({}, {
        react: { useState: initial => [typeof initial === 'function' ? initial() : initial, () => {}] },
        'react/jsx-runtime': { jsx, jsxs: jsx, Fragment: 'fragment' },
        'next/link': { default: 'link' },
        'lucide-react': {},
        '@/lib/analytics': bridge,
        '@/lib/utils': { formatPrice: value => String(value), getTrustColor: () => '', matchBadgeClass: () => '', formatRelativeTime: () => '' },
        '@/lib/specs': { specSummary: () => [] },
        '@/components/trust/VerificationBadge': { default: 'badge' },
        '@/components/product/LockedPanel': { default: 'locked-panel' },
      }).load(`components/product/${component}.tsx`).default;
      const offer = {
        id: ANON, offer_id: ANON, product_id: USER_A, retailer_id: USER_B,
        retailer: { id: USER_B, name: 'private-retailer-name' }, retailer_name: 'private-retailer-name',
        go_url: retailerUrl, currency: 'INR', condition: 'new', availability: 'in_stock', is_demo,
        match: { match_type: 'exact_match', label: 'Exact', confidence: 1, reasons: [] },
        trust: { score: null, verification: 'unverified' },
      };
      const props = component === 'OffersTable'
        ? { comparison: { product_id: USER_A, picks: [], offers: [{ ...offer, price: { listed_price: 24000, estimated_final_price: expected.price, shipping_known: true, final_price_known: true } }] } }
        : { family: { label: 'Test family', variants: [{ label: 'Standard', storage: null, offer_count: 1, colors: [], offers: [{ ...offer, price: expected.price }] }], total_retailers: 1, total_offers: 1 } };
      const links = visitLinks(Component(props));
      assert.equal(links.length, 1);
      links[0].props.onClick(); // Execute the actual component's retailer-link handler.
      await tick();
      const tracks = r.tracks();
      assert.equal(tracks.length, 3);
      assert.deepEqual(tracks.map(e => e.provider).sort(), ['amplitude', 'mixpanel', 'posthog']);
      for (const event of tracks) {
        assert.equal(event.event, 'retailer_clicked');
        assert.equal(event.userId, USER_A);
        for (const [key, value] of Object.entries({ ...expected, is_demo })) assert.equal(event.properties[key], value);
        assert.match(event.properties.event_id, /^[0-9a-f-]{36}$/);
        assert.ok(Date.parse(event.properties.occurred_at));
        assert.equal(event.properties.environment, 'test');
        assert.equal(event.properties.path, '/search');
        assert.equal(event.properties.schema_version, 1);
        assert.deepEqual(event.properties, tracks[0].properties);
      }
      assert.ok(!JSON.stringify(tracks).includes('private'));
      assert.equal(ga.length, 1);
      assert.equal(ga[0][1], 'retailer_clicked');
      assert.ok(!JSON.stringify(ga).includes('private'));
      assert.ok(!fs.readFileSync(path.join(__dirname, `../src/components/product/${component}.tsx`), 'utf8').includes('"retailer_click"'));
    });
  }
}

test('retailer bridge excludes raw URLs and sensitive text from all product providers', async () => {
  const r = runtime();
  r.analytics.reconcileAnonymous();
  r.load('lib/analytics.ts').track('retailer_clicked', {
    ...expected, is_demo: false, url: retailerUrl, retailer: 'private-retailer-name',
    email: 'private@example.invalid', search_term: 'private-query', prompt: 'private-prompt',
  });
  await tick();
  assert.equal(r.tracks().length, 3);
  assert.ok(!JSON.stringify(r.tracks()).includes('private'));
  assert.ok(r.tracks().every(e => e.event === 'retailer_clicked'));
});
