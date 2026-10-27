/* eslint-disable @typescript-eslint/no-require-imports -- Node render tests. */
const { test } = require('node:test');
const assert = require('node:assert/strict');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const { loader } = require('./helpers.cjs');
const DataBadge = loader({}, {
  'react/jsx-runtime': require('react/jsx-runtime'),
  'lucide-react': { FlaskConical: () => null, Radio: () => null },
}).load('components/ui/DataBadge.tsx').default;

test('catalogue recovery is labelled saved, not live data', () => {
  const html = renderToStaticMarkup(React.createElement(DataBadge, { meta: {
    is_demo: false, data_mode: 'live', catalog_fallback: true,
  } }));
  assert.ok(html.includes('Saved results'));
  assert.ok(html.includes('prices may have changed'));
  assert.ok(!html.includes('Live data'));
});

test('ordinary cached provider results and demo results keep their own labels', () => {
  const render = meta => renderToStaticMarkup(React.createElement(DataBadge, { meta }));
  assert.ok(render({ is_demo: false, data_mode: 'live', cached: true }).includes('Live data'));
  assert.ok(render({ is_demo: true, data_mode: 'demo', catalog_fallback: true }).includes('Demo data'));
});
