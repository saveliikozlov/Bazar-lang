# Bazar («Базар»)

Bazar is a small programming language with Ukrainian keywords and a surzhyk
style, as if a cheeky friend were explaining programming beside a garage.
`желєзобетонно` declares a compile-time constant, `зуб даю` an immutable
variable, `мутна тєма` a mutable one, and `перевзувся` assigns a new value.
Conditions start with `якшо реально`, may have an `а нє` branch, and end with
`отакої`. Functions start with `маю дєло`, structures with `такі діла`, and
both end with `порішали`. Source files use `.bazar`.

The compiler reads UTF-8 source, checks lexical and syntactic structure,
runs a semantic pass over the AST, and generates LLVM IR through the
`llvmlite` builder. The IR is built with `llc` and `clang` (or run with `lli`)
into a program that prints its results.

| Document | Contents |
| --- | --- |
| [grammar.ebnf](grammar.ebnf) | complete syntactic and lexical grammar |
| [LANGUAGE.md](LANGUAGE.md) | syntax, lexical rules, positions, AST, and semantics |
| [EXAMPLES.md](EXAMPLES.md) | example programs and common errors |
| [examples/](examples) | source files to try with the compiler |

## Build and run

Requirements: Python **3.9 or newer**, `llvmlite` (pinned in
`requirements.txt`), and LLVM's `llc`, `lli`, and `clang`. On macOS with
Homebrew:

```sh
brew install llvm
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Compile a program to LLVM IR, then run it with `lli`, or build a binary with
`llc` and `clang`:

```sh
.venv/bin/python compiler.py tests/run/point_read.bazar point_read.ll
/opt/homebrew/opt/llvm/bin/lli point_read.ll < tests/run/point_read.in
/opt/homebrew/opt/llvm/bin/llc -filetype=obj point_read.ll -o point_read.o
clang point_read.o -o point_read
./point_read < tests/run/point_read.in
```

Both runs read `3 4` and print `Всьо, розходимось: 25`. If the LLVM tools are
on your `PATH`, drop the `/opt/homebrew/opt/llvm/bin/` prefix. Print the AST
without generating code (this needs no `llvmlite`):

```sh
python3 compiler.py --ast examples/budget.bazar
python3 lexer.py examples/budget.bazar      # inspect tokens
```

Input files may have any extension, including `.bazar` and `.txt`.

| Result | Exit code | stdout | stderr | output.ll |
| --- | --- | --- | --- | --- |
| success | 0 | AST dump (`--ast`) or empty | empty | written |
| lexical, syntax, or semantic error | 1 | empty | one line: `compilation error: line L:C: MESSAGE` | not written |
| invalid arguments, unreadable input, unwritable output, no `llvmlite` | 2 | empty | one line | not written |

```text
compilation error: line 4:14: «ф» чекає 1 аргумент, а дали 2.
```

A compiled program exits with 0. A run-time overflow or division by zero
writes one line to stderr and exits with 1:

```text
помилка виконання: line 3:23: переповнення в «плюс», результат не влазить у тип
```

## Types and declarations

| Bazar type | Meaning | Range or values |
| --- | --- | --- |
| `дрібняк` | signed 32-bit integer (`i32`) | −2147483648 … 2147483647 |
| `крупняк` | signed 64-bit integer (`i64`) | −9223372036854775808 … 9223372036854775807 |
| `базар` | Boolean (`bool`) | `реально` (true), `гон` (false) |
| a structure name | an object of a `такі діла` structure | its fields |

A declaration always has a name, a type after `тіпа`, and an initial value
after `це`.

```text
зуб даю зарплата тіпа крупняк це 100
мутна тєма залишок тіпа крупняк це зарплата мінус 80
зуб даю ок тіпа базар це реально
перевзувся залишок тепер залишок мінус 15
```

| Declaration | Kind | Value known | Can change |
| --- | --- | --- | --- |
| `желєзобетонно` | constant (`const`) | at compile time | never |
| `зуб даю` | immutable variable (`let`) | at run time | never |
| `мутна тєма` | mutable variable (`let mut`) | at run time | with `перевзувся` |

`желєзобетонно` (literally "set in reinforced concrete") binds a name to a
value computed before the program runs. Its initializer is a constant
expression: literals, operators, parentheses, and constants declared
earlier. Constants are declared only at the top level.

```text
желєзобетонно ТИСЯЧА тіпа дрібняк це 1000
желєзобетонно МІЛЬЙОН тіпа крупняк це 1000 на 1000
желєзобетонно ВЕЛИКО тіпа базар це МІЛЬЙОН більше 999999
```

`МІЛЬЙОН` is written as `1000 на 1000`, not `ТИСЯЧА на ТИСЯЧА`: `ТИСЯЧА` is a
`дрібняк`, and there is no implicit conversion to `крупняк` (rule 9).

## Expressions

Operators below are listed from highest to lowest precedence. Parentheses
override precedence.

| Operators | Meaning | Associativity |
| --- | --- | --- |
| `.` field, `.f(…)` member call, `f(…)` call | access and calls | left |
| unary `мінус` | numeric negation | right |
| `на`, `ділити на` | multiplication, integer division | left |
| `плюс`, `мінус` | addition, subtraction | left |
| `рівно`, `не рівно`, `більше`, `менше` | `==`, `!=`, `>`, `<` | one comparison per expression level |
| `і ше` | logical AND, short-circuit | left |
| `або` | logical OR, short-circuit | left |

```text
зуб даю відповідь тіпа дрібняк це 2 плюс 3 на 4
зуб даю перевірка тіпа базар це відповідь не рівно 0 і ше реально або гон
```

`2 плюс 3 на 4` means `2 + (3 * 4)`. Comparisons cannot be chained: write
`a менше b і ше b менше c`. Operators are words; `+`, `-`, `==` are not
accepted. There is no logical NOT.

## Conditions

`якшо реально` has a nonempty body and ends with `отакої`. Its optional
`а нє` branch must also be nonempty. A single `отакої` closes the entire
condition; each nested condition has its own closing word.

```text
мутна тєма залишок тіпа крупняк це 5
якшо реально залишок більше 0
    базарь залишок
