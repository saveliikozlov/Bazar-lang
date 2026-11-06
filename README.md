# Bazar («Базар»)

Bazar is a small programming language with Ukrainian keywords and a surzhyk
style, as if a cheeky friend were explaining programming beside a garage.
`желєзобетонно` declares a compile-time constant, `зуб даю` an immutable
variable, `мутна тєма` a mutable one, and `перевзувся` assigns a new value.
Conditions start with `якшо реально`, may have an `а нє` branch, and end with
`отакої`. Loops start with `крутимось` and end with `докрутились`. Functions
start with `маю дєло`, structures with `такі діла`, and both end with
`порішали`. Fixed-size arrays have types like `[дрібняк; 5]` and are filled
with `[всюди 0]`. `може дрібняк` holds `шось(5)` or `нема`, and
`вийде дрібняк або облом крупняк` holds `вийшло(5)` or `облом(404)`.
`розбери` matches a value against patterns, and the compiler checks that
its `випадок` arms cover every value. `з?` takes the value out of a `може` or
a `вийде`, or returns `нема` or `облом` from the function, and
`базарь "Разом: {сума} грн"` prints values inside a string. Source files use
`.bazar`.

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
/opt/homebrew/opt/llvm/bin/llc -relocation-model=pic -filetype=obj point_read.ll -o point_read.o
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
| lexical, syntax, or semantic error, or an expression too deep to compile | 1 | empty | one line: `compilation error: line L:C: MESSAGE` | not written |
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
| `[TYPE; SIZE]` | a fixed-size array of SIZE elements of TYPE | SIZE from 1 to 2147483647 |
| `може TYPE` | an optional value (`Option`) | `шось(x)` or `нема` |
| `вийде TYPE або облом TYPE` | a result or an error (`Result`) | `вийшло(x)` or `облом(e)` |

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
| `.` field, `.f(…)` member call, `f(…)` call, `[і]` element | access and calls | left |
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

## Loops

The feature of Stage 3. `крутимось` ("we keep spinning") opens a loop and
`докрутились` ("we've spun enough") closes it. `харе` ("enough!") leaves the
innermost loop.

`крутимось поки` checks its condition before every pass. This program
([examples/loop_countdown.bazar](examples/loop_countdown.bazar)) reads a number
and counts down; with input `3` it prints `3`, `2`, `1`, `Поїхали!`:

```text
мутна тєма н тіпа дрібняк це ану кажи
крутимось поки н більше 0
    базарь н
    перевзувся н тепер н мінус 1
докрутились
базарь "Поїхали!"
```

`крутимось NAME тіпа TYPE від A по B` runs its counter over an integer range,
with both ends included. This program
([examples/loop_primes.bazar](examples/loop_primes.bazar)) has a loop inside a
loop, a variable declared in the body, and `харе`; it prints the primes up to 20:

```text
крутимось число тіпа дрібняк від 2 по 20
    мутна тєма просте тіпа базар це реально
    крутимось дільник тіпа дрібняк від 2 по число мінус 1
        якшо реально (число ділити на дільник) на дільник рівно число
            перевзувся просте тепер гон
            харе
        отакої
    докрутились
    якшо реально просте
        базарь число
    отакої
докрутились
```

`від` and `по` are not reserved: they mean something only in a loop header and
stay ordinary names everywhere else, so Stage 2 programs that use them remain
valid [`loop_range_words_stay_names`]. The four new reserved words are
`крутимось`, `поки`, `докрутились`, and `харе`.

### Loops in the IR

This is the output for a loop that prints `к` from 1 to 3
(`крутимось к тіпа дрібняк від 1 по 3`):

```llvm
body:
  store i32 1, i32* %"к"
  %".3" = icmp sle i32 1, 3
  br i1 %".3", label %"for.body", label %"for.end"
for.body:
  %"к.1" = load i32, i32* %"к"
  %".5" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([4 x i8], [4 x i8]* @"str.0", i32 0, i32 0), i32 %"к.1")
  br label %"for.step"
for.step:
  %"к.2" = load i32, i32* %"к"
  %".7" = icmp eq i32 %"к.2", 3
  br i1 %".7", label %"for.end", label %"for.next"
for.next:
  %".9" = add nsw i32 %"к.2", 1
  store i32 %".9", i32* %"к"
  br label %"for.body"
for.end:
  ret i32 0
```

The first block stores the start in the counter's alloca and skips the loop
when the start is above the end. `for.step` compares the counter with the end
before it grows, so a range ending at the type's largest value stops without
overflow; only when another pass remains does `for.next` add 1. The
`br label %"for.body"` at the end of `for.next` is the back edge, the only jump
backwards, and `харе` is a plain `br` to `for.end`. A `крутимось поки` has three
blocks, `while.cond`, `while.body`, and `while.end`, and its back edge goes from
the body to `while.cond`.

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

## Extra feature: arrays

An array holds a fixed number of values of one type. Its type is
`[ELEMENT; SIZE]`, where SIZE is a constant expression from 1 to 2147483647
that may use constants. `[1, 2, 3]` lists the elements, and `[всюди 0]`
("everywhere") repeats one value: its length comes from the array type
expected there. `м[і]` is an element, counted from 0, and `м.розмір` is the
length.

