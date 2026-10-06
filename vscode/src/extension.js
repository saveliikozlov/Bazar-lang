'use strict';
const path = require('path');
const fs = require('fs');
const vscode = require('vscode');
const { complete } = require('./completion');
const { DiagnosticsController } = require('./controller');
const { runBridge } = require('./runner');
const { errorRange } = require('./positions');
const { findAt, hoverMarkdown, referenceMarkdown } = require('./dictionary');

const LANGUAGE_ID = 'bazar';
const DICTIONARY_SCHEME = 'bazar-dictionary';
const DICTIONARY_URI = vscode.Uri.parse(`${DICTIONARY_SCHEME}:/Bazar Keyword Dictionary.md`);

// Dictionary Markdown is untrusted, with commands and HTML disabled.
function untrustedMarkdown(value) {
  const markdown = new vscode.MarkdownString(value);
  markdown.isTrusted = false;
  markdown.supportHtml = false;
  return markdown;
}

const KINDS = {
  statement: vscode.CompletionItemKind.Snippet,
  keyword: vscode.CompletionItemKind.Keyword,
  type: vscode.CompletionItemKind.TypeParameter,
  constant: vscode.CompletionItemKind.Constant,
  operator: vscode.CompletionItemKind.Operator,
  variable: vscode.CompletionItemKind.Variable,
};

const FATAL_MESSAGES = {
  spawn: (d) => `Не вдалося запустити Python для перевірки коду Bazar: ${d}. Вкажи інтерпретатор у налаштуванні «bazar.pythonPath» (потрібен Python 3.9 або новіший).`,
  'python-version': (d) => `Для перевірки коду Bazar потрібен Python 3.9 або новіший, а знайдено ${d}. Вкажи інший інтерпретатор у «bazar.pythonPath».`,
  import: (d) => `Не вдалося завантажити розбирач Bazar із розширення (${d}). Перевстанови розширення.`,
  timeout: () => 'Перевірка коду Bazar не вкладається в час. Діагностики для цього файлу пропущено.',
  output: (d) => `Python повернув задовгу відповідь: ${d}.`,
  json: (d) => `Python повернув неочікувану відповідь (${d}). Перевір «bazar.pythonPath».`,
  request: (d) => `Міст перевірки не зміг прочитати запит: ${d}.`,
  recursion: (d) => `Перевірка коду Bazar зупинилась: ${d}.`,
};

