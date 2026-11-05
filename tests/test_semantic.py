"""Semantic pass unit tests: the symbol table and the annotations code generation reads."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bazar_types import BOOL, I32, I64, ArrayType, OptionType, ResultType  # noqa: E402
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
                         [("х", 0, I32, True), ("у", 1, I64, False)])

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
        self.assertEqual([(p.name, p.type) for p in function.parameters], [("а1", I32), ("б1", BOOL)])
        self.assertEqual(function.result, I64)

    def test_constants_are_computed(self):
        _, info = check("желєзобетонно А тіпа дрібняк це 7 ділити на мінус 2\n"
                        "желєзобетонно Б тіпа базар це А менше 0")
        self.assertEqual((info.constants["А"].value, info.constants["Б"].value), (-3, True))


class AnnotationTest(unittest.TestCase):
    def test_literals_take_their_type_from_context(self):
        program, _ = check("зуб даю а1 тіпа дрібняк це 1 плюс 2\nбазарь 3 плюс 4\nбазарь а1 плюс 5")
        first, second, third = program.statements
        self.assertEqual(first.initializer.left.type, I32)
        self.assertEqual(second.value.left.type, I64)      # no context: крупняк
        self.assertEqual(third.value.right.type, I32)      # from the other operand

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



class ArrayAnnotationTest(unittest.TestCase):
    def test_array_types_use_constants_and_nest(self):
        program, info = check("желєзобетонно Н тіпа дрібняк це 2\n"
                              "маю дєло ф(м тіпа [[базар; Н]; Н плюс 1]) на виході [крупняк; 3]\n"
                              "    тримай [всюди 0]\nпорішали")
        function = info.functions["ф"]
        self.assertEqual(function.parameters[0].type, ArrayType(ArrayType(BOOL, 2), 3))
        self.assertEqual(function.result, ArrayType(I64, 3))
        self.assertEqual(str(function.result), "[i64; 3]")
        self.assertEqual(function.result.word, "[крупняк; 3]")

    def test_literals_take_the_element_type_from_context(self):
        program, _ = check("зуб даю м тіпа [дрібняк; 2] це [1, мінус 2]\nбазарь [5000000000, 1]")
        declaration, printed = program.statements
        self.assertEqual([item.type for item in declaration.initializer.elements], [I32, I32])
        self.assertEqual(printed.value.type, ArrayType(I64, 2))

    def test_index_and_length_annotations(self):
        program, _ = check("зуб даю м тіпа [дрібняк; 3] це [1, 2, 3]\nзуб даю к тіпа дрібняк це 1\n"
                           "базарь м[2]\nбазарь м[к]\nзуб даю д тіпа крупняк це м.розмір\nбазарь м.розмір")
        known, unknown, wide, plain = program.statements[2:]
        self.assertEqual((known.value.index_value, known.value.type), (2, I32))
        self.assertIsNone(unknown.value.index_value)
        self.assertEqual((wide.initializer.length, wide.initializer.type), (3, I64))   # typed by context
        self.assertEqual(plain.value.type, I32)                                      # дрібняк without one
        self.assertIsNone(plain.value.field_info)

    def test_for_each_counter_is_an_immutable_element(self):
        program, _ = check("зуб даю м тіпа [дрібняк; 2] це [1, 2]\nкрутимось е тіпа дрібняк з м\n"
                           "    базарь е\nдокрутились")
        loop = program.statements[1]
        self.assertEqual((loop.info.type, loop.info.kind), (I32, "counter"))



class VariantAnnotationTest(unittest.TestCase):
    def test_values_take_their_type_from_context(self):
        program, _ = check("зуб даю з тіпа може дрібняк це шось(1)\nзуб даю н тіпа може дрібняк це нема\n"
                           "зуб даю р тіпа вийде крупняк або облом базар це облом(гон)\nбазарь шось(5)")
        some, none, error, printed = program.statements
        self.assertEqual(some.initializer.value.type, I32)          # the literal inside is дрібняк
        self.assertEqual(none.initializer.type, OptionType(I32))
        self.assertEqual(error.initializer.type, ResultType(I64, BOOL))
        self.assertEqual(printed.value.type, OptionType(I64))       # шось alone infers its type

    def test_checks_and_fallback(self):
        program, _ = check("зуб даю з тіпа може дрібняк це нема\nбазарь з.нема\nбазарь з або 7\n"
                           "базарь реально або гон")
        check_node = program.statements[1].value
        self.assertEqual((check_node.type, check_node.variant, check_node.field_info), (BOOL, "none", None))
        fallback = program.statements[2].value
        self.assertEqual((fallback.fallback, fallback.type, fallback.right.type), (True, I32, I32))
        self.assertFalse(program.statements[3].value.fallback)      # або on базар stays logical OR



class MatchAnnotationTest(unittest.TestCase):
    def test_patterns_carry_types_bindings_and_values(self):
        program, _ = check("зуб даю з тіпа може вийде дрібняк або облом базар це нема\nрозбери з\n"
                           "випадок шось(вийшло(мінус 2))\n    базарь 0\nвипадок шось(вийшло(х))\n    базарь х\n"
                           "випадок шось(облом(_)) або нема\n    базарь 1\nрозібрали")
        first, second, third = program.statements[1].arms
        literal = first.pattern.inner.inner
        self.assertEqual((literal.type, literal.value), (I32, -2))
        binding = second.pattern.inner.inner
        self.assertEqual((binding.info.type, binding.info.kind), (I32, "immutable"))
        self.assertEqual(third.pattern.type, OptionType(ResultType(I32, BOOL)))

    def test_a_match_whose_arms_all_return_ends_the_function(self):
        check("маю дєло ф(б тіпа базар) на виході дрібняк\n    розбери б\n    випадок реально\n"
              "        тримай 1\n    випадок гон\n        тримай 0\n    розібрали\nпорішали")


if __name__ == "__main__":
    unittest.main()
