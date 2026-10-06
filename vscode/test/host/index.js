'use strict';
// Runs inside the VS Code extension host; see scripts/test-host.js.
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const EXTENSION_ID = 'bazar-lang.bazar';
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function until(predicate, what, timeout = 15000) {
  const end = Date.now() + timeout;
  for (;;) {
    const value = await predicate();
    if (value) return value;
    if (Date.now() > end) throw new Error(`Timed out waiting for: ${what}`);
    await sleep(50);
  }
}

const diagnosticsOf = (uri) => vscode.languages.getDiagnostics(uri).filter((d) => d.source === 'Bazar');

async function replaceAll(document, text) {
  const edit = new vscode.WorkspaceEdit();
  edit.replace(document.uri, new vscode.Range(0, 0, document.lineCount, 0), text);
  assert.ok(await vscode.workspace.applyEdit(edit));
}

async function completions(uri, line, character) {
  const list = await vscode.commands.executeCommand('vscode.executeCompletionItemProvider', uri, new vscode.Position(line, character));
  return list.items;
}

const results = [];
async function step(name, fn) {
  await fn();
  results.push(name);
  console.log(`  ✔ ${name}`);
}

async function run() {
  const dir = process.env.BAZAR_FIXTURES;
  const extension = vscode.extensions.getExtension(EXTENSION_ID);
  assert.ok(extension, 'bazar-lang.bazar extension not found');
  if (process.env.BAZAR_EXPECT_INSTALLED) {
    assert.ok(extension.extensionPath.startsWith(process.env.BAZAR_EXTENSIONS_DIR), `extension was not loaded from the isolated directory: ${extension.extensionPath}`);
    assert.ok(!extension.extensionPath.startsWith(process.env.BAZAR_REPO_ROOT), 'extension was loaded from the repository');
  }
  assert.ok(!dir.startsWith(process.env.BAZAR_REPO_ROOT), 'test files must be outside the repository');
  await extension.activate();

  const validFile = path.join(dir, 'valid.bazar');
  fs.writeFileSync(validFile, 'зуб даю x тіпа дрібняк це 1\n');
  const uri = vscode.Uri.file(validFile);
  const document = await vscode.workspace.openTextDocument(uri);
  await vscode.window.showTextDocument(document);

  await step(".bazar files are recognized as Bazar", async () => {
    assert.strictEqual(document.languageId, 'bazar');
  });

  await step("completion: Cyrillic prefixes offer snippets without Python", async () => {
    await replaceAll(document, 'зу');
    const items = await completions(uri, 0, 2);
    const item = items.find((i) => i.label === 'зуб даю');
    assert.ok(item, `missing зуб даю among ${items.map((i) => i.label)}`);
    assert.ok(item.insertText instanceof vscode.SnippetString);
    assert.ok(item.insertText.value.startsWith('зуб даю ${1:name} тіпа'));
    assert.deepStrictEqual([item.range.start.character, item.range.end.character], [0, 2]);
  });

  await step("phrase prefix зуб д avoids duplication; comments suppress completion", async () => {
    await replaceAll(document, 'зуб д');
    const item = (await completions(uri, 0, 5)).find((i) => i.label === 'зуб даю');
    assert.deepStrictEqual([item.range.start.character, item.range.end.character], [0, 5]);
    await replaceAll(document, 'чутки: зуб');
    assert.strictEqual((await completions(uri, 0, 10)).filter((i) => i.label === 'зуб даю').length, 0);
  });

  const hoversAt = (target, line, character) => vscode.commands.executeCommand('vscode.executeHoverProvider', target, new vscode.Position(line, character));
  const hoverText = (hover) => hover.contents.map((c) => (typeof c === 'string' ? c : c.value)).join('\n');

  await step("hover: every phrase word returns a full UTF-16 range and Bazar example", async () => {
    await replaceAll(document, '😀 зуб \t даю x тіпа дрібняк це 1 чутки: зуб даю\n');
    for (const character of [3, 11]) {
      const found = (await hoversAt(uri, 0, character)).filter((h) => hoverText(h).includes('**зуб даю**'));
      assert.strictEqual(found.length, 1, `position ${character}`);
      assert.deepStrictEqual([found[0].range.start.character, found[0].range.end.character], [3, 12]);
      const text = hoverText(found[0]);
      assert.ok(text.includes('```bazar\n') && text.includes('immutable_declaration'));
      const content = found[0].contents[0];
      assert.ok(content instanceof vscode.MarkdownString);
      assert.ok(!content.isTrusted, 'hover Markdown must remain untrusted');
    }
    assert.strictEqual((await hoversAt(uri, 0, 14)).filter((h) => hoverText(h).includes('Grammar')).length, 0, 'identifier x');
    const marker = (await hoversAt(uri, 0, 34)).filter((h) => hoverText(h).includes('**чутки:**'));
    assert.strictEqual(marker.length, 1);
    assert.strictEqual((await hoversAt(uri, 0, 43)).filter((h) => hoverText(h).includes('Grammar')).length, 0, 'comment body');
  });

  await step("hover: реально as a literal and within якшо реально", async () => {
    await replaceAll(document, 'якшо реально реально\nбазарь 1\nотакої\n');
    const phrase = (await hoversAt(uri, 0, 7)).find((h) => hoverText(h).includes('**якшо реально**'));
    assert.ok(phrase);
    assert.deepStrictEqual([phrase.range.start.character, phrase.range.end.character], [0, 12]);
    const literal = (await hoversAt(uri, 0, 16)).find((h) => hoverText(h).includes('**реально**'));
    assert.ok(literal);
    assert.deepStrictEqual([literal.range.start.character, literal.range.end.character], [13, 20]);
  });

  await step("dictionary: open generated Markdown without Python", async () => {
    const config = vscode.workspace.getConfiguration('bazar');
    await config.update('pythonPath', '/нема/такого/python', vscode.ConfigurationTarget.Global);
    try {
      const commands = await vscode.commands.getCommands(true);
      assert.ok(commands.includes('bazar.showDictionary'));
      await vscode.commands.executeCommand('bazar.showDictionary');
      const dictionary = vscode.window.activeTextEditor.document;
      assert.strictEqual(dictionary.uri.scheme, 'bazar-dictionary');
      assert.strictEqual(dictionary.languageId, 'markdown');
      const text = dictionary.getText();
      for (const heading of ['# Bazar Keyword Dictionary', '### зуб даю', '### мутна тєма', '### якшо реально', '### а нє',
        '### всьо розходимось', '### і ше', '### не рівно', '### ділити на', '### чутки:', '### ше', '### реально']) {
        assert.ok(text.includes(heading), heading);
      }
      assert.ok(text.includes('```bazar'));
    } finally {
      await config.update('pythonPath', undefined, vscode.ConfigurationTarget.Global);
    }
    await vscode.window.showTextDocument(document);
  });

  await step("completion: dictionary documentation belongs to keywords, not variables", async () => {
    await replaceAll(document, 'зуб даю баланс тіпа дрібняк це 1\nпереві');
    const items = await completions(uri, 1, 5);
    const assignment = items.find((i) => i.label === 'перевзувся … тепер');
    assert.ok(assignment && assignment.documentation instanceof vscode.MarkdownString);
    assert.ok(assignment.documentation.value.includes('assignment = '));
    assert.ok(!assignment.documentation.isTrusted);
    assert.ok(assignment.insertText instanceof vscode.SnippetString);
    await replaceAll(document, 'зуб даю баланс тіпа дрібняк це 1\nбазарь ба');
    const variable = (await completions(uri, 1, 9)).find((i) => i.label === 'баланс');
    assert.ok(variable);
    assert.strictEqual(variable.documentation, undefined);
    const elseItem = (await completions(uri, 1, 0)).find((i) => i.label === 'якшо реально … а нє');
    assert.ok(elseItem.documentation.value.includes('if_statement'));
  });

  await step("unsaved invalid text reports the exact diagnostic range", async () => {
    await replaceAll(document, 'чутки: 😀\nзуб даю баланс тіпа дрібняк це\n');
    assert.ok(document.isDirty);
    const [d] = await until(() => { const found = diagnosticsOf(uri); return found.length ? found : null; }, 'diagnostic');
    assert.ok(d.message.startsWith('Де значення?'), d.message);
    assert.strictEqual(d.severity, vscode.DiagnosticSeverity.Error);
    assert.deepStrictEqual([d.range.start.line, d.range.start.character, d.range.end.line, d.range.end.character], [1, 28, 1, 30]);
  });

  await step("emoji before a token maps to the correct UTF-16 range", async () => {
    await replaceAll(document, 'базарь 1 плюс 😀\n');
    const [d] = await until(() => { const f = diagnosticsOf(uri); return f.length && f[0].range.start.line === 0 ? f : null; }, 'emoji diagnostic');
    // 😀 begins at UTF-16 offset 14 and occupies two units.
    assert.deepStrictEqual([d.range.start.character, d.range.end.character], [14, 16]);
  });

  await step("fixing input clears diagnostics", async () => {
    await replaceAll(document, 'зуб даю x тіпа дрібняк це 1\n');
    await until(() => diagnosticsOf(uri).length === 0, 'cleared diagnostics');
  });

  await step("rapid editing retains only the current error", async () => {
    await replaceAll(document, 'базарь\n');
    await sleep(60);
    await replaceAll(document, 'базарь 1 плюс\nчутки: ok\n');
    const [d] = await until(() => { const f = diagnosticsOf(uri); return f.length ? f : null; }, 'diagnostic');
    assert.strictEqual(d.range.start.line, 0);
    await sleep(800);
    assert.strictEqual(diagnosticsOf(uri).length, 1);
  });

  await step("closing clears diagnostics and reopening cannot revive stale results", async () => {
    await vscode.window.showTextDocument(document);
    await vscode.commands.executeCommand('workbench.action.revertAndCloseActiveEditor');
    await until(() => diagnosticsOf(uri).length === 0, 'cleared diagnostics after close');
    const reopened = await vscode.workspace.openTextDocument(uri);
    await sleep(1000);
    assert.strictEqual(reopened.getText(), 'зуб даю x тіпа дрібняк це 1\n');
    assert.deepStrictEqual(diagnosticsOf(uri), []);
  });

  await step("disabling diagnostics clears errors and reenabling restores checking", async () => {
    const config = vscode.workspace.getConfiguration('bazar');
    const doc = await vscode.workspace.openTextDocument(uri);
    await vscode.window.showTextDocument(doc);
    await replaceAll(doc, 'базарь\n');
    await until(() => diagnosticsOf(uri).length === 1, 'diagnostic');
    await config.update('diagnostics.enabled', false, vscode.ConfigurationTarget.Global);
    await until(() => diagnosticsOf(uri).length === 0, 'disabled diagnostics');
    await replaceAll(doc, 'базарь 1 плюс\n');
    await sleep(800);
    assert.strictEqual(diagnosticsOf(uri).length, 0);
    await config.update('diagnostics.enabled', true, vscode.ConfigurationTarget.Global);
    await until(() => diagnosticsOf(uri).length === 1, 'reenabled diagnostics');
  });

  await step("EOF after an emoji comment underlines the whole character", async () => {
    await replaceAll(document, 'якшо реально реально\nбазарь 1\nчутки: 😀');
    const [d] = await until(() => { const f = diagnosticsOf(uri); return f.length && f[0].range.start.line === 2 ? f : null; }, 'EOF diagnostic');
    assert.deepStrictEqual([d.range.start.line, d.range.start.character, d.range.end.line, d.range.end.character], [2, 7, 2, 9]);
    await replaceAll(document, 'зуб даю x тіпа дрібняк це 1\n');
    await until(() => diagnosticsOf(uri).length === 0, 'cleared EOF diagnostic');
  });

  await step("oversized output allows subsequent edits and other files to be checked", async () => {
    const otherFile = path.join(dir, 'other.bazar');
    fs.writeFileSync(otherFile, 'зуб даю x тіпа дрібняк це 1\n');
    const otherUri = vscode.Uri.file(otherFile);
    const other = await vscode.workspace.openTextDocument(otherUri);
    await vscode.window.showTextDocument(other);
    await replaceAll(document, 'x'.repeat(70000));
    await sleep(1500);
    assert.deepStrictEqual(diagnosticsOf(uri), [], 'oversized output must not produce underlines');
    await replaceAll(document, 'базарь\n');
    const [d] = await until(() => { const f = diagnosticsOf(uri); return f.length ? f : null; }, 'diagnostic after oversized output');
    assert.strictEqual(d.range.start.line, 0);
    await replaceAll(other, 'базарь\n');
    await until(() => diagnosticsOf(otherUri).length === 1, 'checking another file');
    await replaceAll(other, 'зуб даю x тіпа дрібняк це 1\n');
    await until(() => diagnosticsOf(otherUri).length === 0, 'cleared other-file diagnostics');
    await vscode.window.showTextDocument(document);
  });

  await step("broken Python produces no invented underlines; completion still works", async () => {
    const config = vscode.workspace.getConfiguration('bazar');
    const doc = await vscode.workspace.openTextDocument(uri);
    await config.update('pythonPath', '/нема/такого/python', vscode.ConfigurationTarget.Global);
    await until(() => diagnosticsOf(uri).length === 0, 'cleared diagnostics with broken Python');
    await replaceAll(doc, 'базарь\n');
    await sleep(800);
    assert.strictEqual(diagnosticsOf(uri).length, 0);
    assert.ok((await completions(uri, 0, 0)).length > 10);
    await config.update('pythonPath', undefined, vscode.ConfigurationTarget.Global);
    await until(() => diagnosticsOf(uri).length === 1, 'checking restored after fixing Python');
  });

  await replaceAll(await vscode.workspace.openTextDocument(uri), 'зуб даю x тіпа дрібняк це 1\n');
  return results;
}

module.exports = { run };
