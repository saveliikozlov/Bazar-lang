# Bazar extension for VS Code

Syntax highlighting, completion, a keyword dictionary, and error underlines
for Bazar (`.bazar`) files. The language is described in the repository's
root `README.md`.

## Features

- **Highlighting.** Keywords, types, Booleans, operators, numbers, parentheses,
  and `чутки:` comments have distinct scopes. Matching uses complete words:
  `дрібняк_2` and `базарний` are not highlighted as keywords.
- **Completion.** Phrases and constructs (`желєзобетонно`, `зуб даю`, `мутна тєма`,
  `якшо реально` with `а нє` and `отакої`, `базарь`, `всьо розходимось`,
  operators, and types) are offered as snippets with defaults. Suggestions
  work with Cyrillic input and Ctrl+Space. A partial phrase such as `зуб д`
  is replaced as a whole, without duplicating `зуб`. Comments get no
  suggestions. Names declared in the file are also suggested; this does not
  perform semantic checking.
- **Hover help.** Hover over a keyword or any word of a phrase (`зуб даю`,
  `ділити на`, `якшо реально`) for its meaning, grammar production, syntax,
  and Bazar example. The longest complete phrase is preferred. Its words
  may be separated by spaces or tabs, never a newline. Matching is exact
  and case-sensitive: `зуби` and `базарний` get no keyword help. `реально`
  is explained as both true and part of the condition opener; `мінус` has
  unary and binary roles. Comment bodies get no hover, but `чутки:` does.
  An incomplete phrase shows the word's role and explains that it cannot
  be used on its own.
- **Keyword dictionary.** Run **Bazar: Keyword Dictionary** in the Command
  Palette (Ctrl/Cmd+Shift+P) to open a generated, read-only Markdown source
  document covering every word and phrase: meaning, grammar, syntax, and
  example. It works without Python, in untrusted workspaces, and outside
  Bazar projects. The same descriptions appear in completion documentation.
- **Error underlines.** Lexical and syntax errors appear as red underlines
  and in the Problems panel. Checking starts 250 ms after an edit, including
  unsaved edits, and immediately after saving. The parser stops at the first
  error, so one error is shown per file.

Completion, hover, dictionary help, and highlighting work without Python.
Underlines require **Python 3.9 or newer**. Language keywords and all compiler
and checker error messages remain Ukrainian/surzhyk.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `bazar.pythonPath` | `python3` | interpreter for code checking, launched without a shell |
| `bazar.diagnostics.enabled` | `true` | enable error underlines |

If Python is missing or too old, the extension warns once and logs details to
the Bazar output channel, without inventing underlines. Changing the setting
rechecks files. **Bazar: Recheck Open Files** also triggers a manual recheck.

**Workspace trust.** In an untrusted workspace, highlighting, completion,
hover, and dictionary help work, but Python is not launched. Diagnostics are
cleared and the workspace's `bazar.pythonPath` setting is ignored. Granting
trust checks open files. The extension runs only its bundled bridge, never
workspace scripts or user programs.

## Building, packaging, and testing

Node.js 22+ and npm are required. Tests also need VS Code and Python 3.9+.

```sh
cd vscode
npm ci                  # install build and test dependencies
npm test                # refresh backend/ and run unit tests
npm run test:host        # integration test in real VS Code
npm run package          # create dist/bazar.vsix
npm run test:vsix        # package, install into an isolated profile, and test
```

`npm run sync-backend`, automatically run by `test` and `package`, copies the
root `lexer.py`, `parser.py`, and `ast_nodes.py`, plus `bridge/bazar_bridge.py`,
into generated `backend/`. Do not edit or commit these copies: their original
files are authoritative. The package is self-contained and works on `.bazar`
files outside this repository.

Run backend-rebuilding commands sequentially: concurrent rebuilds can replace
files while another command is testing them.

Integration tests use temporary VS Code user and extension directories,
leaving your profile and installed extensions unchanged. Set `BAZAR_VSCODE_PATH`
to the VS Code executable, or use its standard installation location.
For manual development testing, run `npm run sync-backend`, then:

```sh
code --extensionDevelopmentPath=$PWD --user-data-dir=/tmp/bazar-dev-user --extensions-dir=/tmp/bazar-dev-ext
```

## Layout

```text
package.json                language, grammar, settings, and trust manifest
language-configuration.json чутки: comments, parentheses, and word pattern
syntaxes/                   TextMate source.bazar grammar
src/extension.js            activation and VS Code integration
src/completion.js           pure completion logic
src/dictionary.js           dictionary data, hover matching, and Markdown
src/controller.js           debounce, cancellation, versions, and trust
src/runner.js               shell-free Python runner with timeout/output limits
src/positions.js            UTF-8 byte columns to UTF-16 ranges
bridge/bazar_bridge.py      stdin/stdout JSON wrapper around parse_program()
scripts/                    backend synchronization and integration testing
test/                       unit and integration tests
```

The bridge calls only `parse_program()`, bypassing `compiler.py`. Editor
errors use the same Ukrainian messages as the compiler. Compiler positions (1-based line and
UTF-8 byte column) are converted to UTF-16 ranges, accounting for Cyrillic,
emoji, tabs, and CRLF.

## Limitations

- The dictionary explains grammar and intended meanings. Execution, types
  (`i32`, `i64`, `bool`), and mutability are not currently evaluated or checked.
- Only the first error in a file is shown.
- At a line ending or EOF, the last preceding token is underlined. An empty
  line gives a zero-width range, which VS Code expands itself.
- The whole file is parsed after each typing pause; parsing is not incremental.
