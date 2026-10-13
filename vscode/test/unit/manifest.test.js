'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..', '..');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8'));

test("manifest: Bazar language, .bazar extension, and source.bazar grammar", () => {
  const [language] = manifest.contributes.languages;
  assert.strictEqual(language.id, 'bazar');
  assert.deepStrictEqual(language.extensions, ['.bazar']);
  assert.strictEqual(manifest.contributes.grammars[0].scopeName, 'source.bazar');
  for (const file of [manifest.main, language.configuration, manifest.contributes.grammars[0].path]) {
    assert.ok(fs.existsSync(path.join(root, file)), file);
  }
});

test("Workspace Trust: limited support and restricted executable configuration", () => {
  const trust = manifest.capabilities.untrustedWorkspaces;
  assert.strictEqual(trust.supported, 'limited');
  assert.ok(trust.description);
  assert.deepStrictEqual(trust.restrictedConfigurations, ['bazar.pythonPath']);
  assert.ok(manifest.contributes.configuration.properties['bazar.pythonPath']);
  assert.strictEqual(manifest.contributes.configuration.properties['bazar.diagnostics.enabled'].default, true);
});

test("language configuration: чутки: comments and Unicode words", () => {
  const config = JSON.parse(fs.readFileSync(path.join(root, 'language-configuration.json'), 'utf8'));
  assert.strictEqual(config.comments.lineComment, 'чутки:');
  const word = new RegExp(config.wordPattern, 'g');
  assert.deepStrictEqual('зуб даю дрібняк_2 їжак'.match(word), ['зуб', 'даю', 'дрібняк_2', 'їжак']);
});

test("runtime extension does not depend on repository-root paths", () => {
  for (const file of ['extension.js', 'runner.js', 'controller.js', 'completion.js', 'positions.js', 'dictionary.js']) {
    const source = fs.readFileSync(path.join(root, 'src', file), 'utf8');
    assert.ok(!/['"]\.\.\/\.\./.test(source), `${file} references the repository root`);
    assert.ok(!/shell:\s*true|exec\(|execSync/.test(source), `${file} launches a shell`);
  }
});

test("dictionary command is declared and version is 0.3.0", () => {
  assert.strictEqual(manifest.version, '0.3.0');
  const lock = JSON.parse(fs.readFileSync(path.join(root, 'package-lock.json'), 'utf8'));
  assert.strictEqual(lock.version, manifest.version);
  assert.strictEqual(lock.packages[''].version, manifest.version);
  const command = manifest.contributes.commands.find((c) => c.command === 'bazar.showDictionary');
  assert.ok(command && command.title.startsWith('Bazar:'));
});
