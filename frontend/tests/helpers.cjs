/* eslint-disable @typescript-eslint/no-require-imports -- Node test harness. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const { randomUUID } = require('node:crypto');
const USER_A = '11111111-1111-4111-8111-111111111111';
const USER_B = '22222222-2222-4222-8222-222222222222';
const ANON = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const user = (id = USER_A) => ({ id, created_at: '2026-10-15T00:00:00Z', role: 'user', is_verified: true });
const response = (id = USER_A) => ({ access_token: `app-token-${id}`, refresh_token: 'refresh-private', token_type: 'bearer', user: user(id) });
const tick = () => new Promise(resolve => setImmediate(resolve));
const plain = value => JSON.parse(JSON.stringify(value));
function deferred() { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; }
function loader(globals = {}, mocks = {}) {
  const cache = new Map(), imports = [];
  function load(file) {
    const full = path.resolve(__dirname, '../src', file);
    if (cache.has(full)) return cache.get(full);
    const exports = {}; cache.set(full, exports);
    const code = ts.transpileModule(fs.readFileSync(full, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
    vm.runInNewContext(code, { exports, AbortController, setTimeout, clearTimeout, crypto: { randomUUID }, process: { env: {} }, ...globals, require(name) {
      imports.push(name);
      if (Object.hasOwn(mocks, name)) return mocks[name];
      if (name.startsWith('.')) {
        const base = path.resolve(path.dirname(full), name);
        const target = [base + '.ts', base + '.tsx', path.join(base, 'index.ts')].find(p => fs.existsSync(p));
        if (target) return load(target);
      }
      throw new Error(`Unexpected import: ${name}`);
    } }, { filename: full });
    return exports;
  }
  return { load, imports };
}
function runtime({ token, initialUser, enabled = true, keys = ['mixpanel', 'posthog', 'amplitude'], fetch, browser = true } = {}) {
  const values = new Map(token ? [['buywise_token', token]] : []);
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
  const logs = [], configs = {}, states = {};
  const statesFor = provider => states[provider] = { userId: initialUser, anonymousId: ANON, resets: 0, inits: 0 };
  const snapshot = (provider, event, properties, kind = 'track') => logs.push({ provider, event, properties: plain(properties), userId: states[provider].userId, anonymousId: states[provider].anonymousId, kind });
  const reset = provider => { const state = states[provider]; state.userId = undefined; state.anonymousId = randomUUID(); state.resets++; };
  const mix = statesFor('mixpanel'), post = statesFor('posthog'), amp = statesFor('amplitude');
  let plugin;
  const sdks = {
    'mixpanel-browser': {
      init: (_, config) => { configs.mixpanel = config; mix.inits++; },
      get_property: key => key === '$user_id' ? mix.userId : undefined,
      identify: id => { mix.userId = id; snapshot('mixpanel', '$identify', {}, 'identify'); },
      people: { set: properties => snapshot('mixpanel', '$set', properties, 'person') },
      reset: () => reset('mixpanel'),
      track: (event, properties) => snapshot('mixpanel', event, properties),
    },
    'posthog-js': {
      init: (_, config) => { configs.posthog = config; post.inits++; },
      get_property: key => key === '$user_id' ? post.userId : key === '$user_state' && post.userId ? 'identified' : undefined,
      identify: (id, properties) => { post.userId = id; snapshot('posthog', '$identify', properties, 'identify'); },
      reset: () => reset('posthog'),
      capture: (event, properties) => snapshot('posthog', event, properties),
    },
    '@amplitude/analytics-browser': {
      init: (_, config) => { configs.amplitude = config; amp.inits++; return { promise: Promise.resolve() }; },
      add: p => { plugin = p; return { promise: p.setup(configs.amplitude) }; },
      getUserId: () => amp.userId,
      setUserId: id => { amp.userId = id; snapshot('amplitude', '$identify', {}, 'identify'); },
      Identify: class { constructor() { this.properties = {}; } set(key, value) { this.properties[key] = value; } },
      identify: identify => snapshot('amplitude', '$set', identify.properties, 'person'),
      reset: () => reset('amplitude'),
      track: (event, properties) => snapshot('amplitude', event, properties),
    },
  };
  const env = { NODE_ENV: 'test', NEXT_PUBLIC_ANALYTICS_ENABLED: enabled ? 'true' : 'false' };
  if (keys.includes('mixpanel')) env.NEXT_PUBLIC_MIXPANEL_TOKEN = 'public-mixpanel-key';
  if (keys.includes('posthog')) env.NEXT_PUBLIC_POSTHOG_KEY = 'public-posthog-key';
  if (keys.includes('amplitude')) env.NEXT_PUBLIC_AMPLITUDE_API_KEY = 'public-amplitude-key';
  const globals = { URLSearchParams, process: { env }, localStorage: storage, sessionStorage: storage, fetch: (...args) => fetch ? fetch(...args) : Promise.reject(new Error('Unexpected fetch')) };
  if (browser) globals.window = { location: { pathname: '/search', search: '', origin: 'https://www.buywise.co.in' }, addEventListener() {}, removeEventListener() {} };
  const modules = loader(globals, sdks);
  const analytics = modules.load('lib/product-analytics/index.ts');
  return { ...modules, analytics, api: () => modules.load('lib/api.ts').api, privacy: () => modules.load('lib/product-analytics/privacy.ts'), logs, configs, states, storage, globals, plugin: () => plugin, tracks: () => logs.filter(entry => entry.kind === 'track') };
}
const ok = body => ({ ok: true, status: 200, json: async () => body });
const failure = status => ({ ok: false, status, json: async () => ({ detail: 'Request rejected' }) });
module.exports = { USER_A, USER_B, ANON, user, response, tick, plain, deferred, loader, runtime, ok, failure };