```text
желєзобетонно Н тіпа дрібняк це 3
мутна тєма м тіпа [дрібняк; Н] це [10, 20, 30]
мутна тєма сітка тіпа [[дрібняк; 2]; 2] це [[1, 2], [всюди 0]]
перевзувся м[0] тепер м[1] плюс м[2]
перевзувся сітка[1][0] тепер м.розмір
базарь м
базарь сітка
базарь м рівно [50, 20, 30]
крутимось ціна тіпа дрібняк з м
    базарь ціна
докрутились
```

This prints `[50, 20, 30]`, `[[1, 2], [3, 0]]`, `реально`, and then `50`, `20`,
and `30` on separate lines. `крутимось ціна тіпа дрібняк з м` gives the counter
every element in turn. Like `від` and `по`, the word `з` means this only in a
loop header and stays an ordinary name elsewhere; `всюди` is the one new
reserved word. Arrays are values like objects: a declaration, an argument, a
result, or an assignment copies the whole array. `рівно` and `не рівно`
compare arrays element by element. An index known at compile time must be
inside the array; any other is checked when the program runs:

```text
помилка виконання: line 3:17: номер за межами масиву: тут можна від 0 до 2
```

See [examples/arrays.bazar](examples/arrays.bazar), which sorts prices read
from standard input.

### Arrays and objects in the IR

An array is an LLVM array type, `[3 x i32]`. Arrays and objects are never
loaded or stored as whole values, because LLVM compiles those in time that
grows faster than the size of the value: copying a 50 000-element array that
way took 14 seconds. They stay in memory instead. A copy is one call to
`llvm.memcpy`, an array or object parameter is a pointer the callee only
reads, and an array or object result is written through a hidden first
parameter that points to memory of the caller. Filling, printing, comparing,
and `крутимось … з` are loops at run time, so compiling a program takes the
same time whatever the sizes of its arrays. A value of 1 KiB or more does not
live on the stack, which is often only 8 MB: its function allocates it once on
the heap and frees it before every `ret`, so arrays of millions of elements
work, and running out of memory is a run-time error, not a crash. This is the
code for
`перевзувся м[к] тепер 5`, where `м` is a `[дрібняк; 3]` and `к` a `дрібняк`:

```llvm
  %"к.1" = load i32, i32* %"к"
  %".19" = sext i32 %"к.1" to i64
  %".20" = icmp uge i64 %".19", 3
  br i1 %".20", label %"fail", label %"ok"
fail:
  %".22" = call i64 @"write"(i32 2, i8* getelementptr ([124 x i8], [124 x i8]* @"str.1", i32 0, i32 0), i64 123)
  call void @"exit"(i32 1)
  unreachable
ok:
  %".25" = getelementptr [3 x i32], [3 x i32]* %"м", i32 0, i64 %".19"
  store i32 5, i32* %".25"
```

One unsigned comparison catches both a negative index and one past the end.
An index known at compile time has no check.

## Extra feature: може and вийде

`може T` ("maybe") holds a value, `шось(x)` ("something"), or nothing, `нема`
("there is none"). `вийде T або облом E` ("it will work out, or a flop") holds
a result, `вийшло(x)` ("it worked out"), or an error, `облом(e)`. `шось(5)`
alone is a `може крупняк`; the other three values take their type from the
type expected there, like `[всюди 0]`. `з.шось`, `з.нема`, `р.вийшло`, and
`р.облом` check which value is held, and `з або x` gives the value held in
`з`, or `x`, which runs only when `з` holds `нема` or `облом`:

```text
маю дєло ділення(а1 тіпа дрібняк, б1 тіпа дрібняк) на виході вийде дрібняк або облом крупняк
    якшо реально б1 рівно 0
        тримай облом(404)
    отакої
    тримай вийшло(а1 ділити на б1)
порішали
зуб даю р тіпа вийде дрібняк або облом крупняк це ділення(7, 0)
базарь р
базарь р.облом
базарь р або мінус 1
зуб даю з тіпа може дрібняк це нема
базарь (з або 5) плюс 1
базарь шось(5) рівно шось(5)
```

This prints `облом(404)`, `реально`, `-1`, `6`, and `реально`. On a `базар`,
`або` is logical OR as before. As a fallback it keeps OR's precedence, the
lowest, so `(з або 5) плюс 1` needs its parentheses. `рівно` compares the
tags first, and the values only when both hold one. Both types are values,
copied like arrays and objects; in memory `може T` is `{i1, T}` and
`вийде T або облом E` is `{i1, T, E}`, whose tag is 1 for `шось` and `вийшло`.
Pattern matching and the `?` operator will add more ways to take the value
out. See [examples/variants.bazar](examples/variants.bazar).

## Extra feature: розбери

`розбери X` ("sort it out") evaluates X once and runs the body of the first
`випадок` ("case") whose pattern matches; `розібрали` ("sorted out") closes it.
A pattern is `_`, which matches anything; a name, which matches anything and
binds the value to a new immutable variable; an integer or `реально`/`гон`;
`шось(P)`, `нема`, `вийшло(P)`, or `облом(P)`; a structure `Точка(P, P)` with
one pattern per field; or alternatives joined by `або`. `якшо реально E` after
a pattern adds a guard:

