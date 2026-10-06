'use strict';
// Diagnostic lifecycle without vscode: debounce, cancellation of stale jobs,
// document version checks, and workspace trust.
//
// Injected host:
//   isTrusted(), isEnabled(), run(text, signal) -> Promise<runner.js result>,
//   publish(doc, error|null): show one error or clear diagnostics,
//   clear(key): clear document diagnostics,
//   version(key): current open-document version, or undefined if closed,
//   report(code, detail): report an environment failure once per cause,
//   setTimer / clearTimer: injected timers for testing.
// doc: { key, version, text() }.

const DEBOUNCE_MS = 250;
// Document-dependent failures (timeout, output size, request, depth) allow
// later edits and other files to be checked. Interpreter, import, version,
// or protocol failures disable checking until settings or trust change.
const DOCUMENT_FAILURES = new Set(['timeout', 'output', 'request', 'recursion']);

class DiagnosticsController {
  constructor(host, { debounceMs = DEBOUNCE_MS } = {}) {
    this.host = host;
    this.debounceMs = debounceMs;
    this.jobs = new Map();         // key -> { timer, abort }
    this.generations = new Map();  // key -> generation; never reset, so reopening cannot revive a stale result
    this.environmentBroken = false;
    this.reported = new Set();
    this.disposed = false;
  }

  generation(key) {
    return this.generations.get(key) || 0;
  }

  cancel(key) {
    this.generations.set(key, this.generation(key) + 1);
    const job = this.jobs.get(key);
    if (!job) return;
    this.jobs.delete(key);
    if (job.timer !== null) this.host.clearTimer(job.timer);
    if (job.abort) job.abort.abort();
  }

  // After an edit, check the document after debounceMs.
  schedule(doc) {
    this.cancel(doc.key);
    if (!this.canRun()) {
      this.host.clear(doc.key);
      return;
    }
    const job = { timer: null, abort: null };
    const generation = this.generation(doc.key);
    job.timer = this.host.setTimer(() => {
      job.timer = null;
      this.start(doc, job, generation);
    }, this.debounceMs);
    this.jobs.set(doc.key, job);
  }

  // Check immediately after opening or saving.
  flush(doc) {
    this.cancel(doc.key);
    if (!this.canRun()) {
      this.host.clear(doc.key);
      return;
    }
    const job = { timer: null, abort: null };
    this.jobs.set(doc.key, job);
    this.start(doc, job, this.generation(doc.key));
  }

  canRun() {
    return !this.disposed && !this.environmentBroken && this.host.isTrusted() && this.host.isEnabled();
  }

  start(doc, job, generation) {
    const abort = new AbortController();
    job.abort = abort;
    const { version } = doc;
    Promise.resolve(this.host.run(doc.text(), abort.signal)).then((result) => {
      if (this.disposed || this.generation(doc.key) !== generation) return;
      this.jobs.delete(doc.key);
      if (this.host.version(doc.key) !== version) return;
      this.apply(doc, result);
    });
  }

  apply(doc, result) {
    if (!result || result.status === 'cancelled') return;
    if (result.status === 'ok') return this.host.publish(doc, null);
    if (result.status === 'error') return this.host.publish(doc, result.error);
    // Environment failure: do not invent syntax underlines.
    this.host.clear(doc.key);
    if (!DOCUMENT_FAILURES.has(result.code)) this.environmentBroken = true;
    if (!this.reported.has(result.code)) {
      this.reported.add(result.code);
      this.host.report(result.code, result.detail);
    }
  }

  // On close, cancel jobs and remove diagnostics.
  close(key) {
    this.cancel(key);
    this.host.clear(key);
  }

  // Trust/settings/interpreter changed: reset state and recheck all documents.
  refreshAll(docs) {
    this.environmentBroken = false;
    this.reported.clear();
    for (const key of [...this.jobs.keys()]) this.cancel(key);
    for (const doc of docs) {
      if (this.canRun()) this.flush(doc);
      else this.close(doc.key);
    }
  }

  dispose() {
    this.disposed = true;
    for (const key of [...this.jobs.keys()]) this.cancel(key);
    for (const key of [...this.generations.keys()]) this.host.clear(key);
  }
}

module.exports = { DiagnosticsController, DEBOUNCE_MS };
