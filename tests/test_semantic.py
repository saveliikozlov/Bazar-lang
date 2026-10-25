"""Semantic pass unit tests: the symbol table and the annotations code generation reads."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parser import CompilationError, parse_program  # noqa: E402
from semantic import FieldInfo, analyze  # noqa: E402

POINT = """такі діла Точка
    мутна тєма х тіпа дрібняк
    зуб даю у тіпа крупняк
    маю дєло посунь(дх тіпа дрібняк) на виході дрібняк
        перевзувся х тепер х плюс дх
        тримай х
    порішали
    маю дєло двічі() на виході дрібняк
        посунь(1)
        тримай посунь(1)
    порішали
    маю дєло читай() на виході дрібняк
        тримай х
    порішали
порішали
"""


def check(source):
    program = parse_program(source.encode())
    return program, analyze(program)


class SymbolTableTest(unittest.TestCase):
    def test_structure_fields_in_order_with_index_type_and_mutability(self):
        _, info = check(POINT)
        fields = info.structures["Точка"].fields
        self.assertEqual([(f.name, f.index, f.type, f.mutable) for f in fields.values()],
                         [("х", 0, "i32", True), ("у", 1, "i64", False)])

    def test_mutating_flags_follow_calls_on_the_own_object(self):
        _, info = check(POINT)
        methods = info.structures["Точка"].methods
        self.assertTrue(methods["посунь"].mutating)
        self.assertTrue(methods["двічі"].mutating)        # only through посунь
        self.assertFalse(methods["читай"].mutating)

    def test_function_signatures(self):
        _, info = check("маю дєло ф(а1 тіпа дрібняк, б1 тіпа базар) на виході крупняк\n"
                        "    тримай 1\nпорішали")
        function = info.functions["ф"]
        self.assertEqual([(p.name, p.type) for p in function.parameters], [("а1", "i32"), ("б1", "bool")])
        self.assertEqual(function.result, "i64")

    def test_constants_are_computed(self):
        _, info = check("желєзобетонно А тіпа дрібняк це 7 ділити на мінус 2\n"
                        "желєзобетонно Б тіпа базар це А менше 0")
        self.assertEqual((info.constants["А"].value, info.constants["Б"].value), (-3, True))


class AnnotationTest(unittest.TestCase):
    def test_literals_take_their_type_from_context(self):
        program, _ = check("зуб даю а1 тіпа дрібняк це 1 плюс 2\nбазарь 3 плюс 4\nбазарь а1 плюс 5")
        first, second, third = program.statements
        self.assertEqual(first.initializer.left.type, "i32")
        self.assertEqual(second.value.left.type, "i64")      # no context: крупняк
        self.assertEqual(third.value.right.type, "i32")      # from the other operand

    def test_lookup_order_inside_a_member_function(self):
        program, _ = check("желєзобетонно х тіпа крупняк це 9\n"
                           "такі діла Т\n    зуб даю х тіпа дрібняк\n"
                           "    маю дєло поле() на виході дрібняк\n        тримай х\n    порішали\n"
                           "    маю дєло параметр(х тіпа базар) на виході базар\n        тримай х\n    порішали\n"
                           "порішали\n"
                           "маю дєло зовні() на виході крупняк\n    тримай х\nпорішали")
        structure, function = program.statements[1], program.statements[2]
        field_use = structure.methods[0].body.statements[0].value
        parameter_use = structure.methods[1].body.statements[0].value
        constant_use = function.body.statements[0].value
        self.assertIsInstance(field_use.ref, FieldInfo)
        self.assertEqual(parameter_use.ref.kind, "param")
        self.assertEqual(constant_use.ref.kind, "const")

    def test_calls_and_fields_are_resolved(self):
        program, _ = check(POINT + "мутна тєма п тіпа Точка це склепай Точка(1, 2)\n"
                                   "базарь п.посунь(п.х)")
        call = program.statements[-1].value
        self.assertEqual(call.target.name, "посунь")
        self.assertEqual(call.arguments[0].field_info.index, 0)
        bare = program.statements[0].methods[1].body.statements[0].call
        self.assertTrue(bare.on_self)

    def test_first_error_is_reported_at_its_node(self):
        with self.assertRaises(CompilationError) as context:
            check("маю дєло ф(н тіпа дрібняк) на виході дрібняк\n    тримай н\nпорішали\n"
                  "базарь ф(1, 2)")
        self.assertEqual((context.exception.line, context.exception.column), (4, 14))


if __name__ == "__main__":
    unittest.main()