```text
маю дєло опиши(з тіпа може вийде дрібняк або облом базар) на виході дрібняк
    розбери з
    випадок нема
        тримай 0
    випадок шось(вийшло(н)) якшо реально н менше 0
        тримай мінус 1
    випадок шось(вийшло(н))
        тримай н
    випадок шось(облом(реально)) або шось(облом(гон))
        тримай 99
    розібрали
порішали
базарь опиши(шось(вийшло(мінус 7)))
базарь опиши(шось(облом(гон)))
```

This prints `-1` and `99`. The compiler checks the arms with the usefulness
algorithm of Luc Maranget ([exhaustiveness.py](exhaustiveness.py)). When
a value has no arm, the error names one; remove the last arm above and it says

```text
compilation error: line 2:5: Не всі випадки розібрано: шо робити з «шось(облом(_))»? Додай для нього «випадок» або «випадок _». Випадки з «якшо реально» не рахуються: їхня умова може не справдитись.
```

The last sentence appears because the match has a guarded arm.

An arm that can never run is an error too, such as `випадок шось(вийшло(5))`
below `випадок шось(_)`. Integers are covered only by `_` or a name, `базар`
by `реально` and `гон`. An arm with a guard does not count toward covering
every value, because its condition may be false. A `розбери` whose arms all
end with `тримай` ends the function. `_` is the wildcard only in a pattern;
elsewhere it stays an ordinary name. See [examples/match.bazar](examples/match.bazar).

In the IR the value is stored once, and the arms are tried in order: each
part of a pattern is a load and a comparison that jumps to the next arm when
it fails, and a name is a copy into its own alloca. After the last arm comes
`unreachable`, because some arm always matches.

## Extra feature: the ? operator

`з?` is the value that `шось` or `вийшло` holds. When `з` holds `нема` or
`облом`, the function returns that value at once, so a chain of steps that
may fail reads like a chain that cannot:

```text
маю дєло ділення(а1 тіпа дрібняк, б1 тіпа дрібняк) на виході вийде дрібняк або облом крупняк
    якшо реально б1 рівно 0
        тримай облом(404)
    отакої
    тримай вийшло(а1 ділити на б1)
порішали
маю дєло середнє(а1 тіпа дрібняк, б1 тіпа дрібняк, д тіпа дрібняк) на виході вийде дрібняк або облом крупняк
    зуб даю сума тіпа дрібняк це ділення(а1, д)? плюс ділення(б1, д)?
    тримай вийшло(сума)
порішали
базарь середнє(10, 20, 2)
базарь середнє(10, 20, 0)
```

This prints `вийшло(15)` and `облом(404)`. `?` on a `може` needs a function
that returns a `може`; on a `вийде … або облом E` it needs one that returns a
`вийде` with the same error type E, because no error is converted. `?` binds
more tightly than any operator and is a step of a chain, so
`м.перша()?.ціна`, `з?[0]`, and `з??` work, and a call that ends in `?`, such
as `запиши(х)?`, may stand on its own line. In the main program there is no
function to return from, so `нема` or `облом` stops the program like an
overflow:

```text
помилка виконання: line 13:34: «?» отримав «облом» замість «вийшло»
```

for `базарь ділення(1, 0)?` on line 13. In the IR, `?` is a branch on the
tag: one side goes on with the value, and the other writes `нема`, or `облом`
with its error, to the caller's result and returns. See
[examples/try.bazar](examples/try.bazar).

## Extra feature: string interpolation

A string printed by `базарь` may hold `{…}` parts. Each holds one
expression of any type, and its value is printed in its place exactly as
`базарь` would print it alone. `\{` and `\}` write braces:

```text
зуб даю ціна тіпа крупняк це 25
зуб даю кошик тіпа [крупняк; 2] це [ціна, 40]
зуб даю знижка тіпа може крупняк це нема
базарь "Разом: {ціна на 4} грн, кошик {кошик}, знижка {знижка або 0}%"
базарь "Так пишуть дужки: \{ і \}"
```

This prints `Разом: 100 грн, кошик [25, 40], знижка 0%` and
`Так пишуть дужки: { і }`. The values run from left to right, each just
before it is printed, so a function that prints inside `{…}` prints after the
text in front of its part. An error inside the braces points at its place in
the line:

```text
compilation error: line 1:30: У «{…}» один вираз: після нього чекаю «}», а тут число 2.
```

for `базарь "Разом: {1 2}"`. The lexer reads each part as its own run of
tokens and the parser as one expression, so a string without `{…}` stays a
plain string. In the IR every value is one `printf` with the text in front
of it, which is escaped so that `%` prints as itself. See
[examples/interpolation.bazar](examples/interpolation.bazar).

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
   compare integers; `рівно` and `не рівно` compare two values of one type
   built from integers and Booleans (arrays, `може`, `вийде`), never objects;
   a condition is a `базар`
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
    or with a `якшо … а нє … отакої` whose branches both do, or with a
    `розбери` whose arms all do (rule 46). Nothing follows
    `тримай` in its block [`semantic_missing_return_path`,
    `semantic_statement_after_return`].