а нє
    базарь 0
отакої
```

The first `реально` belongs to the opening phrase, so an always-true
condition is `якшо реально реально`.

## Functions

`маю дєло` ("I have a business") declares a function with typed parameters
and a result type after `на виході` ("at the output"). `тримай` ("here, hold
it") leaves the function with a value; `порішали` ("settled") closes it. A
call is an expression, and its arguments may be calls too. A function may
call itself and any function declared below it.

```text
маю дєло факт(н тіпа крупняк) на виході крупняк
    якшо реально н менше 2
        тримай 1
    отакої
    тримай н на факт(н мінус 1)
порішали
базарь факт(20)
```

A call made only for its effect stands on its own line: `порахуй(1, 2)`.

## Structures

`такі діла` ("such are the things") declares a structure. Fields are declared
like variables: `зуб даю` makes a constant field, `мутна тєма` a mutable
one. `склепай` ("knock together") creates an object with values for the
fields in field order. Fields are read through a chain, `к.центр.х`, and
assigned through `перевзувся`.

```text
такі діла Точка
    мутна тєма х тіпа дрібняк
    зуб даю у тіпа дрібняк
порішали
такі діла Коло
    мутна тєма центр тіпа Точка
    зуб даю радіус тіпа дрібняк
порішали
мутна тєма к тіпа Коло це склепай Коло(склепай Точка(1, 2), 5)
перевзувся к.центр.х тепер к.центр.у плюс к.радіус
базарь к.центр.х
```

## Member functions

A `маю дєло` inside `такі діла` is a member function. Its body sees the
fields and the other member functions of the structure by name. It is called
on an object: `п.д2()`.

```text
такі діла Точка
    мутна тєма х тіпа дрібняк
    зуб даю у тіпа дрібняк
    маю дєло посунь(дх тіпа дрібняк) на виході дрібняк
        перевзувся х тепер х плюс дх
        тримай х
    порішали
    маю дєло д2() на виході дрібняк
        тримай х на х плюс у на у
    порішали
порішали
мутна тєма п тіпа Точка це склепай Точка(3, 4)
п.посунь(1)
всьо розходимось п.д2()
```

`посунь` assigns a field, so it may be called only on a mutable object.

## Input and output

`ану кажи` ("come on, tell") reads one integer from standard input.
`базарь` prints an integer, a `базар`, a string literal, or an object.
`всьо розходимось` ends the program and prints its result.

```text
такі діла Точка
    зуб даю х тіпа дрібняк
    зуб даю у тіпа дрібняк
    маю дєло д2() на виході дрібняк
        тримай х на х плюс у на у
    порішали
