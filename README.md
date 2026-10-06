# Bazar («Базар»)

Bazar is a small programming language with Ukrainian keywords and a surzhyk
style, as if a cheeky friend were explaining programming beside a garage.
`зуб даю` declares an immutable variable, `мутна тєма` declares a mutable one,
and `перевзувся` assigns a new value. Conditions start with `якшо реально`,
may have an `а нє` branch, and end with `отакої`. Source files use `.bazar`.

The compiler reads UTF-8 source, checks lexical and syntactic structure, and
prints an abstract syntax tree (AST). It does not execute programs or check
semantic rules such as types, mutability, or overflow.

| Document | Contents |
| --- | --- |
| [grammar.ebnf](grammar.ebnf) | complete syntactic and lexical grammar |
| [LANGUAGE.md](LANGUAGE.md) | syntax, lexical rules, positions, AST, and intended semantics |
| [EXAMPLES.md](EXAMPLES.md) | example programs, common errors, and semantic rules |
| [examples/](examples) | source files to try with the compiler |

## VS Code extension

The extension adds syntax highlighting, completion, keyword explanations,
and lexical and syntax error underlines to `.bazar` files. Build and install it
with Node.js 22+ and npm:

```sh
cd vscode
npm ci
npm run package
code --install-extension dist/bazar.vsix
```

Hover over a keyword or a word in a phrase such as `зуб даю` or `ділити на` to
see its meaning, grammar rule, and example. Run **Bazar: Keyword Dictionary**
from the Command Palette to open the complete reference.

Highlighting, completion, hover help, and the dictionary need no additional
programs. Error underlines require Python 3.9 or newer. Set the interpreter
with `bazar.pythonPath`, which defaults to `python3`. Code checking is disabled
in untrusted workspaces. See [vscode/README.md](vscode/README.md).

## Types and declarations

| Bazar type | Meaning | Range or values |
| --- | --- | --- |
| `дрібняк` | signed 32-bit integer (`i32`) | −2147483648 … 2147483647 |
| `крупняк` | signed 64-bit integer (`i64`) | −9223372036854775808 … 9223372036854775807 |
| `базар` | Boolean (`bool`) | `реально` (true), `гон` (false) |

A declaration always has a name, a type after `тіпа`, and an initial value
after `це`.

```text
зуб даю зарплата тіпа крупняк це 100
мутна тєма залишок тіпа крупняк це зарплата мінус 80
зуб даю ок тіпа базар це реально
```

### Constants

Bazar has two kinds of constants:

- **Literal constants**: integer literals (`42`, `2147483647`) and the Boolean
  literals `реально` and `гон`. Their values are fixed in the source.
- **Named constants**: `зуб даю` (literally "I swear") binds a name to a value
  that can never change. It is Bazar's equivalent of `const` / `let`, so the
  language needs no separate constant keyword.

```text
зуб даю ліміт тіпа дрібняк це 2147483647
зуб даю правда тіпа базар це реально
```

### Mutable variables

A variable declared with `мутна тєма` can be changed by assignment:

```text
перевзувся залишок тепер залишок мінус 15
```

`тіпа` must be entirely Cyrillic: its final letter is Cyrillic `а`, not
Latin `a`. Keywords are case-sensitive.

## Expressions

Operators below are listed from highest to lowest precedence. Parentheses
override precedence.

| Operators | Meaning | Associativity |
| --- | --- | --- |
| unary `мінус` | numeric negation | right |
| `на`, `ділити на` | multiplication, integer division | left |
| `плюс`, `мінус` | addition, subtraction | left |
| `рівно`, `не рівно`, `більше`, `менше` | `==`, `!=`, `>`, `<` | one comparison per expression level |
| `і ше` | logical AND | left |
| `або` | logical OR | left |

```text
зуб даю відповідь тіпа дрібняк це 2 плюс 3 на 4
зуб даю інша тіпа дрібняк це (2 плюс 3) на 4 ділити на 2
зуб даю борг тіпа дрібняк це мінус 100
зуб даю перевірка тіпа базар це відповідь не рівно 0 і ше ок або гон
```

`2 плюс 3 на 4` means `2 + (3 * 4)`. AND binds more tightly than OR.
Comparisons cannot be chained: write `a менше b і ше b менше c` instead of
`a менше b менше c`.

Operators are words. Symbolic alternatives such as `+`, `-`, `==`, and `!=`
are not accepted. A standalone `нє` is not negation; the language has no
logical NOT operator.

## Conditions

`якшо реально` has a nonempty body and ends with `отакої`. Its optional
`а нє` branch must also be nonempty. Conditions may be nested. A single
`отакої` closes the entire condition, including its optional else branch;
each nested condition has its own closing word.

```text
якшо реально залишок більше 0
    якшо реально залишок менше 10
        базарь залишок
    отакої
а нє
    базарь 0
отакої
```