14. `всьо розходимось` takes an integer and is allowed only in the main
    program [`exit_stops_the_program` / `semantic_exit_inside_function`,
    `semantic_exit_with_bool`].
15. A structure may be the type of a variable, a parameter, a result, a
    field, or an array element, but cannot contain itself, directly or
    through other fields, arrays, `може`, and `вийде`
    [`semantic_structure_contains_itself`, `array_structure_contains_itself`,
    `variant_structure_contains_itself`].
16. `склепай Т(…)` names an existing structure and gives values of the field
    types in field order; fields left out need a default
    [`auto_constructor` / `semantic_new_object_wrong_value_type`,
    `semantic_new_object_field_without_default`].
17. `о.поле` needs an object with that field; `о.ф(…)` needs a member
    function with that name [`semantic_unknown_field`,
    `semantic_unknown_method`, `semantic_field_of_integer`].
18. Objects are values: a declaration, an argument, a result, or an
    assignment copies the whole object, and no copy shares memory with the
    original [`objects_are_copied`, `objects_in_memory_never_alias`].

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
    strings as written, an object as its type and its fields:
    `Коло { центр: Точка { х: 1, у: 2 }, радіус: 5 }`, an array as its
    elements: `[1, 2, 3]`, and the values of `може` and `вийде` as they are
    written: `шось(5)`, `нема`, `вийшло(5)`, `облом(404)`. Every `базарь` ends
    with one newline; a `\n` inside a string adds another, and `%` prints as
    itself [`print_objects_nested`, `print_strings_and_bools`].
24. `всьо розходимось N` prints `Всьо, розходимось: N` on its own line and
    exits with 0; statements after it do not run.
25. Overflow is an error, never a wraparound: the lexer rejects literals that
    fit no type, the semantic pass rejects literals and constant values that
    do not fit their type, and the generated code checks `плюс`, `мінус`,
    `на`, `ділити на`, and negation at run time. Division truncates toward
    zero; dividing by zero or `MIN ділити на мінус 1` is a run-time error,
    and so is an array index out of range (rule 35)
    [`runtime_overflow`, `runtime_division_by_zero`,
    `semantic_constant_overflow`, `semantic_constant_division_by_zero`].

**Loops**

26. The condition of `крутимось поки` is a `базар`, with no implicit
    conversion [`loop_while_countdown` / `loop_condition_not_bool`].
27. A range loop states the counter's type, which is `дрібняк` or `крупняк`.
    Both bounds have exactly that type. They are evaluated once, the start
    first, before the first pass, and they cannot see the counter
    [`loop_for_inclusive_range` / `loop_counter_not_integer`,
    `loop_counter_structure_type`, `loop_counter_unknown_type`,
    `loop_bound_wrong_type`, `loop_bound_literal_too_large`,
    `loop_bound_sees_no_counter`].
28. The counter cannot be assigned. The counter and the outer block of the
    body are one scope, so a local cannot redeclare it, and the counter is
    invisible after the loop [`loop_counter_assigned`,
    `loop_body_redeclares_counter`, `loop_counter_invisible_after`].
29. A range includes both ends. A start above the end means no pass at all. A
    range ending at the largest value of its type stops without overflow
    [`loop_for_inclusive_range`, `loop_for_at_type_maximum`].
30. The body is nonempty and is a child scope: an inner declaration may shadow
    an outer one, it is invisible after the loop, and it is initialized again
    on every pass [`loop_body_declares_variable` / `loop_empty_body`,
    `loop_body_variable_invisible_after`].
31. `харе` is allowed only inside a loop, directly or in a nested `якшо`, and
    leaves only the innermost loop. A function body starts outside any loop,
    even when the function is called from one. Nothing follows `харе` in its
    block [`loop_nested_with_break` / `loop_break_outside`,
    `loop_break_in_condition_outside`, `loop_break_in_function_body`,
    `loop_statement_after_break`].
32. A loop never counts as "every path ends with `тримай`", not even
    `крутимось поки реально`, so a function still needs a `тримай` after it.
    `тримай` and `всьо розходимось` may leave from inside a loop
    [`loop_leaves_function_and_program` / `loop_function_needs_return_after`].

**Arrays**

33. In `[T; N]`, N is a constant integer expression from 1 to 2147483647.
    It may name constants: a signature or a field sees every constant, and a
    statement sees the constants its expressions see (rules 5–7), unless a
    variable hides the name. An array may be the type of a variable, a
    parameter, a result, a field, or an element, but not of a constant, and
    an array field has no `це`. Nested lengths multiply, and one array value
    may take at most 2^40 bytes (1 TiB) [`arrays_types_and_literals`,
    `arrays_huge` /
    `array_size_zero`, `array_size_negative`, `array_size_not_constant`,
    `array_size_bool`, `array_size_call`,
    `array_size_constant_declared_below`, `array_size_constant_shadowed`,
    `array_constant`, `array_field_default`, `array_too_large`,
    `array_of_structures_too_large`].