порішали
зуб даю п тіпа Точка це склепай Точка(ану кажи, ану кажи)
базарь "Привіт, \"базар\"!"
базарь п
всьо розходимось п.д2()
```

With input `3 4` this prints:

```text
Привіт, "базар"!
Точка { х: 3, у: 4 }
Всьо, розходимось: 25
```

## Extra feature: auto constructor

A field may have a default after `це`, a constant expression. `склепай`
fills the fields from the left; every field left out takes its default. A
field whose type is a structure takes no `це`: it is built automatically
when every field of its structure has a default.

```text
такі діла Точка
    мутна тєма х тіпа дрібняк це 0
    мутна тєма у тіпа дрібняк це мінус 1
порішали
такі діла Коло
    мутна тєма центр тіпа Точка
    зуб даю радіус тіпа крупняк це 10
порішали
базарь склепай Точка(5)      чутки: Точка { х: 5, у: -1 }
базарь склепай Коло()        чутки: Коло { центр: Точка { х: 0, у: -1 }, радіус: 10 }
```

The defaults are a constant built at compile time, so `склепай Коло()`
costs no instructions at run time. See also the [VS Code
extension](#vs-code-extension).

## Semantic rules

The semantic pass ([semantic.py](semantic.py)) runs on the AST before code
generation. It reports the first broken rule as a compilation error at the
node that broke it. Each rule has a program in `tests/run` or `tests/valid`
that follows it and one in `tests/invalid` that breaks it (named in brackets).

**Declarations and names**

1. All structures and function signatures are collected before any body is
   checked, so a call may name a function declared below
   [`functions_recursion_and_forward_calls` / `semantic_unknown_function`].
2. Structures, functions, and values are separate namespaces. Two structures
   or two functions cannot share a name, and a function cannot be named like
   a structure [`semantic_duplicate_function`,
   `semantic_function_named_like_structure`].
3. Inside a structure, field names and member function names are unique and
   do not share names; parameter names of one function are unique
   [`semantic_duplicate_field`, `semantic_method_named_like_field`,
   `semantic_duplicate_parameter`]. A structure cannot be named `i32`,
   `i64`, or `bool`, the AST spellings of the built-in types
   [`semantic_structure_named_i32`].
4. A name is declared before use and once per scope; an initializer cannot
   see the name it declares. Each `якшо` and `а нє` block is a child scope,
   and an inner declaration may shadow an outer one [`scopes_and_shadowing` /
   `semantic_redeclared_in_same_scope`, `semantic_name_invisible_outside_block`].

**What a body sees**

5. The main program sees its own variables and the constants declared above.
6. A function body sees its parameters, its locals, and every constant, but
   not the main program's variables. Parameters and the outer block of the
   body are one scope, so a local cannot redeclare a parameter
   [`constants_everywhere` / `semantic_function_sees_no_main_variables`,
   `semantic_local_redeclares_parameter`].
7. Inside a member function, a name is looked up among the parameters and
   locals, then the fields of the structure, then the constants. A parameter
   `х` hides a field `х`, and a field hides a constant `х`
   [`lookup_parameter_field_constant`].
8. A bare call inside a member function finds the structure's member
   functions first, then the top-level functions
   [`bare_call_finds_member_first`].

**Types**

9. There is no implicit conversion between `дрібняк`, `крупняк`, and
   `базар`. Arithmetic needs two integers of one type; `більше` and `менше`
   compare integers; `рівно` and `не рівно` compare two integers or two
   Booleans of one type, never objects; a condition is a `базар`
   [`semantic_mixed_integer_widths`, `semantic_arithmetic_on_bool`,
   `semantic_condition_not_bool`, `semantic_compare_objects`].
10. Integer literals and `ану кажи` take their type from context; with no
    context they are `крупняк`. A literal must fit its type
    [`integer_widths_and_read` / `semantic_literal_too_large_for_i32`,
    `semantic_read_in_bool_context`].
11. A call has exactly as many arguments as parameters, and each argument
    has exactly its parameter's type [`nested_call_arguments` /
    `semantic_too_many_arguments`, `semantic_too_few_arguments`,
    `semantic_argument_wrong_type`, `semantic_argument_wider_integer`].
12. `тримай` is allowed only in a function body, and its value has exactly
    the function's result type [`semantic_return_wrong_type`,
    `semantic_return_outside_function`].
13. Every path through a function ends with `тримай`: the body ends with it,
    or with a `якшо … а нє … отакої` whose branches both do. Nothing follows
    `тримай` in its block [`semantic_missing_return_path`,
    `semantic_statement_after_return`].
14. `всьо розходимось` takes an integer and is allowed only in the main
    program [`exit_stops_the_program` / `semantic_exit_inside_function`,
    `semantic_exit_with_bool`].
15. A structure may be the type of a variable, a parameter, a result, or a
    field, but cannot contain itself, directly or through other fields
    [`semantic_structure_contains_itself`].
16. `склепай Т(…)` names an existing structure and gives values of the field
    types in field order; fields left out need a default
    [`auto_constructor` / `semantic_new_object_wrong_value_type`,
    `semantic_new_object_field_without_default`].
17. `о.поле` needs an object with that field; `о.ф(…)` needs a member
    function with that name [`semantic_unknown_field`,
    `semantic_unknown_method`, `semantic_field_of_integer`].
18. Objects are values: a declaration, an argument, a result, or an
    assignment copies the whole object [`objects_are_copied`].

**Mutability**

19. `перевзувся х` needs a `мутна тєма` variable; constants, `зуб даю`
    variables, and parameters cannot be assigned
    [`semantic_assign_to_constant`, `semantic_immutable_assignment`,
    `semantic_assign_to_parameter`].
20. `перевзувся а.б.в` needs a chain that is mutable at every step: `а` is a
    `мутна тєма` variable and `б` and `в` are `мутна тєма` fields. Inside a
    member function a chain may start at a field [`field_chain_assignment` /
    `semantic_assign_through_constant_variable`,
    `semantic_assign_constant_field`, `semantic_assign_through_constant_chain`,
    `semantic_method_assigns_constant_field`].
21. A member function is mutating when it assigns a field of its own object,
    or calls a mutating member function on its own object or one of its
    fields. The flag is recomputed until it stops changing.
22. A mutating member function may be called only on a chain that is mutable
    at every step; not on a `зуб даю` variable, a parameter, a constant
    field, or a temporary value [`mutation_through_members` /
    `semantic_mutating_call_on_constant_object`,
    `semantic_mutating_call_on_parameter`,
    `semantic_mutating_call_on_temporary`,
    `semantic_mutating_call_through_member`].

**Output and overflow**

23. `базарь` prints integers in decimal, Booleans as `реально` or `гон`,
    strings as written, and an object as its type and its fields:
    `Коло { центр: Точка { х: 1, у: 2 }, радіус: 5 }`. Every `базарь` ends
    with one newline; a `\n` inside a string adds another
    [`print_objects_nested`, `print_strings_and_bools`].
24. `всьо розходимось N` prints `Всьо, розходимось: N` on its own line and
    exits with 0; statements after it do not run.
25. Overflow is an error, never a wraparound: the lexer rejects literals that
    fit no type, the semantic pass rejects literals and constant values that
    do not fit their type, and the generated code checks `плюс`, `мінус`,
    `на`, `ділити на`, and negation at run time. Division truncates toward
    zero; dividing by zero or `MIN ділити на мінус 1` is a run-time error
    [`runtime_overflow`, `runtime_division_by_zero`,
    `semantic_constant_overflow`, `semantic_constant_division_by_zero`].

## Code generation

[codegen.py](codegen.py) builds the module with `llvmlite.ir`; the only IR
text the compiler writes is `str(module)`.

- **Structures**: an identified struct type `bz.Точка` per structure. An
  object is an alloca of it; a field is reached with a `gep` by the field's
  index from the symbol table.
- **Functions**: `bz.NAME` per function and `bz.Точка.NAME` per member
  function, whose first parameter is a pointer to the object. Every function
  is declared before any body, so forward calls resolve. The `bz.` prefix
  keeps a function named `main` or `printf` apart from the C runtime.
- **Runtime**: `printf`, `scanf`, `write`, and `exit` are declared without
  bodies and linked by `clang`. Format strings are private global constants.
  Printing an object walks the field table with one `gep`, `load`, and
  `printf` per field, so a new structure prints without new compiler code.
- **Variables** are allocas in the function's entry block. Arithmetic uses
  the `llvm.s*.with.overflow` intrinsics.

## Source format

Source files use UTF-8 without a byte order mark.

- Names start with an ASCII letter, a Cyrillic letter (`А–Я`, `а–я`, `Ё`, `ё`),
  a Ukrainian letter (`І`, `і`, `Ї`, `ї`, `Є`, `є`, `Ґ`, `ґ`), or `_`, and may
  continue with ASCII digits. An apostrophe (`'` or `ʼ`) may stand between
  two letters, as in `з'їзд`.