The first `реально` belongs to the opening phrase. An always-true condition
therefore repeats it:

```text
якшо реально реально
    базарь перевірка
отакої
```

Indentation is for readability. `а нє` and `отакої` occupy separate lines.
Blank lines and comments do not count as body statements. Both words of
`а нє` must appear on the same line.

## Output and exit

`базарь` prints a value; `всьо розходимось` exits with an integer result.
Exit is optional and may appear inside a condition.

```text
базарь залишок
всьо розходимось залишок
```

The current compiler represents these operations in the AST without executing
them.

## Source format

Source files use UTF-8 without a byte order mark.

- Names start with an ASCII letter, a Cyrillic letter (`А–Я`, `а–я`, `Ё`, `ё`),
  a Ukrainian letter (`І`, `і`, `Ї`, `ї`, `Є`, `є`, `Ґ`, `ґ`), or `_`.
  Subsequent characters may also be ASCII digits. `answer_42`, `залишок`,
  `їжак`, and `дрібняк_2` are valid names. An apostrophe (`'` or `ʼ`) may
  stand between two letters, as in `з'їзд` or `мʼясо`; it cannot start or end
  a name, follow a digit or `_`, or be doubled. Other letters are not allowed;
  Latin and Cyrillic letters may be mixed.
- Keywords are case-sensitive. Every word of a phrase is independently
  reserved, including `а`, `нє`, `і`, and `ше`. A keyword prefix does not
  reserve a whole name: `дрібняк_2` is an identifier. Words absent from the
  language, such as `якщо` and `кажи`, are ordinary identifiers.
- Integers are decimal digit sequences of arbitrary length. Leading zeros
  are allowed. Negative values use unary `мінус`. Forms such as `12abc`,
  `12_3`, `0x1F`, and `1.5` are invalid.
- Spaces and tabs separate words. LF and CRLF are accepted line endings;
  a standalone CR is invalid.
- Each statement occupies its own line, except a condition that spans
  multiple lines. Phrases and expressions cannot continue onto another
  line, even within parentheses. The final top-level newline is optional.
- `чутки:` starts a comment through the end of the line. The colon must
  immediately follow the complete word. Comments may contain any valid
  UTF-8, including emoji.
- Parentheses are the only punctuation outside comments. Braces, semicolons,
  and string literals are not supported.

```text
чутки: comments accept Unicode 😎
зуб даю answer_42 тіпа крупняк це 42 чутки: the answer
базарь answer_42
```

## Running the compiler

Python **3.9 or newer** is required. The compiler uses only the standard
library; there are no dependencies or build steps.

```sh
python3 compiler.py --ast examples/budget.bazar
python3 lexer.py examples/budget.bazar      # inspect tokens
```

Input files may have any extension, including `.bazar` and `.txt`.

| Result | Exit code | stdout | stderr |
| --- | --- | --- | --- |
| valid syntax | 0 | complete AST dump with a final newline | empty |
| lexical or syntax error | 1 | empty | one line: `compilation error: line L:C: MESSAGE` |
| invalid arguments or unreadable input | 2 | empty | usage hint or file error |

For example, `зуб даю x це 1` lacks the required type:

```text
compilation error: line 1:17: Де «тіпа», шеф? Після «x» треба вказати тип, а тут «це».
```

Diagnostics stay in Ukrainian/surzhyk and name what was expected and found.
The fixed prefix and byte position identify the location. Examples:

| Problem | Message |
| --- | --- |
| empty condition body | `Блок «якшо реально» пустий. Хотів шось зробить чи просто зайшов?` |
| reserved word used as a name | `«базар» — зарезервоване слово, іменем воно не стане. Вигадай свою кличку для змінної після «зуб даю».` |
| chained comparisons | `Порівняння в ланцюжок не ліпи: з'єднай їх через «і ше» / «або» або візьми дужки.` |
| invalid number | `Число з буквами? Не мути: після цифр букви й '_' не ліплять.` |
| else without a condition | `«А нє» без «якшо»? Ти з ким спориш?` |
| unclosed condition | `Де «отакої»? Базар із рядка 1:1 не закритий, а файл уже скінчився.` |

The compiler writes all messages as UTF-8 bytes, regardless of terminal locale.

### Spicy mode (optional failure counters)

By default, every error uses the plain diagnostic above, and the compiler
keeps no state. Set `BAZAR_SPICY=1` to turn on an optional joke mode with
persistent counters, in which the compiler's mood degrades as failures
accumulate. With spicy mode on, every lexical or syntax failure from
`compiler.py` or `lexer.py` increments two persistent counters by 1:

- `lifetime_failures`: all failures ever recorded; never decreases.
- `message_counter`: decreases by 2 after each swear-word diagnostic.

After incrementing, the first applicable rule takes priority. Thresholds
are strict:

1. `lifetime_failures > 40`: replace the error body with `Вась... Ну тут вже все.`;
   do not decrease the message counter.
