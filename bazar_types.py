"""Bazar types: the resolved types of the semantic pass and code generation.

A type is an immutable value with no source position. Two types are equal
when they have the same structure, wherever they were written, and they can
be dictionary keys:

* IntType(32) and IntType(64): дрібняк and крупняк;
* BoolType(): базар;
* StructType(name): an object of a такі діла structure;
* StringType(): a string literal, the operand of базарь; it cannot be written
  as a type.

str(type) is the spelling of the AST dump (i32, i64, bool, or the structure
name), and type.word is the spelling of error messages (дрібняк, крупняк,
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
    """A type whose values live in memory and are copied as a block: a structure."""
    return isinstance(t, StructType)


def is_comparable(t):
    """A type whose values рівно and не рівно compare."""
    return is_scalar(t)


def contained_structs(t):
    """The names of the structures that a value of type t holds directly, by value."""
    if isinstance(t, StructType):
        return [t.name]
    return []
