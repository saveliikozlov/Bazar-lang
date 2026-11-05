"""Bazar types: the resolved types of the semantic pass and code generation.

A type is an immutable value with no source position. Two types are equal
when they have the same structure, wherever they were written, and they can
be dictionary keys:

* IntType(32) and IntType(64): дрібняк and крупняк;
* BoolType(): базар;
* StructType(name): an object of a такі діла structure;
* ArrayType(element, length): a fixed-size array, [дрібняк; 5];
* OptionType(inner): може дрібняк, a value шось(x) or нема;
* ResultType(ok, error): вийде дрібняк або облом крупняк, a value вийшло(x)
  or облом(e);
* StringType(): a string literal, the operand of базарь; it cannot be written
  as a type.

str(type) is the spelling of the AST dump (i32, i64, bool, the structure
name, [i32; 5], Option<i32>, Result<i32, i64>), and type.word is the spelling of error messages (дрібняк, крупняк,
базар, or the structure name).

Every compound type that is added later needs its own class here, a case in
contained_structs(), and its cases in the semantic pass and the code generator.
The module does not import llvmlite, because the VS Code extension uses the
semantic pass without it.
"""

from __future__ import annotations

from dataclasses import dataclass


class Type:
    """Base class for all resolved types."""

    @property
    def word(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class IntType(Type):
    bits: int

    def __str__(self):
        return f"i{self.bits}"

    @property
    def word(self):
        return INT_WORDS[self.bits]

    @property
    def range(self):
        """The smallest and the largest value, both included."""
        return -2 ** (self.bits - 1), 2 ** (self.bits - 1) - 1


@dataclass(frozen=True)
class BoolType(Type):
    def __str__(self):
        return "bool"

    @property
    def word(self):
        return "базар"


@dataclass(frozen=True)
class StructType(Type):
    name: str

    def __str__(self):
        return self.name

    @property
    def word(self):
        return self.name


@dataclass(frozen=True)
class ArrayType(Type):
    element: Type
    length: int

    def __str__(self):
        return f"[{self.element}; {self.length}]"

    @property
    def word(self):
        return f"[{self.element.word}; {self.length}]"


@dataclass(frozen=True)
class OptionType(Type):
    inner: Type

    def __str__(self):
        return f"Option<{self.inner}>"

    @property
    def word(self):
        return f"може {self.inner.word}"


@dataclass(frozen=True)
class ResultType(Type):
    ok: Type
    error: Type

    def __str__(self):
        return f"Result<{self.ok}, {self.error}>"

    @property
    def word(self):
        return f"вийде {self.ok.word} або облом {self.error.word}"


@dataclass(frozen=True)
class StringType(Type):
    def __str__(self):
        return "string"

    @property
    def word(self):
        return "рядок"


INT_WORDS = {32: "дрібняк", 64: "крупняк"}

I32, I64 = IntType(32), IntType(64)
BOOL = BoolType()
STRING = StringType()

# The canonical names that the parser and the AST dump use for the built-in types.
BUILTIN_TYPES = {"i32": I32, "i64": I64, "bool": BOOL}


def is_integer(t):
    """дрібняк or крупняк; False for None, the absence of an expected type."""
    return isinstance(t, IntType)


def is_scalar(t):
    """A built-in type: дрібняк, крупняк, or базар."""
    return isinstance(t, (IntType, BoolType))


def is_aggregate(t):
    """A type whose values live in memory and are copied as a block: all but the scalars."""
    return isinstance(t, (StructType, ArrayType, OptionType, ResultType))


def is_variant(t):
    """може or вийде: a tag and the value it holds."""
    return isinstance(t, (OptionType, ResultType))


def payloads(t):
    """The types a може or вийде value may hold, in their order in memory after the tag."""
    if isinstance(t, OptionType):
        return [t.inner]
    return [t.ok, t.error]


def is_comparable(t):
    """A type whose values рівно and не рівно compare: a scalar or an array of comparable elements."""
    if isinstance(t, ArrayType):
        return is_comparable(t.element)
    if is_variant(t):
        return all(is_comparable(inner) for inner in payloads(t))
    return is_scalar(t)


def contained_structs(t):
    """The names of the structures that a value of type t holds directly, by value."""
    if isinstance(t, StructType):
        return [t.name]
    if isinstance(t, ArrayType):
        return contained_structs(t.element)
    if is_variant(t):
        return [name for inner in payloads(t) for name in contained_structs(inner)]
    return []
