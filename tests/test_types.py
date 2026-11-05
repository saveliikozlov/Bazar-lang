"""Type value unit tests: equality, hashing, and the two spellings of a type."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bazar_types import (  # noqa: E402
    BOOL, BUILTIN_TYPES, I32, I64, STRING, BoolType, IntType, StructType, contained_structs, is_comparable,
    is_integer, is_scalar,
)


class TypeValueTest(unittest.TestCase):
    def test_types_are_equal_by_structure(self):
        self.assertEqual(IntType(32), I32)
        self.assertEqual(BoolType(), BOOL)
        self.assertEqual(StructType("Точка"), StructType("Точка"))
        self.assertNotEqual(StructType("Точка"), StructType("Коло"))
        self.assertNotEqual(I32, I64)

    def test_types_are_never_equal_to_their_spelling(self):
        self.assertNotEqual(I32, "i32")
        self.assertNotEqual(StructType("Точка"), "Точка")

    def test_types_are_dictionary_keys(self):
        table = {I32: "a", StructType("Точка"): "b"}
        self.assertEqual(table[IntType(32)], "a")
        self.assertEqual(table[StructType("Точка")], "b")

    def test_dump_spelling(self):
        self.assertEqual([str(t) for t in (I32, I64, BOOL, StructType("Точка"), STRING)],
                         ["i32", "i64", "bool", "Точка", "string"])

    def test_message_spelling(self):
        self.assertEqual([t.word for t in (I32, I64, BOOL, StructType("Точка"))],
                         ["дрібняк", "крупняк", "базар", "Точка"])

    def test_integer_ranges(self):
        self.assertEqual(I32.range, (-2147483648, 2147483647))
        self.assertEqual(I64.range, (-9223372036854775808, 9223372036854775807))

    def test_builtin_names_are_the_dump_spelling(self):
        self.assertEqual({name: str(t) for name, t in BUILTIN_TYPES.items()},
                         {"i32": "i32", "i64": "i64", "bool": "bool"})


class TypePredicateTest(unittest.TestCase):
    def test_predicates(self):
        point = StructType("Точка")
        self.assertEqual([is_integer(t) for t in (I32, I64, BOOL, point, None)],
                         [True, True, False, False, False])
        self.assertEqual([is_scalar(t) for t in (I32, BOOL, point, STRING)], [True, True, False, False])
        self.assertEqual([is_comparable(t) for t in (I64, BOOL, point)], [True, True, False])

    def test_contained_structs(self):
        self.assertEqual(contained_structs(StructType("Точка")), ["Точка"])
        self.assertEqual(contained_structs(I32), [])


if __name__ == "__main__":
    unittest.main()