- Keywords are case-sensitive, and every word of a phrase is independently
  reserved, including `а`, `нє`, `і`, `ше`, `маю`, `дєло`, `такі`, `діла`,
  `ану`, and `кажи`.
- Integers are decimal digit sequences from `0` to `9223372036854775807`;
  negative values use unary `мінус`. `12abc`, `0x1F`, and `1.5` are invalid.
- `(`, `)`, `,`, and `.` are the only punctuation. A string literal stands
  between double quotes on one line, only after `базарь`; it accepts the
  escapes `\n`, `\"`, and `\\`.
- Each statement occupies its own line; conditions, functions, and
  structures span several. `чутки:` starts a comment through the end of the
  line.

Lines and columns start at 1, and columns count **UTF-8 bytes**: a Cyrillic
letter uses two bytes, an emoji four, and a tab one. Diagnostics stay in
Ukrainian surzhyk and name what was expected and found.

## AST dump format

For `зуб даю x тіпа дрібняк це 1`, `--ast` prints:

```text
ProgramNode line=1 column=1
  DeclarationNode line=1 column=1 name=x type=i32 mutable=false
    initializer:
      IntegerNode line=1 column=46 value=1
```

Each node prints its class, position, and scalar fields; children appear
under labels, indented by two spaces per level. Stage 2 nodes print their
flags: `FunctionNode` its `result` and `parameters` (each with a `type`),
`FieldNode` its `type`, `mutable`, `index`, and `default`, `CallNode` and
`MemberCallNode` their `arguments`, and `CallStatementNode`
`member_call=true` when the chain ends in a member call. A list prints its
items under the label, or `label: []` when empty. Types are `i32`, `i64`,
`bool`, or a structure name.

