"""Type value unit tests: equality, hashing, and the two spellings of a type."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bazar_types import (  # noqa: E402
    BOOL, BUILTIN_TYPES, I32, I64, STRING, ArrayType, BoolType, IntType, OptionType, ResultType, StructType,
    contained_structs, is_aggregate, is_comparable, is_integer, is_scalar, is_variant, payloads,
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
        self.assertEqual(contained_structs(ArrayType(ArrayType(StructType("Точка"), 2), 3)), ["Точка"])


class ArrayTypeTest(unittest.TestCase):
    def test_equal_by_element_and_length(self):
        self.assertEqual(ArrayType(I32, 3), ArrayType(IntType(32), 3))
        self.assertNotEqual(ArrayType(I32, 3), ArrayType(I32, 4))
        self.assertNotEqual(ArrayType(I32, 3), ArrayType(I64, 3))
        self.assertEqual({ArrayType(I32, 3): 1}[ArrayType(I32, 3)], 1)

    def test_spellings(self):
        grid = ArrayType(ArrayType(BOOL, 2), 3)
        self.assertEqual((str(grid), grid.word), ("[[bool; 2]; 3]", "[[базар; 2]; 3]"))

    def test_predicates(self):
        point = StructType("Точка")
        self.assertTrue(is_aggregate(ArrayType(I32, 1)))
        self.assertTrue(is_aggregate(point))
        self.assertFalse(is_aggregate(I32))
        self.assertTrue(is_comparable(ArrayType(ArrayType(BOOL, 2), 2)))
        self.assertFalse(is_comparable(ArrayType(point, 2)))
        self.assertFalse(is_scalar(ArrayType(I32, 1)))



class VariantTypeTest(unittest.TestCase):
    def test_equal_by_structure(self):
        self.assertEqual(OptionType(I32), OptionType(IntType(32)))
        self.assertNotEqual(OptionType(I32), OptionType(I64))
        self.assertEqual(ResultType(I32, I64), ResultType(I32, I64))
        self.assertNotEqual(ResultType(I32, I64), ResultType(I64, I32))

    def test_spellings(self):
        nested = ResultType(OptionType(ArrayType(I32, 2)), I64)
        self.assertEqual(str(nested), "Result<Option<[i32; 2]>, i64>")
        self.assertEqual(nested.word, "вийде може [дрібняк; 2] або облом крупняк")

    def test_predicates_and_payloads(self):
        point = StructType("Точка")
        self.assertTrue(is_variant(OptionType(I32)) and is_aggregate(ResultType(I32, BOOL)))
        self.assertFalse(is_variant(ArrayType(I32, 1)))
        self.assertEqual(payloads(OptionType(I32)), [I32])
        self.assertEqual(payloads(ResultType(I32, BOOL)), [I32, BOOL])
        self.assertTrue(is_comparable(ResultType(OptionType(BOOL), ArrayType(I64, 2))))
        self.assertFalse(is_comparable(OptionType(point)))
        self.assertEqual(contained_structs(ResultType(point, OptionType(StructType("Коло")))), ["Точка", "Коло"])


if __name__ == "__main__":
    unittest.main()
