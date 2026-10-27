/* eslint-disable @typescript-eslint/no-require-imports -- Node render tests. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { loader } = require('./helpers.cjs');

const mocks = {
  react: React,
  'react/jsx-runtime': require('react/jsx-runtime'),
  'next/link': { __esModule: true, default: ({ children, ...props }) => React.createElement('a', props, children) },
  'next/navigation': { usePathname: () => '/product/example' },
  'lucide-react': new Proxy({}, { get: () => () => null }),
  '@/lib/api': { api: { plans: async () => [] } },
  '@/lib/analytics': { track() {} },
  '@/lib/utils': { formatPrice: value => `₹${value}`, getTrustColor: () => '', matchBadgeClass: () => '', formatRelativeTime: () => 'today' },
  '@/components/trust/VerificationBadge': { __esModule: true, default: () => null },
};
const LockedPanel = loader({}, mocks).load('components/product/LockedPanel.tsx').default;
const OffersTable = loader({}, { ...mocks, '@/components/product/LockedPanel': { __esModule: true, default: LockedPanel } }).load('components/product/OffersTable.tsx').default;
const offer = {
  id: 'offer-visible', retailer: { id: 'retailer-visible', name: 'Visible store' },
  go_url: 'https://visible.example/product', currency: 'INR', condition: 'new', availability: 'in_stock',
  price: { listed_price: 1200, estimated_final_price: 1200, final_price_known: false },
  match: { match_type: 'exact_match', label: 'Exact match', confidence: 1, reasons: [] },
  trust: { score: null, verification: 'unverified' },
};
function render(comparison) {
  return renderToStaticMarkup(React.createElement(OffersTable, { comparison: { product_id: 'example', picks: [], ...comparison } }));
}

test('locked pick placeholders appear above usable preview offers', () => {
  const html = render({ locked: true, offers: [offer], hidden_offers: 4, hidden_retailers: 3, locked_pick_categories: ['BEST_OVERALL', 'CHEAPEST'] });
  assert.ok(html.indexOf('Best overall') < html.indexOf('Free preview offers'));
  assert.ok(html.includes('blur-[5px]') && html.includes('aria-hidden="true"'));
  assert.ok(html.includes('Visible store') && html.includes('₹1200'));
  assert.ok(html.includes('href="https://visible.example/product"'));
  assert.ok(html.includes('4 offers across 3 retailers'));
  assert.ok(html.includes('returnTo=%2Fproduct%2Fexample'));
  assert.equal(html.match(/Unlock with Pro/g).length, 1);
  assert.ok(!html.includes('Highest trust score')); // No fabricated pick category.
});

test('no eligible preview still shows the locked offers and honest empty state', () => {
  const html = render({ locked: true, offers: [], hidden_offers: 1, locked_pick_categories: ['CHEAPEST'] });
  assert.ok(html.includes('Lowest price') && html.includes('Unlock with Pro'));
  assert.ok(html.includes('No free preview offers for this product yet'));
  assert.ok(!html.includes('<table') && !html.includes('₹'));
});

test('paid comparison has working retailer links and no preview upsell', () => {
  const html = render({ locked: false, offers: [offer] });
  assert.ok(html.includes('Visible store') && html.includes('₹1200'));
  assert.ok(!html.includes('Unlock with Pro') && !html.includes('Free preview offers'));
});
