'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { DiagnosticsController } = require('../../src/controller');

// Manual clock and jobs allow explicit control over completion order.
function setup({ trusted = true, enabled = true } = {}) {
  const state = {
    trusted, enabled, timers: [], runs: [], published: new Map(), reports: [], versions: new Map(),
  };
  const host = {
    isTrusted: () => state.trusted,
    isEnabled: () => state.enabled,
    version: (key) => state.versions.get(key),
    run: (text, signal) => new Promise((resolve) => {
      const run = { text, signal, resolve };
      signal.addEventListener('abort', () => resolve({ status: 'cancelled' }));
      state.runs.push(run);
    }),
    publish: (doc, error) => state.published.set(doc.key, error),
    clear: (key) => state.published.delete(key),
    report: (code, detail) => state.reports.push([code, detail]),
    setTimer: (fn) => { state.timers.push({ fn, active: true }); return state.timers.length - 1; },
    clearTimer: (id) => { state.timers[id].active = false; },
  };
  const controller = new DiagnosticsController(host, { debounceMs: 250 });
  const fire = () => state.timers.forEach((t) => { if (t.active) { t.active = false; t.fn(); } });
  const doc = (key, version, text = 'x') => { state.versions.set(key, version); return { key, version, text: () => text }; };
  return { state, controller, fire, doc };
}
const tick = () => new Promise((r) => setImmediate(r));
const err = (message) => ({ kind: 'syntax', line: 1, column: 1, message });

test("debounce: repeated edits cancel previous timers", () => {
  const { state, controller, fire, doc } = setup();
  controller.schedule(doc('a', 1));
  controller.schedule(doc('a', 2));
  fire();
  assert.strictEqual(state.runs.length, 1);
});

test("stale job results cannot replace newer results", async () => {
  const { state, controller, fire, doc } = setup();
  controller.schedule(doc('a', 1));
  fire();
  controller.schedule(doc('a', 2));
  assert.strictEqual(state.runs[0].signal.aborted, true);
  fire();
  state.runs[0].resolve({ status: 'error', error: err('стара') }); // late response from the first job
  await tick();
  assert.strictEqual(state.published.has('a'), false);
  state.runs[1].resolve({ status: 'error', error: err('нова') });
  await tick();
  assert.strictEqual(state.published.get('a').message, 'нова');
});

test("valid documents clear diagnostics", async () => {
  const { state, controller, doc } = setup();
  controller.flush(doc('a', 1));
  state.runs[0].resolve({ status: 'error', error: err('помилка') });
  await tick();
  assert.ok(state.published.get('a'));
  controller.flush(doc('a', 2));
  state.runs[1].resolve({ status: 'ok' });
  await tick();
  assert.strictEqual(state.published.get('a'), null);
});

test("close cancels jobs/timers and ignores late responses", async () => {
  const { state, controller, fire, doc } = setup();
  controller.schedule(doc('a', 1));
  controller.close('a');
  fire();
  assert.strictEqual(state.runs.length, 0);
  controller.flush(doc('a', 1));
  controller.close('a');
  assert.strictEqual(state.runs[0].signal.aborted, true);
  state.versions.delete('a');
  state.runs[0].resolve({ status: 'error', error: err('привид') });
  await tick();
  assert.strictEqual(state.published.has('a'), false);
});

test("reopening the same URI cannot revive a stale error", async () => {
  const { state, controller, doc } = setup();
  controller.flush(doc('a', 1));
  controller.close('a');
  controller.flush(doc('a', 1)); // reopened with the same document version
  state.runs[0].resolve({ status: 'error', error: err('стара') });
  await tick();
  assert.strictEqual(state.published.has('a'), false);
  state.runs[1].resolve({ status: 'ok' });
  await tick();
  assert.strictEqual(state.published.get('a'), null);
});

test("document version changes discard old results", async () => {
  const { state, controller, doc } = setup();
  controller.flush(doc('a', 1));
  state.versions.set('a', 2);
  state.runs[0].resolve({ status: 'error', error: err('x') });
  await tick();
  assert.strictEqual(state.published.has('a'), false);
});