34. `[a, b, c]` has at least one element, all of one type; the length and
    the element type are part of its type, so `[дрібняк; 2]` is not a
    `[дрібняк; 3]`. An expected array type gives its element type to literals
    inside. `[всюди x]` needs an expected array type, from a declaration, an
    assignment, an argument, a result, or an enclosing literal; `x` runs once
    [`arrays_basics` / `array_literal_empty`, `array_literal_mixed_types`,
    `array_literal_length_mismatch`, `array_literal_element_too_big`,
    `array_fill_without_type`, `array_fill_wrong_element`,
    `array_whole_wrong_length`].
35. `м[і]` needs an array and an integer of either width. An index known at
    compile time (literals, constants, `розмір`, and arithmetic on them) must
    be from 0 to the length minus 1; any other index out of range stops the
    program with a run-time error and exit code 1 [`arrays_index_out_of_range`,
    `arrays_negative_index` / `array_index_constant_out_of_range`,
    `array_index_negative_constant`, `array_index_length_out_of_range`,
    `array_index_not_integer`, `array_index_not_array`].
36. `м.розмір` is the length, known at compile time. It takes an integer type
    from context like a literal, but without context it is `дрібняк`. It
    cannot be assigned, and an array has no other field [`arrays_basics` /
    `array_length_assigned`, `array_no_such_field`].
37. `перевзувся м[і].х тепер …` needs a chain that is mutable at every step,
    as in rule 20; an element is as mutable as its array. Arrays are values,
    like objects (rule 18). `рівно` and `не рівно` compare arrays of comparable
    elements element by element; arithmetic, `більше`, `менше`, and
    `всьо розходимось` take no arrays [`arrays_are_values` /
    `array_element_of_immutable`, `array_element_wrong_type`,
    `array_compare_structures`, `array_arithmetic`, `array_exit_value`].
38. `крутимось е тіпа T з м` needs an array whose element type is exactly T.
    The array is evaluated once, before the first pass, and cannot see the
    counter; the loop walks that value, so changing `м` in the body changes
    no pass. The counter is each element in turn, cannot be assigned, and is
    scoped like a range loop's counter (rules 28, 30, 31)
    [`arrays_for_each` / `array_for_each_counter_type`,
    `array_for_each_not_array`, `array_for_each_counter_assigned`,
    `array_for_each_fill`].

**може and вийде**

39. `може T` and `вийде T або облом E` take any types, and are the types of
    variables, parameters, results, fields, and elements, but not of
    constants, and a field of them has no `це`. `шось(x)` is a `може` of the
    type of x unless a `може` is expected; `нема` needs an expected `може`, and
    `вийшло(x)` and `облом(e)` an expected `вийде`, whose types x and e have
    exactly [`variants_basics` / `variant_none_without_type`,
    `variant_ok_without_type`, `variant_err_for_option`,
    `variant_none_for_integer`, `variant_some_wrong_type`,
    `variant_err_wrong_type`, `variant_both_sides_need_type`,
    `variant_constant`, `variant_field_default`].
40. `з.шось` and `з.нема` need a `може`, `р.вийшло` and `р.облом` a `вийде`;
    each is a `базар`, takes no parentheses, and cannot be assigned
    [`variants_basics` / `variant_wrong_check`, `variant_unknown_field`,
    `variant_check_on_integer`, `variant_check_with_parentheses`,
    `variant_check_assigned`].
41. `з або x` with a `може` or `вийде` on the left gives the value of `шось`
    or `вийшло`, and x must have exactly that type; x runs only when the left
    side holds `нема` or `облом`. With a `базар` on the left, `або` is logical
    OR; any other left side is an error [`variants_fallback_is_lazy` /
    `variant_fallback_wrong_type`, `variant_fallback_result_wrong_type`,
    `variant_fallback_on_integer`].
42. `може` and `вийде` are values: copies share no memory (rule 18). `рівно`
    and `не рівно` need equal types whose parts compare (rule 9); arithmetic,
    conditions, and `всьо розходимось` take neither [`variants_are_values` /
    `variant_compare_structures`, `variant_compare_different_types`,
    `variant_arithmetic`, `variant_condition`, `variant_exit_value`].

**розбери**

43. The value of `розбери` may have any type and is evaluated once. Each arm
    is a child scope that holds the names its pattern binds and the outer
    block of its body, so the body cannot redeclare them; they are immutable
    and invisible after the arm. A guard is a `базар`, sees those names, and
    runs only when the pattern matches. An arm body is nonempty, and a
    `розбери` has at least one arm [`match_values` / `match_binding_is_immutable`,
    `match_binding_invisible_after`, `match_body_redeclares_binding`,
    `match_guard_not_bool`, `match_guard_without_really`, `match_empty_arm`,
    `match_no_arms`, `match_unclosed`, `match_arm_outside`,
    `match_closer_outside`, `match_pattern_expression`].
44. The arms without a guard cover every value: integers only with `_` or a
    name, `базар` with `реально` and `гон`, `може` with `шось` and `нема`,
    `вийде` with `вийшло` and `облом`, and inside them every value of what they
    hold. The error names a value no arm covers [`match_basics` /
    `match_missing_none`, `match_missing_nested`,
    `match_integers_need_wildcard`, `match_guard_does_not_count`,
    `match_missing_structure_field_value`].