2. `message_counter > 10`: prepend an uncensored exclamation containing `!`
   to the original message, then decrease `message_counter` by 2.
3. Otherwise, use the original message.

The `compilation error: line L:C:` prefix, position, exit code 1, and empty
stdout remain unchanged. Starting from zero, failures 1–10 are ordinary,
odd-numbered failures 11–39 use swear words, failure 40 is ordinary, and
failure 41 onward uses only `Вась... Ну тут вже все.`. Successes, argument
errors, and unreadable files neither increment nor reset the counters.

State is stored in `~/.bazar/compiler_failures.sqlite3`, shared across projects
for the OS user. Override the path with `BAZAR_FAILURE_COUNTER_FILE`.
Concurrent invocations are counted atomically. To reset the counters, delete
the file while the compiler is not running. If storage is unavailable or
corrupt, the compiler uses the original diagnostic and leaves the file alone.
`check.py` and the CLI tests disable spicy mode; counter tests enable it with
temporary state and do not change your counters.

### Source positions

Lines and columns start at 1. Columns count **UTF-8 bytes**: a Cyrillic letter
uses two bytes, an emoji four, and a tab one. CRLF is one newline. Missing
words at the end of a line are reported at its newline; at EOF, the position
is immediately after the final byte.

### AST dump format

For `зуб даю x тіпа дрібняк це 1`, the dump is:

```text
ProgramNode line=1 column=1
  DeclarationNode line=1 column=1 name=x type=i32 mutable=false
    initializer:
      IntegerNode line=1 column=46 value=1
```

Each node prints its class, position, and scalar fields. Children appear
under `initializer`, `value`, `condition`, `then_body`, `else_body`, `left`,
`right`, and `operand` labels, indented by two spaces per level. Statements
retain source order. An absent else branch prints as `else_body: None`.

Types use canonical names `i32`, `i64`, and `bool`; operators use
`add sub mul div neg eq ne gt lt and or`. Boolean values are `true` and `false`.
Integer literals retain digits without leading zeros, so their length is
not limited by Python integer conversion.

## Semantic rules and current behavior

The language design requires declared names, assignment only to `мутна тєма`
variables, matching types, Boolean conditions, and checked integer arithmetic.
See [LANGUAGE.md](LANGUAGE.md). The compiler currently checks syntax and builds
an AST; semantic checking and execution are not implemented.

Assigning to an immutable variable or initializing `дрібняк` with `2147483648`
therefore produces an AST if the syntax is valid.

Intended overflow behavior is an error rather than wraparound. Minimum values
are written as `мінус 2147483648` and `мінус 9223372036854775808`, with range
checking after unary minus. Integer division truncates toward zero. Division
by zero or division of the minimum value by `мінус 1` is an error under the
intended rules.

Combined parenthesis and condition nesting is limited to **100** levels.
Deeper input produces a compilation error. Flat operator chains are parsed
and printed iteratively, and the AST dump is streamed line by line. Because
each nesting level adds indentation, a dump of a very deep chain grows
quadratically with its length.

## Tests

Run from the repository root:

```sh
python3 check.py
python3 -m unittest discover -s tests -v
```

The fixture runner compares 44 valid programs with expected ASTs, 107 invalid
programs with expected error lines, and checks 7 examples. It verifies exit
codes and both output streams, reports each failure, and exits nonzero if any
check fails. It never rewrites expected files. Missing expectations and orphan
expectation files without sources are failures.

The 85 unit tests cover UTF-8 validation, byte positions, identifiers
(including both cases of every Ukrainian letter), keywords, comments, line
endings, AST structure, operators, nesting, diagnostics, CLI output, and
spicy-mode counters (disabled by default, thresholds, shared state, storage
failures, and concurrency).
They also confirm that semantic violations are accepted when syntax is valid.
The `tests/invalid/syntax_legacy_ru_*` fixtures deliberately contain old Russian
syntax to verify its rejection.

From another directory, use absolute paths:

```sh
python3 /path/to/ZubDayuLang/check.py
python3 -m unittest discover -s /path/to/ZubDayuLang/tests -v
```

## Implementation

The lexer is a handwritten byte-oriented finite-state machine: one machine
validates UTF-8 and assembles code points; another recognizes words, integers,
comments, and line endings. The recursive-descent parser consumes tokens
through `peek`, `eat`, and `expect`, building positioned AST nodes. AST dumping
uses an explicit stack to handle long operator chains.

```text
grammar.ebnf  LANGUAGE.md  EXAMPLES.md  README.md
lexer.py       byte-oriented lexer state machine
parser.py      recursive-descent parser
ast_nodes.py   AST classes and stable dump
compiler.py    command-line interface
diagnostics.py optional spicy-mode counters and CLI error text
check.py       fixture validation runner
examples/      sample programs
tests/         source fixtures, expected results, and unit tests
```
