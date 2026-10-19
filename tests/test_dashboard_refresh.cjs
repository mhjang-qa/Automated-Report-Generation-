const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/app.js', 'utf8');
const functions = source.slice(source.indexOf('async function loadDefectDashboard('), source.indexOf('async function loadLocalizationApp('));
function boot(fetchImpl, timeStep = 1) {
  let now = 1000;
  const state = { defectDashboardUrl: 'https://notion-daily-defect-dashboard.onrender.com/?existing=1', defectDashboardEmbedUrl: 'https://notion-daily-defect-dashboard.onrender.com/embed/hanpass-renewal', defectDashboardWarmupToken: 0 };
  const el = { defectDashboardFrame: {src: ''}, defectDashboardOpenBtn: {}, defectDashboardEmbedBtn: {} };
  const context = { state, el, URL, Date: {now() {now += timeStep; return now;}}, fetch: fetchImpl, showDefectDashboardMessage() {}, FLOOR_RISE_LOADING_DURATION_MS: 0, setTimeout: cb => cb() };
  vm.createContext(context); vm.runInContext(functions, context);
  return context;
}
const ready = async () => ({ok: true, json: async () => ({status: 'ok'})});
test('initial iframe and new-tab link use fresh URLs and preserve existing query values', async () => {
  const c = boot(ready); await c.loadDefectDashboard();
  const first = c.el.defectDashboardFrame.src;
  const parsed = new URL(first);
  assert.ok(parsed.searchParams.get('_refresh'));
  assert.equal(parsed.searchParams.get('existing'), '1');
  assert.equal(c.el.defectDashboardOpenBtn.href, first);
  await c.loadDefectDashboard(true);
  assert.notEqual(c.el.defectDashboardFrame.src, first);
});
test('health timeout also loads the iframe with a fresh URL', async () => {
  const c = boot(ready, 100000); await c.warmUpDefectDashboard();
  assert.ok(new URL(c.el.defectDashboardFrame.src).searchParams.get('_refresh'));
  assert.equal(c.el.defectDashboardOpenBtn.href, c.el.defectDashboardFrame.src);
});
test('a superseded health response cannot replace a newer iframe', async () => {
  const responses = [];
  const c = boot(() => new Promise(resolve => responses.push(resolve)));
  const oldLoad = c.warmUpDefectDashboard();
  const newLoad = c.warmUpDefectDashboard();
  responses[1](await ready()); await newLoad;
  const latest = c.el.defectDashboardFrame.src;
  responses[0](await ready()); await oldLoad;
  assert.equal(c.el.defectDashboardFrame.src, latest);
});