45. Every arm, and every alternative of an `або` pattern, matches some value
    that no arm without a guard above it matches. A name is not a constant:
    `випадок МАКС` binds every value, so the arms below it never run
    [`match_unreachable_after_wildcard`, `match_unreachable_binding_catches_all`,
    `match_unreachable_alternative`, `match_unreachable_nested`].
46. Patterns fit the type of the value: a literal of its type and range,
    `шось` and `нема` for `може`, `вийшло` and `облом` for `вийде`, and a
    structure pattern for that structure with one pattern per field. A name
    is bound at most once per pattern, and not inside alternatives. A
    `розбери` whose arms all end with `тримай` counts as ending with it
    (rule 13) [`match_values` / `match_variant_wrong_type`,
    `match_literal_wrong_type`, `match_literal_too_big`,
    `match_structure_wrong_field_count`, `match_structure_unknown`,
    `match_structure_wrong_type`, `match_binding_in_alternatives`,
    `match_binding_twice`, `match_function_missing_return`].

**?**

47. `з?` needs a `може` or a `вийде` and is what `шось` or `вийшло` holds. In a
    function, `?` on a `може` needs the function to return a `може`, and `?` on
    `вийде T або облом E` needs it to return a `вийде` whose error type is
    exactly E; `нема` or `облом` returns from the function at once, skipping
    the rest of the expression. In the main program they stop it with a
    run-time error and exit code 1. `?` is not allowed in a constant, and a
    function that contains `?` is never inlined [`try_basics`,
    `try_in_main_stops`, `try_not_inlined` / `try_on_integer`,
    `try_on_none_without_type`, `try_option_in_integer_function`,
    `try_option_in_result_function`, `try_result_in_option_function`,
    `try_result_error_types_differ`, `try_in_method_with_integer_result`,
    `try_payload_wrong_type`, `try_alone_is_not_a_statement`,
    `try_in_constant`, `try_in_assignment_place`].

**String interpolation**

48. A `{…}` part of a string holds exactly one expression, of any type, on
    the same line; it sees the names the statement sees. The parts run from
    left to right, each just before its value is printed as rule 23
    describes. A quote, a `{`, or a line end before the closing `}`, empty
    braces, and a `}` without `{` are lexical errors; `\{` and `\}` print
    braces [`interpolation_basics`, `interpolation_order` /
    `interpolation_unclosed_brace`, `interpolation_lone_closing_brace`,
    `interpolation_empty_braces`, `interpolation_nested_braces`,
    `interpolation_unknown_character`, `interpolation_two_expressions`,
    `interpolation_missing_operand`, `interpolation_unknown_name`,
    `interpolation_none_without_type`, `interpolation_string_outside_print`].

## Code generation

[codegen.py](codegen.py) builds the module with `llvmlite.ir`; the only IR
text the compiler writes is `str(module)`.

- **Structures**: an identified struct type `bz.Точка` per structure. An
  object is an alloca of it; a field is reached with a `gep` by the field's
  index from the symbol table.
