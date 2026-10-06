'use strict';
// Verify the bridge against real parser fixtures and exact source positions.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');
const { runBridge } = require('../../src/runner');

const root = path.resolve(__dirname, '..', '..', '..');
const script = path.resolve(__dirname, '..', '..', 'backend', 'bazar_bridge.py');
const python = process.env.BAZAR_PYTHON || 'python3';
const counterFile = path.join(os.tmpdir(), `bazar-bridge-counter-${process.pid}.sqlite3`);

function bridge(text) {
  const out = execFileSync(python, ['-I', script], {
    input: JSON.stringify({ text }),
    env: { ...process.env, BAZAR_FAILURE_COUNTER_FILE: counterFile },
  });
  return JSON.parse(out.toString('utf8'));
}

const decoder = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });
const files = (dir) => fs.readdirSync(dir).filter((f) => f.endsWith('.bazar')).sort().map((f) => path.join(dir, f));

test("all valid fixtures and examples parse successfully", () => {
  const sources = [...files(path.join(root, 'tests', 'valid')), ...files(path.join(root, 'examples'))];
  assert.ok(sources.length >= 40);
  for (const file of sources) {
    assert.deepStrictEqual(bridge(decoder.decode(fs.readFileSync(file))), { ok: true }, file);
  }
});

test("invalid fixtures retain exact .err messages and positions", () => {
  let compared = 0;
  let skipped = 0;
  for (const file of files(path.join(root, 'tests', 'invalid'))) {
    const bytes = fs.readFileSync(file);
    let text;
    try {
      text = decoder.decode(bytes);
    } catch (error) {
      skipped += 1; // malformed raw UTF-8 cannot be represented as JSON text
      continue;
    }
    const expected = fs.readFileSync(file.replace(/\.bazar$/, '.err'), 'utf8')
      .match(/^compilation error: line (\d+):(\d+): ([^\n]*)\n$/);
    assert.ok(expected, file);
    const result = bridge(text);
    assert.strictEqual(result.ok, false, file);
    assert.deepStrictEqual(
      [result.error.line, result.error.column, result.error.message],
      [Number(expected[1]), Number(expected[2]), expected[3]],
      path.basename(file),
    );
    compared += 1;
  }
  assert.ok(compared >= 90, `only ${compared} fixtures compared`);
  assert.ok(skipped <= 10);
});

test("bridge does not create or modify failure counter state", () => {
  bridge('зуб даю x\n');
  bridge('зуб даю x тіпа дрібняк це 1\n');
  assert.strictEqual(fs.existsSync(counterFile), false);
});

test("lone surrogate reports a lexical error at its byte position", () => {
  const result = bridge('базарь \ud800\n');
  assert.strictEqual(result.ok, false);
  assert.strictEqual(result.error.kind, 'lex');
  assert.strictEqual(result.error.line, 1);
  assert.strictEqual(result.error.column, 14);
});

test("error kind distinguishes lexical and syntax errors", () => {
  assert.strictEqual(bridge('зуб даю 1\n').error.kind, 'syntax');
  assert.strictEqual(bridge('чутки без двокрапки\n').error.kind, 'lex');
});

test("runBridge: success, diagnostic, missing Python, timeout, and cancellation", async () => {
  assert.deepStrictEqual(await runBridge({ python, script, text: 'базарь 1\n' }), { status: 'ok' });
  const bad = await runBridge({ python, script, text: 'базарь\n' });
  assert.strictEqual(bad.status, 'error');
  assert.strictEqual(bad.error.line, 1);
  const missing = await runBridge({ python: '/нема/такого/python', script, text: 'x' });
  assert.deepStrictEqual([missing.status, missing.code], ['fatal', 'spawn']);

  const sleeper = path.join(os.tmpdir(), `bazar-sleep-${process.pid}.py`);
  fs.writeFileSync(sleeper, 'import time\ntime.sleep(30)\n');
  const slow = await runBridge({ python, script: sleeper, text: 'x', timeoutMs: 300 });
  assert.deepStrictEqual([slow.status, slow.code], ['fatal', 'timeout']);

  const controller = new AbortController();
  const pending = runBridge({ python, script: sleeper, text: 'x', signal: controller.signal });
  setTimeout(() => controller.abort(), 100);
  assert.deepStrictEqual(await pending, { status: 'cancelled' });

  fs.writeFileSync(sleeper, 'print("not json")\n');
  const garbage = await runBridge({ python, script: sleeper, text: 'x' });
  assert.deepStrictEqual([garbage.status, garbage.code], ['fatal', 'json']);

  fs.writeFileSync(sleeper, 'import sys\nsys.stdout.write("x" * 200000)\n');
  const huge = await runBridge({ python, script: sleeper, text: 'x' });
  assert.deepStrictEqual([huge.status, huge.code], ['fatal', 'output']);
  fs.rmSync(sleeper);
});
