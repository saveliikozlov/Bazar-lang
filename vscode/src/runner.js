'use strict';
// Run the Python bridge without a shell; text uses stdin, with output/time limits.
// The Promise never rejects: all failures return { status: 'fatal' }.
const { spawn } = require('child_process');
const os = require('os');
const path = require('path');

const DEFAULT_TIMEOUT_MS = 10000;
const MAX_STDOUT = 64 * 1024;
const MAX_STDERR = 8 * 1024;

function runBridge({ python, script, text, timeoutMs = DEFAULT_TIMEOUT_MS, signal, spawnFn = spawn }) {
  return new Promise((resolve) => {
    let finished = false;
    let child = null;
    let timer = null;
    const finish = (result) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      if (signal) signal.removeEventListener('abort', onAbort);
      if (child && child.exitCode === null && !child.killed) child.kill();
      resolve(result);
    };
    const fatal = (code, detail) => finish({ status: 'fatal', code, detail });
    const onAbort = () => finish({ status: 'cancelled' });

    if (signal && signal.aborted) return finish({ status: 'cancelled' });
    if (signal) signal.addEventListener('abort', onAbort);

    // The bridge does not need CLI failure state. Even if future code touches it,
    // this fallback path cannot affect the personal state file.
    const env = {
      ...process.env,
      BAZAR_FAILURE_COUNTER_FILE: path.join(os.tmpdir(), 'bazar-vscode-no-counter', 'unused.sqlite3'),
      PYTHONUTF8: '1',
      PYTHONDONTWRITEBYTECODE: '1',
    };
    try {
      child = spawnFn(python, ['-I', script], {
        shell: false,
        stdio: ['pipe', 'pipe', 'pipe'],
        cwd: path.dirname(script),
        env,
        windowsHide: true,
      });
    } catch (error) {
      return fatal('spawn', error.message);
    }

    child.on('error', (error) => fatal('spawn', error.code ? `${error.code}: ${error.message}` : error.message));
    if (child.pid === undefined) return; // spawn failed; the error event reports the cause

    const out = [];
    let outSize = 0;
    let err = '';
    child.stdout.on('data', (chunk) => {
      outSize += chunk.length;
      if (outSize > MAX_STDOUT) return fatal('output', `вивід моста перевищив ${MAX_STDOUT} байтів`);
      out.push(chunk);
    });
    child.stderr.on('data', (chunk) => {
      if (err.length < MAX_STDERR) err += chunk.toString('utf8');
    });
    child.stdin.on('error', () => {}); // EPIPE if the process finishes before receiving input
    child.on('close', (code) => {
      const raw = Buffer.concat(out).toString('utf8').trim();
      let parsed;
      try {
        parsed = JSON.parse(raw);
      } catch (error) {
        return fatal('json', `код виходу ${code}; stdout: ${raw.slice(0, 200)}; stderr: ${err.slice(0, 500)}`);
      }
      if (parsed && parsed.ok === true) return finish({ status: 'ok' });
      const e = parsed && parsed.error;
      if (parsed && parsed.ok === false && e && Number.isInteger(e.line) && Number.isInteger(e.column)
          && typeof e.message === 'string') {
        return finish({ status: 'error', error: { kind: e.kind, line: e.line, column: e.column, message: e.message } });
      }
      if (parsed && parsed.fatal) return fatal(String(parsed.fatal.code), String(parsed.fatal.detail));
      return fatal('json', `неочікувана відповідь моста: ${raw.slice(0, 200)}`);
    });

    timer = setTimeout(() => fatal('timeout', `міст не відповів за ${timeoutMs} мс`), timeoutMs);
    child.stdin.end(JSON.stringify({ text }));
  });
}

module.exports = { runBridge, DEFAULT_TIMEOUT_MS, MAX_STDOUT };