- **Arrays, objects, `може`, and `вийде`** stay in memory and are copied with
  `llvm.memcpy`; see [Arrays and objects in the IR](#arrays-and-objects-in-the-ir).
  `може T` is the literal struct `{i1, T}` and `вийде T або облом E` is
  `{i1, T, E}`; `з або x` is a branch on the tag and a `phi`.
- **?** is a branch on the tag that returns `нема` or `облом` through the
  caller's result pointer, or stops the main program.
- **розбери** tries its arms in order with a chain of comparisons; see
  [Extra feature: розбери](#extra-feature-розбери).
- **Functions**: `bz.NAME` per function and `bz.Точка.NAME` per member
  function, whose first parameter is a pointer to the object. Every function
  is declared before any body, so forward calls resolve. The `bz.` prefix
  keeps a function named `main` or `printf` apart from the C runtime.
- **Runtime**: `printf`, `scanf`, `write`, and `exit` are declared without
  bodies and linked by `clang`. Format strings are private global constants.
  Printing an object walks the field table with one `gep`, `load`, and
  `printf` per field, so a new structure prints without new compiler code.
  A run-time error calls `fflush(NULL)` before it writes to stderr, so what
  the program printed before it appears first.
- **Variables** are allocas in the function's entry block, so a loop body that
  declares a variable does not grow the stack. A value of 1 KiB or more is
  allocated there with `malloc` instead and freed before every `ret`.
  Arithmetic uses the `llvm.s*.with.overflow` intrinsics.
- **Loops** are basic blocks with a back edge; see [Loops in the IR](#loops-in-the-ir).

## Optimizer

`--optimize`, anywhere on the command line, runs [optimizer.py](optimizer.py) on
the checked tree before code generation. Together with `--ast` it prints the
tree after the optimizer. A program prints the same with and without the flag,
run-time errors included, because moved nodes keep their line and column. The
three transformations repeat until a whole round changes nothing, since each
can give work to the others.

```sh
.venv/bin/python compiler.py --optimize programs/bank.txt bank.ll
.venv/bin/python compiler.py --optimize --ast tests/optimize/inline_simple.bazar
```

**Unused variables.** A declaration nobody reads is removed with its
assignments, so its `alloca` disappears from the IR, and this repeats because a
removal can leave another variable unread. Names are compared by the symbol the
semantic pass resolved, not by spelling, so a shadowing variable and the one it
hides are never confused. An assignment through `п.х` writes `п`, it does not
read it. Writing `х` from its own old value counts as reading it. Parameters,
loop counters, and constants are not removed. A variable stays when any value
it receives cannot be dropped: a call or `ану кажи` is never dropped, and
neither is arithmetic that could stop the program with an overflow or a division
by zero, since that error is output too. Arithmetic on values known at compile
time is checked and can be dropped, so `2 плюс 3 на 4` goes.

**Unused functions.** A function or member function that cannot be reached from
the main program is removed with its whole body. Following calls from the main
program means a chain of functions goes at once, and so do functions that only
call each other.

**Inlining.** A top-level function called exactly once is replaced by its body
in front of the statement that calls it. Each parameter becomes a local
declaration initialised with the argument, its `тримай` becomes a local whose
value stands where the call stood, and its locals are renamed `NAME.FUNCTION.N`.
A `.` cannot occur in a source name, so these cannot collide with the caller's.
The function is then removed as unused.

| Left alone | Why |
| --- | --- |
| a recursive function, directly or through others | its body would contain its own call |
| a member function | its body uses the fields of its object |
| a `тримай` anywhere but the last line, such as inside `якшо` or a loop | it would need a jump out of the middle of the caller |
| a `?` anywhere in the body | it returns from the function, and in the caller it would return from the caller |
| a call in the condition of `крутимось поки` | the condition runs on every pass, the moved body only once |
| a call on the right of `і ше` or `або` | it may never run |
| a call in any `{…}` part of a string but the first | the parts before it are printed before it runs |
| a call after something that is not a plain value, as in `ф() плюс г()` for `г` | the moved body would run first and change the order of effects |

For this program, `другий` is called once, its parameter `перший` is never read,
and nobody reads `зайва`:

```text
маю дєло другий(перший тіпа дрібняк, другий тіпа дрібняк) на виході дрібняк
    тримай другий
порішали
зуб даю зайва тіпа дрібняк це 5
базарь другий(1, 2)
```

Before, without the flag:

```llvm
define i32 @"bz.другий"(i32 %"перший", i32 %"другий")
{
entry:
  %"перший.1" = alloca i32
  %"другий.1" = alloca i32
  br label %"body"
body:
  store i32 %"перший", i32* %"перший.1"
  store i32 %"другий", i32* %"другий.1"
  %"другий.2" = load i32, i32* %"другий.1"
  ret i32 %"другий.2"
}
define i32 @"main"()
{
entry:
  %"зайва" = alloca i32
  br label %"body"
body:
  store i32 5, i32* %"зайва"
  %".3" = call i32 @"bz.другий"(i32 1, i32 2)
  %".4" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([4 x i8], [4 x i8]* @"str.0", i32 0, i32 0), i32 %".3")
  ret i32 0
}
```

After, with `--optimize`: the function, the call, and both unused slots are gone.

```llvm
define i32 @"main"()
{
entry:
  %"другий.другий.1" = alloca i32
  %"результат.другий.1" = alloca i32
  br label %"body"
body:
  store i32 2, i32* %"другий.другий.1"
  %"другий.другий.1.1" = load i32, i32* %"другий.другий.1"
  store i32 %"другий.другий.1.1", i32* %"результат.другий.1"
  %"результат.другий.1.1" = load i32, i32* %"результат.другий.1"
  %".4" = call i32 (i8*, ...) @"printf"(i8* getelementptr ([4 x i8], [4 x i8]* @"str.0", i32 0, i32 0), i32 %"результат.другий.1.1")
  ret i32 0
}
```

## The real program: Bazar Bank

[programs/bank.txt](programs/bank.txt) is a small bank account you use from the
keyboard. It asks for an account number, then shows a menu: deposit, withdraw,
show the account, forecast compound interest, or leave. It uses the structures
`Рахунок` and `Прогноз`, member functions that change the balance, and the
functions `запитай` and `покажи_меню`.

Loops carry the whole program: the menu is a `крутимось поки реально` left with
`харе`, `запитай` repeats its question in a `крутимось поки реально` until the
answer fits, and the forecast is a range loop over the months. Amounts have
limits, so the forecast cannot overflow. Typing 0 cancels any question. The end
of input reads as 0, and so does text that is not a number, so neither can hang
the program. It prints each prompt on its own line.

Build it into a native binary and replay each recorded session:

```sh
.venv/bin/python compiler.py programs/bank.txt bank.ll
llc -relocation-model=pic -filetype=obj bank.ll -o bank.o
clang bank.o -o bank
./bank < programs/bank.in      # deposit, withdraw, show, forecast, leave
./bank < programs/bank_2.in    # rejected, cancelled, and overdrawn answers
./bank < programs/bank_3.in    # the input ends without choosing to leave
./bank                         # or use it yourself
```

Each session's exact output is in `programs/NAME.expected`, and `check.py`
builds the binary and compares it.

## The second program: Bazar Stall

[programs/stall.txt](programs/stall.txt) is a market stall that uses every
extra feature in one compiled program. It shows four goods with their codes,
prices, and stock, reads a code and a quantity until you type 0, then prints a
receipt with a discount.
[programs/stall.bazar](programs/stall.bazar) is the same program with the
`.bazar` extension, so the [VS Code extension](#vs-code-extension) highlights
and checks it.

| Feature | Where the stall uses it |
| --- | --- |
| arrays | the codes, prices, and stock are `[крупняк; ТОВАРІВ]` fields of `Лоток`, and the cart is `[всюди 0]` summed with `крутимось штук тіпа крупняк з кошик` |
| `може` | `знайди` looks a code up in the array and returns `шось(к)` or `нема`; `знижка` returns `шось(10)`, `шось(5)`, or `нема`, read with `або 0` |
| `вийде` | `продай` returns `вийшло(Покупка(…))` or `облом(1)`, `облом(2)`, or `облом(3)` for an unknown code, a bad quantity, or too little stock |
| `розбери` | the main loop matches `вийшло(Покупка(товар, штук, сума))` and answers each `облом` in surzhyk, with guards (`якшо реально`) that tell zero from too many and sold out from too few, `номер_товару` turns a `може` into a `вийде`, and `рядок_чека` matches the item number to print its name |
| `?` | `продай` starts with `номер_товару(код)?` and `перевірені_штуки(скільки)?`, so the first step that fails returns its `облом` |
| `{…}` | the display, every answer, and the receipt, including whole arrays such as `{лоток.залишок}` |

The end of input reads as 0 and goes to the till, so no session can hang the
program. Build it and replay each recorded session:

```sh
.venv/bin/python compiler.py programs/stall.txt stall.ll
llc -relocation-model=pic -filetype=obj stall.ll -o stall.o
clang stall.o -o stall
./stall < programs/stall.in      # three purchases and a 10% discount
./stall < programs/stall_2.in    # unknown code, zero, negative, and too many, too little stock, sold out
./stall < programs/stall_3.in    # leave with an empty cart
./stall < programs/stall_4.in    # a 5% discount, and the input ends without 0
./stall                          # or use it yourself
```

`check.py` replays these sessions like the bank's, with and without
`--optimize`.

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
`bool`, a structure name, an array type with its size as written in the
source, such as `[[i32; 3]; Н плюс 1]`, `Option<i32>`, or `Result<i32, i64>`.
A `VariantNode` prints `variant=some`, `none`, `ok`, or `err`. The fallback
`з або x` prints as `operator=or`, like logical OR; the semantic pass tells
them apart by the type on the left. A `MatchNode` prints its `subject` and
`arms`; each `MatchArmNode` its `pattern`, `guard` (`guard: None` without
one), and `body`.

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
| `tests/valid` | 56 | `--ast` output equals `NAME.ast` (front-end tests; some Stage 1 ones use undeclared names on purpose); with `--optimize`, it equals `NAME.optimized.ast` when the optimizer changes the tree, or `NAME.optimized.err` for the 16 that stop in the semantic pass |
| `tests/invalid` | 349 | compiling exits 1, prints exactly `NAME.err`, and writes no file |
| `tests/run` | 45 | end to end: compiled, run with `lli` (or built with `llc` and `clang`), stdout equals `NAME.expected`; `NAME.in` is stdin; `NAME.error` is the expected run-time error |
| `examples` | 15 | compiling succeeds |
| `programs` | 3 sessions | built with `llc` and `clang`; the native binary's stdout equals the session's `.expected` |
| `tests/optimize` | 14 | `--optimize --ast` output equals `NAME.ast`, and stdout equals `NAME.expected` with and without the flag; `NAME.in` and `NAME.error` as in `tests/run` |

The `tests/valid`, `tests/invalid`, `tests/run`, `examples`, and `programs` checks each run twice, without the flag and with `--optimize`. In `tests/valid`, 29 trees are unchanged by the optimizer and still equal `NAME.ast`; 11 change (unused declarations and functions removed, `покажи` inlined), and their trees are in `NAME.optimized.ast`; 16 deliberately use undeclared names, so they stop in the semantic pass before the optimizer and print the same error as without the flag, pinned in `NAME.optimized.err`.

LLVM tools are looked up in `$LLVM_BIN`, then on `PATH`, then in the
Homebrew folders. The 137 unit tests cover the lexer, the parser, the type
values, the exhaustiveness algorithm, where generated code keeps its slots, the semantic pass's symbol table and annotations, and the CLI.

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
bazar_types.py the resolved types: integers, базар, structures, arrays, може, вийде
semantic.py    semantic pass and symbol table
exhaustiveness.py  the usefulness algorithm behind розбери
optimizer.py   the transformations behind --optimize
codegen.py     LLVM IR through the llvmlite builder
compiler.py    command-line interface
check.py       test runner: AST, errors, and end-to-end runs
examples/      sample programs
tests/         fixtures, expected results, and unit tests
programs/      the real program and its recorded sessions
```
