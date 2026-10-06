'use strict';
// Refresh generated backend/ with root lexer.py, parser.py, ast_nodes.py,
// and the bridge. Generated copies are neither edited nor committed.
const fs = require('fs');
const path = require('path');

const extensionRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(extensionRoot, '..');
const backend = path.join(extensionRoot, 'backend');

const sources = [
  path.join(repoRoot, 'lexer.py'),
  path.join(repoRoot, 'parser.py'),
  path.join(repoRoot, 'ast_nodes.py'),
  path.join(extensionRoot, 'bridge', 'bazar_bridge.py'),
];

function syncBackend() {
  for (const file of sources) {
    if (!fs.existsSync(file)) {
      throw new Error(`Не знайдено джерело для бекенда: ${file}`);
    }
  }
  fs.rmSync(backend, { recursive: true, force: true });
  fs.mkdirSync(backend, { recursive: true });
  for (const file of sources) {
    fs.copyFileSync(file, path.join(backend, path.basename(file)));
  }
  return backend;
}

module.exports = { syncBackend };

if (require.main === module) {
  console.log(`Backend refreshed: ${syncBackend()}`);
}