## Tests

Run from the repository root:

```sh
.venv/bin/python check.py
.venv/bin/python -m unittest discover -s tests -v
```

`check.py` runs every test through the real CLI, says which ones failed, and
exits nonzero if any did:

| Folder | Count | Check |
| --- | --- | --- |
| `tests/valid` | 48 | `--ast` output equals `NAME.ast` (front-end tests; some Stage 1 ones use undeclared names on purpose) |
| `tests/invalid` | 203 | compiling exits 1, prints exactly `NAME.err`, and writes no file |
| `tests/run` | 19 | end to end: compiled, run with `lli` (or built with `llc` and `clang`), stdout equals `NAME.expected`; `NAME.in` is stdin; `NAME.error` is the expected run-time error |
| `examples` | 8 | compiling succeeds |

LLVM tools are looked up in `$LLVM_BIN`, then on `PATH`, then in the
Homebrew folders. The 96 unit tests cover the lexer, the parser, the semantic
pass's symbol table and annotations, and the CLI.

## VS Code extension

The extension adds syntax highlighting, completion, keyword explanations,
and error underlines to `.bazar` files. As an extra of Stage 2, the
underlines come from the compiler's own semantic pass, so a wrong argument
count, an unknown field, or a mutating call on a constant object is shown
while you type, not only syntax errors. Build and install it with Node.js
22+ and npm:

```sh
cd vscode
npm ci
npm run package
code --install-extension dist/bazar.vsix
```

Hover over a keyword or a word in a phrase such as `зуб даю` or `маю дєло` to
see its meaning, grammar rule, and example. Run **Bazar: Keyword Dictionary**
from the Command Palette to open the complete reference. Error underlines
require Python 3.9 or newer, set with `bazar.pythonPath`. See
[vscode/README.md](vscode/README.md).

## Implementation

```text
grammar.ebnf  LANGUAGE.md  EXAMPLES.md  README.md  requirements.txt
lexer.py       byte-oriented lexer state machine
parser.py      recursive-descent parser, one method per grammar rule
ast_nodes.py   AST classes and stable dump
semantic.py    semantic pass and symbol table
codegen.py     LLVM IR through the llvmlite builder
compiler.py    command-line interface
check.py       test runner: AST, errors, and end-to-end runs
examples/      sample programs
tests/         fixtures, expected results, and unit tests
```
