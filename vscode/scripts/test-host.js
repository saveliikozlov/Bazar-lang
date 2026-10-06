'use strict';
// Real VS Code integration testing with isolated user and extension directories.
//   node scripts/test-host.js               : load vscode/ in development mode
//   node scripts/test-host.js --vsix x.vsix : install and test an isolated VSIX
// VS Code path: BAZAR_VSCODE_PATH or standard macOS/Linux installation.
// The normal VS Code profile and extensions remain unchanged.
const cp = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { runTests } = require('@vscode/test-electron');

const extensionRoot = path.resolve(__dirname, '..');
const repoRoot = path.resolve(extensionRoot, '..');

function findVSCode() {
  const candidates = [
    process.env.BAZAR_VSCODE_PATH,
    '/Applications/Visual Studio Code.app/Contents/MacOS/Code',
    '/Applications/Visual Studio Code.app/Contents/MacOS/Electron',
    '/usr/share/code/code',
  ].filter(Boolean);
  const found = candidates.find((candidate) => fs.existsSync(candidate));
  if (!found) throw new Error('VS Code не знайдено. Задай BAZAR_VSCODE_PATH.');
  return found;
}

function shortTemp(prefix) {
  // VS Code socket paths have length limits: use /tmp rather than os.tmpdir().
  return fs.mkdtempSync(path.join(fs.existsSync('/tmp') ? '/tmp' : os.tmpdir(), prefix));
}

async function main() {
  delete process.env.ELECTRON_RUN_AS_NODE; // otherwise Electron would run as plain Node
  const vsixIndex = process.argv.indexOf('--vsix');
  const vsix = vsixIndex >= 0 ? path.resolve(process.argv[vsixIndex + 1]) : null;
  const vscodeExecutablePath = findVSCode();
  const root = shortTemp('bz-');
  const extensionsDir = path.join(root, 'ext');
  try {
    let extensionDevelopmentPath = extensionRoot;
    if (vsix) {
      const cli = path.join(path.dirname(vscodeExecutablePath), '..', 'Resources', 'app', 'bin', 'code');
      const install = cp.spawnSync(cli, ['--user-data-dir', path.join(root, 'user'), '--extensions-dir', extensionsDir,
        '--install-extension', vsix, '--force'], { encoding: 'utf8' });
      process.stdout.write(install.stdout || '');
      if (install.status !== 0) throw new Error(`Не вдалося встановити VSIX: ${install.stderr}`);
      // A stub supplies extensionDevelopmentPath; actual code loads from the installed VSIX.
      extensionDevelopmentPath = path.join(root, 'stub');
      fs.mkdirSync(extensionDevelopmentPath);
      fs.writeFileSync(path.join(extensionDevelopmentPath, 'package.json'),
        JSON.stringify({ name: 'stub', publisher: 'stub', version: '0.0.0', engines: { vscode: '^1.85.0' } }));
    }

    {
      // Extension test mode always treats the workspace as trusted:
      // isTrusted stays true even without --disable-workspace-trust.
      // Controller unit tests therefore cover untrusted-workspace behavior.
      const fixtures = path.join(root, 'files');
      fs.mkdirSync(fixtures);
      const userData = path.join(root, 'user');
      fs.mkdirSync(path.join(userData, 'User'), { recursive: true });
      fs.writeFileSync(path.join(userData, 'User', 'settings.json'), JSON.stringify({
        'update.mode': 'none',
        'telemetry.telemetryLevel': 'off',
        'workbench.startupEditor': 'none',
      }));
      console.log(`\nVS Code host (${vsix ? 'installed VSIX' : 'development mode'}):`);
      await runTests({
        vscodeExecutablePath,
        extensionDevelopmentPath,
        extensionTestsPath: path.join(extensionRoot, 'test', 'host', 'index.js'),
        launchArgs: [fixtures, '--user-data-dir', userData, '--extensions-dir', extensionsDir, '--skip-welcome', '--skip-release-notes'],
        extensionTestsEnv: {
          BAZAR_FIXTURES: fixtures,
          BAZAR_REPO_ROOT: repoRoot,
          BAZAR_EXTENSIONS_DIR: extensionsDir,
          ...(vsix ? { BAZAR_EXPECT_INSTALLED: '1' } : {}),
        },
      });
    }
    console.log('\nIntegration tests passed.');
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
