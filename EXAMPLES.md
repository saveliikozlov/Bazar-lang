# Bazar examples

Each program below is a file in [examples/](examples), parsed with
`python3 compiler.py --ast examples/NAME.bazar`. `python3 check.py` checks them
all. Larger valid and invalid suites, with expected ASTs or error lines, are
in [tests/valid](tests/valid) and [tests/invalid](tests/invalid).

## Valid programs

### Types, mutability, output, and exit — [examples/budget.bazar](examples/budget.bazar)

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

All money variables have type `крупняк`: there is no implicit narrowing from `i64` to `i32`.

### Constants, immutable and mutable variables — [examples/constants.bazar](examples/constants.bazar)

```text
чутки: constants are set in reinforced concrete before the program runs

желєзобетонно ТИЖДЕНЬ тіпа дрібняк це 7
желєзобетонно ДОБА_ГОДИН тіпа дрібняк це 24
желєзобетонно ТИЖДЕНЬ_ГОДИН тіпа дрібняк це ТИЖДЕНЬ на ДОБА_ГОДИН

зуб даю відпрацьовано тіпа дрібняк це 50
мутна тєма переробка тіпа дрібняк це 0

якшо реально відпрацьовано більше ТИЖДЕНЬ_ГОДИН ділити на 4
    перевзувся переробка тепер відпрацьовано мінус ТИЖДЕНЬ_ГОДИН ділити на 4
отакої

базарь переробка
```

`ТИЖДЕНЬ_ГОДИН` is computed from two earlier constants before the program runs.
`відпрацьовано` is an immutable variable and `переробка` a mutable one.
Constants are declared only at the top level, outside `якшо реально`.

### Other types and logic — [examples/types_and_logic.bazar](examples/types_and_logic.bazar)

```text
зуб даю дрібні тіпа дрібняк це 5
зуб даю норм тіпа базар це дрібні не рівно 0 і ше реально

якшо реально норм
    базарь дрібні
а нє
    базарь 0
отакої
```

### Parentheses, precedence, unary minus, and division — [examples/arithmetic.bazar](examples/arithmetic.bazar)

```text
чутки: parentheses, precedence, unary minus, and division
зуб даю x тіпа дрібняк це (2 плюс 3) на 4
зуб даю y тіпа дрібняк це мінус x ділити на 3
зуб даю z тіпа дрібняк це 2 плюс 3 на 4 мінус 1
зуб даю найменший тіпа крупняк це мінус 9223372036854775808
базарь x плюс y плюс z
```

`2 плюс 3 на 4 мінус 1` means `(2 + (3 * 4)) - 1`; `мінус x ділити на 3`
means `(-x) / 3`.

### Boolean literals, comparisons, and logic — [examples/logic.bazar](examples/logic.bazar)

```text
чутки: Boolean literals, comparisons, and logic
зуб даю a тіпа дрібняк це 10
зуб даю b тіпа дрібняк це 20
зуб даю ок тіпа базар це a не рівно b і ше реально
зуб даю збіглись тіпа базар це a рівно b або гон
зуб даю більше_чи_ні тіпа базар це (a більше b) рівно (b менше a)
базарь ок або збіглись і ше більше_чи_ні
```

The last line means `ок or (збіглись and більше_чи_ні)`: `і ше` binds more
tightly than `або`.

### Nested conditions and optional else — [examples/nested_if.bazar](examples/nested_if.bazar), [examples/nested_blocks.bazar](examples/nested_blocks.bazar)

```text
чутки: nested conditions and optional else; each якшо has its own отакої
мутна тєма x тіпа дрібняк це 10
якшо реально x більше 0
    якшо реально x не рівно 1
        перевзувся x тепер x мінус 1
    а нє
        перевзувся x тепер 0
    отакої
отакої
якшо реально реально
    чутки: always-true condition
    базарь x
отакої
всьо розходимось x
```

The inner `отакої` closes the inner condition together with its else branch;
the outer closer ends the outer condition.

### Comments and names — [examples/comments_and_names.bazar](examples/comments_and_names.bazar)

```text
чутки: comments accept Unicode 😎, including ґанок and їжак
зуб даю answer_42 тіпа крупняк це 42 чутки: this is not a string literal
зуб даю дрібняк_2 тіпа дрібняк це 2
зуб даю Їжак тіпа базар це гон
зуб даю ґанок_Є тіпа дрібняк це 7
зуб даю мелочь тіпа дрібняк це 1 чутки: the former keyword is now just a name
базарь answer_42
```

`дрібняк_2` is a name: the whole word is read before checking whether it is
reserved. `мелочь` is a word from the former vocabulary, now an ordinary name.

## Invalid programs (lexical or syntax errors)

| Program | Error |
| --- | --- |
| `зуб даю x це 1` | `line 1:17: Де «тіпа», шеф? Після «x» треба вказати тип, а тут «це».` |
| `якшо реально реально` / `отакої` | `line 2:1: Блок «якшо реально» пустий. Хотів шось зробить чи просто зайшов?` |
| `зуб даю x тіпа дрібняк це 10 ділити 2` | `line 1:62: «Ділити» на шо? Після нього треба слово «на», а тут число 2.` |
| `зуб даю ок тіпа базар це 1 менше 2 менше 3` | `line 1:60: Порівняння в ланцюжок не ліпи: з'єднай їх через «і ше» / «або» або візьми дужки.` |
| `зуб даю x тіпа дрібняк це 12abc` | `line 1:46: Число з буквами? Не мути: після цифр букви й '_' не ліплять.` |
| `базарь 1 плюс` + newline + `2` | `line 1:24: Де значення? Тут має бути число, «реально», «гон», ім'я або «(», а не кінець рядка.` |
| `желєзобетонно X тіпа дрібняк це 1` on the second line inside a condition | `line 2:5: Константа «желєзобетонно» оголошується тільки на верхньому рівні програми, а не всередині «якшо реально».` |
| `зуб даю x тіпа дрібняк це 1 + 2` | `line 1:48: Шо за символ '+'? Такого в нашому базарі нема.` |
| `а нє базарь 2` on the third line inside a condition | `line 3:9: «А нє» займає цілий рядок: після «нє» чекаю кінець рядка, а тут «базарь».` |
| `зуб даю x тіпa дрібняк це 1` (Latin `a`) | `line 1:17: Де «тіпа», шеф? … ім'я «тіпa» (латинську літеру підсунули замість кириличної: треба «тіпа» суто кирилицею).` |

The same errors are covered by [tests/invalid](tests/invalid) fixtures with
exact expected error lines. The `syntax_legacy_ru_*` fixtures deliberately
contain the old Russian syntax to verify its rejection.

## Valid syntax with invalid semantics (currently accepted)

These programs match the grammar, so the parser accepts them and prints an
AST. Semantic analysis is intended to reject them.

```text
зуб даю x тіпа дрібняк це 1
перевзувся x тепер 2
```

Assignment to an immutable variable.

```text
зуб даю x тіпа дрібняк це 1
желєзобетонно Y тіпа дрібняк це x плюс 1
```

A constant initialized from a variable: its value is not known at compile time.

```text
желєзобетонно ЛІМІТ тіпа дрібняк це 10
перевзувся ЛІМІТ тепер 20
```

Assignment to a constant.

```text
зуб даю x тіпа дрібняк це 2147483648
```

The literal does not fit in `дрібняк` (i32): it is an overflow error under the intended semantic rules.

```text
якшо реально 123
    базарь невідомий
отакої
```

A non-Boolean condition and an undeclared name.

These are the `tests/valid/deferred_semantics_*.bazar` fixtures.