function activate(context) {
  const output = vscode.window.createOutputChannel('Bazar');
  const collection = vscode.languages.createDiagnosticCollection('bazar');
  const script = path.join(context.extensionPath, 'backend', 'bazar_bridge.py');
  const docsByKey = new Map();

  const config = () => vscode.workspace.getConfiguration('bazar');
  const isBazar = (doc) => doc.languageId === LANGUAGE_ID;
  const asDoc = (doc) => ({ key: doc.uri.toString(), version: doc.version, text: () => doc.getText() });

  const host = {
    isTrusted: () => vscode.workspace.isTrusted,
    isEnabled: () => config().get('diagnostics.enabled', true),
    version: (key) => (docsByKey.has(key) ? docsByKey.get(key).version : undefined),
    run: (text, signal) => {
      if (!fs.existsSync(script)) {
        return Promise.resolve({ status: 'fatal', code: 'import', detail: 'нема backend/bazar_bridge.py; виконай npm run sync-backend' });
      }
      const python = (config().get('pythonPath', 'python3') || 'python3').trim() || 'python3';
      return runBridge({ python, script, text, signal });
    },
    publish: (doc, error) => {
      const document = docsByKey.get(doc.key);
      if (!document || !error) {
        collection.delete(vscode.Uri.parse(doc.key));
        return;
      }
      const r = errorRange(document.getText(), error.line, error.column);
      const range = new vscode.Range(r.startLine, r.startCharacter, r.endLine, r.endCharacter);
      const diagnostic = new vscode.Diagnostic(range, error.message, vscode.DiagnosticSeverity.Error);
      diagnostic.source = 'Bazar';
      diagnostic.code = error.kind === 'lex' ? 'лексика' : 'синтаксис';
      collection.set(document.uri, [diagnostic]);
    },
    clear: (key) => collection.delete(vscode.Uri.parse(key)),
    report: (code, detail) => {
      const text = (FATAL_MESSAGES[code] || ((d) => `Збій перевірки Bazar (${code}): ${d}`))(detail);
      output.appendLine(text);
      vscode.window.showWarningMessage(text, 'Settings').then((choice) => {
        if (choice) vscode.commands.executeCommand('workbench.action.openSettings', 'bazar.pythonPath');
      });
    },
    setTimer: (fn, ms) => setTimeout(fn, ms),
    clearTimer: (timer) => clearTimeout(timer),
  };
  const controller = new DiagnosticsController(host);

  const track = (doc) => {
    if (!isBazar(doc)) return false;
    docsByKey.set(doc.uri.toString(), doc);
    return true;
  };
  const untrack = (doc) => {
    const key = doc.uri.toString();
    if (!docsByKey.has(key)) return;
    controller.close(key);
    docsByKey.delete(key);
  };
  const openDocs = () => [...docsByKey.values()].map(asDoc);

  const provider = vscode.languages.registerCompletionItemProvider(LANGUAGE_ID, {
    provideCompletionItems(document, position) {
      const line = document.lineAt(position.line).text;
      const prefix = line.slice(0, position.character);
      const items = complete(prefix, document.getText(), document.offsetAt(position));
      return items.map((entry) => {
        const item = new vscode.CompletionItem(entry.label, KINDS[entry.kind]);
        item.insertText = entry.isSnippet ? new vscode.SnippetString(entry.insertText) : entry.insertText;
        item.filterText = entry.filterText;
        item.sortText = entry.sortText;
        item.detail = entry.detail;
        if (entry.documentation) item.documentation = untrustedMarkdown(entry.documentation);
        item.range = new vscode.Range(position.translate(0, -entry.replaceLength), position);
        return item;
      });
    },
  });

  const hoverProvider = vscode.languages.registerHoverProvider(LANGUAGE_ID, {
    provideHover(document, position) {
      const hit = findAt(document.lineAt(position.line).text, position.character);
      if (!hit) return undefined;
      const range = new vscode.Range(position.line, hit.start, position.line, hit.end);
      return new vscode.Hover(untrustedMarkdown(hoverMarkdown(hit.entry)), range);
    },
  });

  const dictionaryProvider = vscode.workspace.registerTextDocumentContentProvider(DICTIONARY_SCHEME, {
    provideTextDocumentContent: () => referenceMarkdown(),
  });

  context.subscriptions.push(
    output, collection, provider, hoverProvider, dictionaryProvider,
    vscode.workspace.onDidOpenTextDocument((doc) => {
      if (isBazar(doc)) {
        track(doc);
        controller.flush(asDoc(doc));
      } else {
        untrack(doc); // language changed from Bazar to another language
      }
    }),
    vscode.workspace.onDidChangeTextDocument((event) => {
      if (event.contentChanges.length && track(event.document)) controller.schedule(asDoc(event.document));
    }),
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (track(doc)) controller.flush(asDoc(doc));
    }),
    vscode.workspace.onDidCloseTextDocument(untrack),
    vscode.workspace.onDidGrantWorkspaceTrust(() => controller.refreshAll(openDocs())),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration('bazar')) controller.refreshAll(openDocs());
    }),
    vscode.commands.registerCommand('bazar.recheckDiagnostics', () => controller.refreshAll(openDocs())),
    vscode.commands.registerCommand('bazar.showDictionary', async () => {
      const document = await vscode.workspace.openTextDocument(DICTIONARY_URI);
      await vscode.window.showTextDocument(document, { preview: true });
      return document.uri.toString();
    }),
    { dispose: () => controller.dispose() },
  );

  vscode.workspace.textDocuments.forEach((doc) => {
    if (track(doc)) controller.flush(asDoc(doc));
  });

  // Exposed for extension-host integration tests.
  return { controller, collection };
}

function deactivate() {}

module.exports = { activate, deactivate };
