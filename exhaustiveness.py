"""Exhaustiveness and reachability of розбери: the usefulness algorithm.

    useful(rows, vector, types, structures) -> witness or None

Patterns are reduced to three shapes:
* Wild(): _ or a name, which match anything;
* Con(key, args): a constructor with its argument patterns. The keys are
  ("some",), ("none",), ("ok",), ("err",), ("bool", True or False),
  ("int", value), and ("struct", name);
* Alt(options): an or-pattern.

A vector of patterns is useful against rows when some value matches the
vector but no row. The function returns a witness, a vector of patterns
describing such values, or None when there is none. An arm is unreachable
when its pattern is not useful against the arms above it, and a match is
exhaustive when _ is not useful against all of its arms. This is the
algorithm U of Luc Maranget, "Warnings for pattern matching" (2007), with
witnesses.

The constructors of a type form its signature: базар has реально and гон,
може has шось and нема, вийде has вийшло and облом, and a structure has one
constructor whose arguments are its fields. Integers and arrays have no
complete signature, so only _ or a name covers all of them.
"""

from __future__ import annotations

from dataclasses import dataclass

from bazar_types import BoolType, OptionType, ResultType, StructType


@dataclass(frozen=True)
class Wild:
    pass


@dataclass(frozen=True)
class Con:
    key: tuple
    args: tuple = ()


@dataclass(frozen=True)
class Alt:
    options: tuple


def signature(t, structures):
    """[(key, argument types)] for every constructor of t, or None if they cannot all be listed."""
    if isinstance(t, BoolType):
        return [(("bool", True), []), (("bool", False), [])]
    if isinstance(t, OptionType):
        return [(("some",), [t.inner]), (("none",), [])]
    if isinstance(t, ResultType):
        return [(("ok",), [t.ok]), (("err",), [t.error])]
    if isinstance(t, StructType):
        return [(("struct", t.name), [field.type for field in structures[t.name].fields.values()])]
    return None


def argument_types(key, t, structures):
    if key[0] == "int":
        return []
    return next(types for candidate, types in signature(t, structures) if candidate == key)


def expand(rows):
    """Rows whose first pattern is an or-pattern become one row per alternative."""
    result = []
    for row in rows:
        if row and isinstance(row[0], Alt):
            result.extend(expand([(option,) + row[1:] for option in row[0].options]))
        else:
            result.append(row)
    return result


def specialize(rows, key, arity):
    """The rows that can match constructor key, with its arguments in front."""
    result = []
    for row in rows:
        head = row[0]
        if isinstance(head, Wild):
            result.append((Wild(),) * arity + row[1:])
        elif head.key == key:
            result.append(head.args + row[1:])
    return result


def default(rows):
    """The rows whose first pattern matches anything, without it."""
    return [row[1:] for row in rows if isinstance(row[0], Wild)]


def useful(rows, vector, types, structures):
    if not vector:
        return None if rows else []
    head, rest = vector[0], vector[1:]
    if isinstance(head, Alt):
        for option in head.options:
            witness = useful(rows, (option,) + rest, types, structures)
            if witness is not None:
                return witness
        return None
    rows = expand(rows)
    t = types[0]
    if isinstance(head, Con):
        arguments = argument_types(head.key, t, structures)
        return _rebuild(head.key, len(arguments),
                        useful(specialize(rows, head.key, len(arguments)), head.args + rest,
                               arguments + types[1:], structures))
    used = []
    for row in rows:
        if isinstance(row[0], Con) and row[0].key not in used:
            used.append(row[0].key)
    constructors = signature(t, structures)
    if constructors is not None and all(key in used for key, _ in constructors):
        # Every constructor appears: some value is missed only inside one of them.
        for key, arguments in constructors:
            witness = _rebuild(key, len(arguments),
                               useful(specialize(rows, key, len(arguments)), (Wild(),) * len(arguments) + rest,
                                      arguments + types[1:], structures))
            if witness is not None:
                return witness
        return None
    witness = useful(default(rows), rest, types[1:], structures)
    if witness is None:
        return None
    if not used:
        return [Wild()] + witness
    if constructors is not None:
        key, arguments = next((key, arguments) for key, arguments in constructors if key not in used)
        return [Con(key, (Wild(),) * len(arguments))] + witness
    # An integer: the smallest non-negative value that no row names.
    values = {key[1] for key in used}
    value = 0
    while value in values:
        value += 1
    return [Con(("int", value))] + witness


def _rebuild(key, arity, witness):
    if witness is None:
        return None
    return [Con(key, tuple(witness[:arity]))] + witness[arity:]


WORDS = {"some": "шось", "none": "нема", "ok": "вийшло", "err": "облом"}


def show(pattern):
    """A pattern as the programmer writes it: шось(облом(_)), Точка(_, гон), мінус 3."""
    if isinstance(pattern, Wild):
        return "_"
    if isinstance(pattern, Alt):
        return " або ".join(show(option) for option in pattern.options)
    kind = pattern.key[0]
    if kind == "bool":
        return "реально" if pattern.key[1] else "гон"
    if kind == "int":
        value = pattern.key[1]
        return f"мінус {-value}" if value < 0 else str(value)
    arguments = ", ".join(show(argument) for argument in pattern.args)
    if kind == "struct":
        return f"{pattern.key[1]}({arguments})"
    return WORDS[kind] if kind == "none" else f"{WORDS[kind]}({arguments})"