test("untrusted workspace: no Python launch and diagnostics cleared", async () => {
  const { state, controller, fire, doc } = setup({ trusted: false });
  state.published.set('a', err('залишок'));
  controller.schedule(doc('a', 1));
  controller.flush(doc('a', 1));
  fire();
  assert.strictEqual(state.runs.length, 0);
  assert.strictEqual(state.published.has('a'), false);
});

test("granting trust checks open documents; losing trust clears diagnostics", async () => {
  const { state, controller, doc } = setup({ trusted: false });
  const d = doc('a', 1);
  controller.refreshAll([d]);
  assert.strictEqual(state.runs.length, 0);
  state.trusted = true;
  controller.refreshAll([d]);
  assert.strictEqual(state.runs.length, 1);
  state.trusted = false;
  controller.refreshAll([d]);
  assert.strictEqual(state.runs[0].signal.aborted, true);
});

test("disabled diagnostics do not launch Python", () => {
  const { state, controller, doc } = setup({ enabled: false });
  controller.flush(doc('a', 1));
  assert.strictEqual(state.runs.length, 0);
});

test("environment failure: no underlines, one report, no repeated launches", async () => {
  const { state, controller, fire, doc } = setup();
  state.published.set('a', err('залишок'));
  controller.flush(doc('a', 1));
  state.runs[0].resolve({ status: 'fatal', code: 'spawn', detail: 'ENOENT' });
  await tick();
  assert.strictEqual(state.published.has('a'), false);
  controller.schedule(doc('a', 2));
  controller.schedule(doc('a', 3));
  fire();
  assert.strictEqual(state.runs.length, 1);
  assert.deepStrictEqual(state.reports, [['spawn', 'ENOENT']]);
  controller.refreshAll([doc('a', 3)]); // settings changed
  assert.strictEqual(state.runs.length, 2);
});

test("timeout allows future checks without repeated warnings", async () => {
  const { state, controller, doc } = setup();
  controller.flush(doc('a', 1));
  state.runs[0].resolve({ status: 'fatal', code: 'timeout', detail: '' });
  await tick();
  controller.flush(doc('a', 2));
  state.runs[1].resolve({ status: 'fatal', code: 'timeout', detail: '' });
  await tick();
  assert.strictEqual(state.reports.length, 1);
});

test("dispose cancels work and clears diagnostics", async () => {
  const { state, controller, fire, doc } = setup();
  controller.schedule(doc('b', 1));
  controller.flush(doc('a', 1));
  state.published.set('a', err('x'));
  controller.dispose();
  fire();
  assert.strictEqual(state.runs[0].signal.aborted, true);
  assert.strictEqual(state.published.size, 0);
  state.runs[0].resolve({ status: 'error', error: err('після dispose') });
  await tick();
  assert.strictEqual(state.published.size, 0);
  controller.schedule(doc('c', 1));
  assert.strictEqual(state.timers.length, 1); // no new timers
});

test("document-dependent output failures allow later edits and other files", async () => {
  for (const code of ['output', 'request', 'recursion', 'timeout']) {
    const { state, controller, doc } = setup();
    controller.flush(doc('a', 1));
    state.runs[0].resolve({ status: 'fatal', code, detail: 'завеликий' });
    await tick();
    assert.strictEqual(controller.environmentBroken, false, code);
    assert.strictEqual(state.reports.length, 1);
    controller.flush(doc('a', 2));
    controller.flush(doc('b', 1));
    assert.strictEqual(state.runs.length, 3, code);
    state.runs[1].resolve({ status: 'error', error: err('x') });
    state.runs[2].resolve({ status: 'error', error: err('y') });
    await tick();
    assert.strictEqual(state.published.get('a').message, 'x');
    assert.strictEqual(state.published.get('b').message, 'y');
    controller.flush(doc('a', 3));
    state.runs[3].resolve({ status: 'fatal', code, detail: 'знову' });
    await tick();
    assert.strictEqual(state.reports.length, 1, 'without repeated warnings');
  }
});

test("import failure disables checking until refreshAll", async () => {
  const { state, controller, doc } = setup();
  controller.flush(doc('a', 1));
  state.runs[0].resolve({ status: 'fatal', code: 'import', detail: 'x' });
  await tick();
  controller.flush(doc('a', 2));
  assert.strictEqual(state.runs.length, 1);
});
