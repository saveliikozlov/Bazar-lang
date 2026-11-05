# Bazar («Базар») — language specification, version 0.4

Bazar is a small imperative language whose keywords are Ukrainian/surzhyk
phrases. Its motto means: *Bazar is a language where you answer for your words.*
Constructs use words instead of symbols and braces, and every `якшо реально`
block ends explicitly with `отакої`. Source files use `.bazar`.

This document describes the lexer, parser, AST, and semantics. Version 0.3
(Stage 2) adds functions, structures, member functions, `ану кажи`, string
printing, and the auto constructor; the semantic pass enforces every rule,
and the compiler generates LLVM IR. Version 0.4 adds fixed-size arrays. The
full numbered rule list is in
[README.md](README.md#semantic-rules). The authoritative
syntax is [grammar.ebnf](grammar.ebnf). Programs are in [examples/](examples)
and explained in [EXAMPLES.md](EXAMPLES.md).

## 1. Statements

Each statement occupies one physical line. `якшо реально`, `маю дєло`, and
`такі діла` span multiple lines; their closers (`а нє`, `отакої`,
`порішали`) each occupy a separate line.

| Form | Meaning | Equivalent |
| --- | --- | --- |
| `желєзобетонно NAME тіпа TYPE це EXPR` | compile-time constant, top level only; literally set in reinforced concrete | `const NAME: T = e` |
| `зуб даю NAME тіпа TYPE це EXPR` | immutable variable; literally a promise | `let name: T = e` |
| `мутна тєма NAME тіпа TYPE це EXPR` | mutable variable; literally a shady business | `let mut name: T = e` |
| `перевзувся NAME тепер EXPR` | assignment; literally changed shoes or position | `name = e` |
| `базарь EXPR` | print a value; literally talk | `print(e)` |
| `всьо розходимось EXPR` | exit; literally everyone, go home | `exit(e)` |
| `якшо реально EXPR` … `а нє` … `отакої` | condition with an optional else branch | `if e { … } else { … }` |
| `крутимось поки EXPR` … `докрутились` | loop while a condition holds; literally we keep spinning | `while e { … }` |
| `крутимось NAME тіпа TYPE від A по B` … `докрутились` | loop over an inclusive integer range | `for name in a..=b { … }` |
| `крутимось NAME тіпа TYPE з EXPR` … `докрутились` | loop over the elements of an array | `for name in array { … }` |
| `харе` | leave the innermost loop; literally enough | `break` |
| `перевзувся NAME.FIELD… тепер EXPR` | assignment to a field through a mutable chain | `o.f = e` |
| `перевзувся NAME[I]… тепер EXPR` | assignment to an array element through a mutable chain | `a[i] = e` |
| `тримай EXPR` | leave the function with a value; literally here, hold it | `return e` |
| `NAME(ARGS)`, `OBJ.NAME(ARGS)`, `ARR[I].NAME(ARGS)` | a call on its own line | `f(a)`, `o.m(a)`, `a[i].m(b)` |
| `маю дєло NAME(P тіпа T, …) на виході T` … `порішали` | function, top level; literally I have a business | `fn name(p: T) -> T { … }` |
| `такі діла NAME` … `порішали` | structure with fields and member functions, top level | `struct Name { … }` |

Expressions add calls `f(a, b)`, field access `o.f`, member calls `o.m(a)`,
object creation `склепай T(a, b)`, and `ану кажи`, which reads one integer.
Arrays add literals `[a, b, c]`, filled arrays `[всюди x]` (literally
everywhere), elements `м[і]`, and the length `м.розмір`. `базарь` also prints a
string literal `"…"`, an object, and an array.

```text
чутки: time to count the money

зуб даю зарплата тіпа крупняк це 100
зуб даю оренда тіпа крупняк це 80

мутна тєма залишок тіпа крупняк це зарплата мінус оренда
перевзувся залишок тепер залишок мінус 15

якшо реально залишок більше 0
    базарь залишок
а нє
    базарь 0
отакої

всьо розходимось залишок
```

- Declarations always require a type (`тіпа`) and initializer (`це`).
- `всьо розходимось` is optional and allowed wherever a statement is allowed,
  including before other statements and inside blocks.
- The `якшо реально` body and optional `а нє` body each require at least one
  statement. Blank and comment-only lines do not count.
- `а нє` consists of two reserved words on the same line. Its words cannot
  be separated by a newline, and the phrase occupies the whole line.
- **`отакої` closes the entire condition, including its optional else branch**,
  rather than each branch separately. Each nested condition has its own closer.
- Conditions may nest, subject to the implementation limit in section 7.
- The true literal is also `реально`, so an always-true condition is written
  `якшо реально реально`. Both occurrences are required.
- Indentation is ignored as ordinary horizontal whitespace.
- `желєзобетонно` declares a named constant; `зуб даю` is an immutable
  variable whose value is known only at run time.

## 2. Types

| Bazar | Meaning | Canonical AST name | Range |
| --- | --- | --- | --- |
| `дрібняк` | signed 32-bit integer | `i32` | −2147483648 … 2147483647 |
| `крупняк` | signed 64-bit integer | `i64` | −9223372036854775808 … 9223372036854775807 |
| `базар` | Boolean | `bool` | `реально` (true) / `гон` (false) |
| a `такі діла` name | object, copied as a value | the structure name | its fields |
| `[TYPE; SIZE]` | fixed-size array, copied as a value | `[i32; 5]`, with SIZE as written | SIZE elements, SIZE from 1 to 2147483647 |

## 3. Expressions

Operators are listed from **highest** to lowest precedence:

| Level | Operators | Canonical operator | Associativity |
| --- | --- | --- | --- |
| 1 | literals, names, `( … )`, arrays `[…]`, `.` fields and calls, `м[і]` elements | | |
| 2 | `мінус x` (unary minus) | `neg` | right: `мінус мінус x` = `-(-x)` |
| 3 | `на` (×), `ділити на` (÷) | `mul`, `div` | left |
| 4 | `плюс` (+), `мінус` (−) | `add`, `sub` | left |
| 5 | `рівно` (==), `не рівно` (!=), `більше` (>), `менше` (<) | `eq`, `ne`, `gt`, `lt` | **one per expression level; no chains** |
| 6 | `і ше` (logical AND) | `and` | left |
| 7 | `або` (logical OR) | `or` | left |

```text
зуб даю відповідь тіпа дрібняк це 2 плюс 3 на 4             чутки: 2 + (3 * 4)
зуб даю інша тіпа дрібняк це (2 плюс 3) на 4                чутки: (2 + 3) * 4
зуб даю борг тіпа крупняк це мінус 100
зуб даю ок тіпа базар це відповідь не рівно 0 і ше реально
```

- `a менше b менше c` is a **syntax error**. Write `a менше b і ше b менше c`
  or use parentheses, such as `(a менше b) рівно гон`.
- There are no symbolic alternatives: `+ - * / == != < > = ! { }` produce
  lexical errors outside comments.
- A standalone `нє` is neither unary NOT nor an operator. Logical negation
  does not exist; `нє` occurs only in `а нє`.
- An expression never continues onto another line, even inside parentheses.

## 4. Lexical rules

- **Encoding.** Source is valid UTF-8 without a byte order mark. The lexer
  validates every byte manually, including bytes in comments. Isolated
  continuation bytes, `C0`, `C1`, `F5`–`FF`, overlong encodings, surrogates
  (U+D800–U+DFFF), values above U+10FFFF, and truncated sequences are errors.
- **Words.** A word starts with an ASCII letter, a Cyrillic letter (`А`–`Я`,
  `а`–`я`, `Ё`, `ё`), a Ukrainian letter (`І`, `і`, `Ї`, `ї`, `Є`, `є`, `Ґ`, `ґ`),
  or `_`, and continues with those characters or ASCII digits. The lexer
  reads the complete word before checking reservations, so `дрібняк_2`,
  `базарний`, `зуби`, `наш`, `якшоб`, and `отакоїж` are ordinary names.
  Matching is exact and case-sensitive: `є` ≠ `е`, `і` ≠ `и`, and Latin `a` ≠
  Cyrillic `а`. Other letters (`é`, `ß`, `ў`, `љ`, …) are errors.
- **Apostrophes.** The Ukrainian apostrophe, ASCII `'` (U+0027) or `ʼ`
  (U+02BC), may appear inside a word only between two letters: `з'їзд`,
  `мʼясо`, `O'Neil`. An apostrophe at the start or end of a word, after a
  digit or `_`, before a non-letter, or doubled is a lexical error positioned
  at the apostrophe. The typographic `’` (U+2019) is not accepted.
  Unicode normalization is not performed.
- **Reserved words** are the individual words of every phrase:
  `желєзобетонно зуб даю мутна тєма тіпа це дрібняк крупняк базар перевзувся тепер базарь
  всьо розходимось якшо реально а нє отакої гон або і ше рівно не більше менше
  плюс мінус на ділити маю дєло виході тримай порішали такі діла склепай ану кажи
  крутимось поки докрутились харе всюди чутки`. `від`, `по`, and `з` are not
  reserved.
  `тіпа` is entirely Cyrillic: `тіпa` with a final Latin `a` is an identifier,
  rather than the keyword.
- **Integers.** One or more decimal ASCII digits; leading zeros are allowed.
  A literal greater than `9223372036854775808` (2^63) is a lexical error at
  its first digit, because no type can hold it. `9223372036854775808` itself
  is valid only directly after unary `мінус`. A literal has no sign: `мінус 5` applies unary minus
  to `5`. Digits immediately followed by a letter or `_` (`12abc`, `12_3`,
  `0x1F`) produce a lexical error at the first digit.
- **Whitespace.** Only space and tab separate tokens. Lines end with LF or
  CRLF, each producing one NEWLINE token. CR without LF is an error.
- **Comments.** The complete word `чутки` **immediately** followed by `:` starts
  a comment through the end of the line. It may contain any valid UTF-8,
  including emoji. `чутки :` and bare `чутки` are errors. In `xчутки:`, the word
  is `xчутки`, so `:` is unexpected. A comment's ending newline still produces
  a NEWLINE token.
- **Punctuation** is `(`, `)`, `[`, `]`, `,`, `.`, and `;`. All other
  punctuation outside comments and string literals produces a lexical error.
  A string literal `"…"` may appear only as the operand of `базарь`.

### Positions

Each token and AST node has 1-based `line` and `column` fields. **Columns count
UTF-8 bytes**, not characters: a Cyrillic letter advances by 2, an emoji by 4,
and a tab by 1. After LF or CRLF, the next byte is column 1 of the next line.
NEWLINE is positioned at LF, or at CR for CRLF, and its text is always `"\n"`.
EOF is positioned immediately after the last input byte.

### Lines and statements

- Empty input, or input containing only blank/comment lines, is a valid program.
- Two statements never share one line.
- The final top-level statement may end at EOF without a final LF. Inside a
  block, every statement, including a nested condition, ends with a newline
  so `а нє` and `отакої` can start their own lines.

## 5. Semantics

The semantic pass ([semantic.py](semantic.py)) enforces these Stage 1 rules
and the Stage 2 rules listed in [README.md](README.md#semantic-rules). The
parser still accepts every grammatically valid program, so `--ast` prints an
AST for programs that break them; compiling reports the first broken rule.

- **Names.** Declare a name before using it. Redeclaration in the same scope
  is an error. An initializer cannot see the name being declared. The program
  is one scope; each if/else block introduces a child scope. Names declared
  inside a block are invisible outside it; shadowing an outer name is allowed.
- **Constants.** The initializer of `желєзобетонно` is a constant
  expression: it may use literals, operators, parentheses, and names of
  constants declared earlier, but not variables. Its value is computed at
  compile time, and the result must fit the declared type. A constant can
  never be assigned. (The parser already enforces that constants are
  declared only at the top level, outside `якшо реально`.)
- **Mutability.** `перевзувся` may assign only to a `мутна тєма` variable.
  Assignment to a `желєзобетонно` constant or a `зуб даю` variable is an error, with the intended diagnostic
  «Ти за 'x' зуб дав. Перевзуватись нема чого.».
- **Types.** Initializers and assigned values must exactly match the variable's
  type. No implicit conversion exists between `дрібняк`, `крупняк`, and `базар`.
  Arithmetic requires two integers of the same type. `рівно` and `не рівно`
  compare values of the same type, including Booleans. `більше` and `менше`
  compare integers of the same type. Comparisons return `базар`. `і ше` and
  `або` take Booleans and short-circuit. A condition must be `базар`. `базарь`
  prints decimal integers and Booleans as `реально` / `гон`. `всьо розходимось`
  takes an integer and exits the entire program.
- **Integer literals** keep their exact value until type checking. They
  obtain an integer type from context: a declaration, assignment, or typed
  other operand. An expression of literals with no context defaults to
  `крупняк`.
- **Overflow checks.** The lexer and parser already reject literals that
  fit no type (see section 4). Beyond that, a literal outside its type's
  range is a compilation error. Minimum values use unary minus (`мінус 2147483648` and
  `мінус 9223372036854775808`), so range checking follows unary minus.
  Every arithmetic result, including unary negation, is checked. Overflow
  is an error and never wraps. Division truncates toward zero; division
  by zero and `MIN ділити на мінус 1` are errors.

Semantic checking is a separate pass, not mixed into parsing.
`зуб даю x тіпа дрібняк це 2147483648` matches the grammar, so the parser
accepts it, and the semantic pass rejects it. Syntax tests cover type and literal spelling errors: missing or
misspelled types, `12abc`, `0x1F`, `10L`, `12_3`, `1.5`, `-1`, and `+`.

## 6. Abstract syntax tree

```text
ASTNode(line, column)
├── ProgramNode(statements)
├── BlockNode(statements)                  IfNode branch body
├── StmtNode
│   ├── ConstantDeclarationNode(name, declared_type, initializer)
│   ├── DeclarationNode(name, declared_type, mutable, initializer)
│   ├── AssignmentNode(name, value)
│   ├── IfNode(condition, then_body, else_body)   else_body may be None
│   ├── PrintNode(value)                   value may be a StringNode
│   ├── ExitNode(value)
│   ├── ReturnNode(value)
│   ├── CallStatementNode(call)            member_call flag
│   ├── FieldAssignmentNode(target, value)    target: fields and indexes
│   ├── ForEachNode(name, declared_type, array, body)
│   ├── FunctionNode(name, parameters, result_type, body)
│   └── StructureNode(name, fields, methods)
├── ParameterNode(name, declared_type)
├── FieldNode(name, declared_type, mutable, index, default)
├── TypeNode
│   ├── NamedTypeNode(name)                i32, i64, bool, or a structure name
│   └── ArrayTypeNode(element, size, size_text)
└── ExprNode
    ├── IntegerNode(value)                 digits without leading zeros
    ├── BooleanNode(value)                 True / False
    ├── IdentifierNode(name)
    ├── StringNode(value)                  escapes resolved
    ├── ReadNode()                         ану кажи
    ├── CallNode(name, arguments)
    ├── FieldAccessNode(object, field)
    ├── MemberCallNode(object, method, arguments)
    ├── NewObjectNode(structure, arguments)
    ├── IndexNode(object, index)           positioned at [
    ├── ArrayLiteralNode(elements)
    ├── ArrayFillNode(value)               [всюди value]
    ├── UnaryNode(operator, operand)       operator = neg
    └── BinaryNode(operator, left, right)  add sub mul div eq ne gt lt and or
```

Statements are positioned at their first keyword (`желєзобетонно`, `зуб`, `мутна`, `перевзувся`,
`базарь`, `всьо`, `якшо`). Operators are positioned at their first word (`не`
in `не рівно`, `ділити` in `ділити на`, `і` in `і ше`). Literals and names use
their own token positions; a block uses its first statement. The program uses
the first non-NEWLINE token, or EOF for empty input. Parentheses create no nodes.

`IntegerNode.value` is a normalized digit string (`0042` → `42`, `000` → `0`),
not a Python `int`, allowing arbitrarily long literals to remain valid syntax.
Range checks belong to semantic analysis.

See [README.md](README.md#ast-dump-format) for the `compiler.py --ast` dump format.

## 7. Implementation limits (not language rules)

- Parentheses, brackets, and conditions together may nest at most **100**
  levels. Deeper input reports `compilation error: … Занадто глибоко закопався: понад 100
  рівнів вкладеності (ліміт компілятора).` at the opening `(`, `[`, or `якшо`, instead
  of overflowing Python's stack. Long flat chains (`1 плюс 1 плюс …`,
  `мінус мінус … x`) are parsed and printed without recursion or that limit.
  The dump is streamed line by line; its indentation still makes the output
  of a very deep chain grow quadratically.
- The entire file is read into memory.
- Variables, arrays among them, live on the stack of the running program. An
  array of millions of elements can exceed the stack (often 8 MB) and crash
  the program; a copy that the program makes for a moment, such as an
  argument, needs room too.

## 8. Features absent from this version

String variables, logical NOT, floating-point numbers, and arrays whose
length is known only at run time are not part of the grammar. Strings exist
only as the operand of `базарь`.
