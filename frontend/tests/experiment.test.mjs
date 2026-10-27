import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import ts from 'typescript';
function storage() {
  const values = new Map();
  return { getItem: k => values.get(k) ?? null, setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k) };
}
function load(file, globals = {}, imports = {}) {
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
  const context = { exports: {}, require: name => imports[name], ...globals };
  vm.runInNewContext(code, context);
  return context.exports;
}
function environment(mode='ab', search='') {
  return { process: { env: { NEXT_PUBLIC_HOMEPAGE_EXPERIMENT: mode } }, window: { location: { search } }, localStorage: storage(), sessionStorage: storage(), crypto: { getRandomValues: arr => { arr[0]=0; return arr; } }, URLSearchParams };
}
test('V2 is default; AB assignments persist across page reloads', () => {
  const env = environment('v2');
  assert.equal(load('src/lib/experiment.ts', env).assignExperiment().variant, 'b');
  env.process.env.NEXT_PUBLIC_HOMEPAGE_EXPERIMENT='ab';
  assert.equal(load('src/lib/experiment.ts', env).assignExperiment().variant, 'a');
  env.crypto.getRandomValues = arr => { arr[0]=1; return arr; };
  assert.equal(load('src/lib/experiment.ts', env).assignExperiment().variant, 'a');
});
test('both random buckets are reachable', () => {
  const env = environment();
  env.crypto.getRandomValues = arr => { arr[0]=1; return arr; };
  assert.equal(load('src/lib/experiment.ts', env).assignExperiment().variant, 'b');
});
test('previews persist through navigation, do not replace real assignment, and reset', () => {
  const env=environment();
  load('src/lib/experiment.ts',env).assignExperiment();
  env.window.location.search='?variant=b';
  assert.equal(load('src/lib/experiment.ts',env).assignExperiment().preview,true);
  env.window.location.search='';
  assert.equal(load('src/lib/experiment.ts',env).assignExperiment().variant,'b');
  env.window.location.search='?variant=reset';
  const result=load('src/lib/experiment.ts',env).assignExperiment();
  assert.equal(result.variant,'a'); assert.equal(result.preview,false);
});
test('blocked storage fails safely and excludes unstable participants', () => {
  const env=environment(); env.sessionStorage.getItem=()=>{throw new Error('blocked');};
  const result=load('src/lib/experiment.ts',env).assignExperiment();
  assert.equal(result.variant,'b'); assert.equal(result.preview,true);
});
test('return path rejects external URLs, backslashes and control characters', () => {
  const {safeReturnPath}=load('src/lib/oauth.ts',{}, {'./api':{}});
  for(const path of ['https://evil.test','//evil.test','/\\evil.test','/\nevil.test','/auth/callback',null]) assert.equal(safeReturnPath(path),'/dashboard');
  assert.equal(safeReturnPath('/product/123?tab=offers'),'/product/123?tab=offers');
});
test('analytics queues early exposure and strips query strings from page locations', () => {
  const env=environment(); env.process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID='G-TEST';
  Object.assign(env.window.location,{pathname:'/',origin:'https://buywise.test'}); env.document={title:'BuyWise'};
  const exp=load('src/lib/experiment.ts',env);
  const analytics=load('src/lib/analytics.ts',env,{'./experiment':exp});
  analytics.track('experiment_exposure');
  const calls=[]; env.window.gtag=(...args)=>calls.push(args);
  analytics.flushAnalytics();
  analytics.pageview('/search?q=private@example.com');
  assert.equal(calls[0][1],'experiment_exposure');
  assert.equal(calls[0][2].variant,'a');
  assert.equal(calls[1][2].page_location,'https://buywise.test/search');
  assert.equal(calls[1][2].page_path,'/search');
});
test('preview and callback traffic never sends custom analytics', () => {
  for(const [search,pathname] of [['?variant=b','/'],['','/auth/callback']]) {
    const env=environment('ab',search); env.process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID='G-TEST';
    Object.assign(env.window.location,{pathname,origin:'https://buywise.test'});
    const calls=[]; env.window.gtag=(...args)=>calls.push(args);
    const exp=load('src/lib/experiment.ts',env);
    const analytics=load('src/lib/analytics.ts',env,{'./experiment':exp});
    analytics.track('login'); assert.equal(calls.length,0);
  }
});
