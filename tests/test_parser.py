"""Parser and AST unit tests: hierarchy, positions, and boundary cases."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ast_nodes import (  # noqa: E402
    AssignmentNode, ASTNode, BinaryNode, BlockNode, BooleanNode, DeclarationNode,
    ExitNode, ExprNode, IdentifierNode, IfNode, IntegerNode, PrintNode, ProgramNode,
    StmtNode, UnaryNode,
)
from lexer import KEYWORDS, LexError, lex  # noqa: E402
from parser import MAX_NESTING, CompilationError, Parser, parse_program  # noqa: E402


def parse(source):
    return parse_program(source.encode())


class HierarchyTest(unittest.TestCase):
    def test_class_hierarchy(self):
        for statement in (DeclarationNode, AssignmentNode, IfNode, PrintNode, ExitNode):
            self.assertTrue(issubclass(statement, StmtNode))
        for expression in (IntegerNode, BooleanNode, IdentifierNode, UnaryNode, BinaryNode):
            self.assertTrue(issubclass(expression, ExprNode))
        for node in (ProgramNode, BlockNode, StmtNode, ExprNode):
            self.assertTrue(issubclass(node, ASTNode))

    def test_declaration_fields_and_positions(self):
        program = parse("  мутна тєма ж тіпа крупняк це мінус 007")
        self.assertEqual((program.line, program.column), (1, 3))
        declaration = program.statements[0]
        self.assertIsInstance(declaration, DeclarationNode)
        self.assertEqual((declaration.name, declaration.declared_type, declaration.mutable),
                         ("ж", "i64", True))
        self.assertEqual((declaration.line, declaration.column), (1, 3))
        unary = declaration.initializer
        self.assertIsInstance(unary, UnaryNode)
        self.assertEqual((unary.operator, unary.line, unary.column), ("neg", 1, 55))
        self.assertEqual((unary.operand.value, unary.operand.column), ("7", 66))

    def test_type_words_map_to_canonical_names(self):
        for word, canonical in (("дрібняк", "i32"), ("крупняк", "i64"), ("базар", "bool")):
            with self.subTest(word=word):
                declaration = parse(f"зуб даю x тіпа {word} це 1").statements[0]
                self.assertEqual(declaration.declared_type, canonical)
                self.assertFalse(declaration.mutable)

    def test_two_word_operators_are_positioned_at_first_word(self):
        expression = parse("базарь a не рівно b").statements[0].value
        self.assertEqual((expression.operator, expression.column), ("ne", 16))
        expression = parse("базарь a ділити на b").statements[0].value
        self.assertEqual((expression.operator, expression.column), ("div", 16))
        expression = parse("базарь a і ше b").statements[0].value
        self.assertEqual((expression.operator, expression.column), ("and", 16))

    def test_all_operator_phrases_have_canonical_names(self):
        cases = {"плюс": "add", "мінус": "sub", "на": "mul", "ділити на": "div",
                 "рівно": "eq", "не рівно": "ne", "більше": "gt", "менше": "lt",
                 "і ше": "and", "або": "or"}
        for phrase, canonical in cases.items():
            with self.subTest(phrase=phrase):
                expression = parse(f"базарь a {phrase} b").statements[0].value
                self.assertEqual(expression.operator, canonical)

    def test_parentheses_create_no_node(self):
        value = parse("базарь ((x))").statements[0].value
        self.assertEqual(value, IdentifierNode(1, 16, "x"))

    def test_if_without_else_has_none(self):
        statement = parse("якшо реально реально\n  базарь 1\nотакої").statements[0]
        self.assertIsInstance(statement, IfNode)
        self.assertEqual(statement.condition, BooleanNode(1, 25, True))
        self.assertIsNone(statement.else_body)
        self.assertEqual((statement.then_body.line, statement.then_body.column), (2, 3))

    def test_empty_program_is_positioned_at_eof(self):
        program = parse("\n\nчутки: нічого\n")
        self.assertEqual((program.line, program.column, program.statements), (4, 1, []))

    def test_integer_text_is_normalised_and_unbounded(self):
        digits = "9" * 5000            # exceeds the default Python int/string conversion limit
        value = parse("базарь 000" + digits).statements[0].value
        self.assertEqual(value.value, digits)
        self.assertEqual(parse("базарь 0000").statements[0].value.value, "0")
        self.assertEqual(len(parse("базарь " + "9" * 10000).statements[0].value.value), 10000)

    def test_parser_class_entrypoint(self):
        program = Parser(lex("базарь гон".encode())).parse_program()
        self.assertEqual(program.statements, [PrintNode(1, 1, BooleanNode(1, 14, False))])


class DumpTest(unittest.TestCase):
    def test_dump_format(self):
        program = parse("зуб даю x тіпа дрібняк це 1\nвсьо розходимось x\n")
        self.assertEqual(program.dump(), "\n".join([
            "ProgramNode line=1 column=1",
            "  DeclarationNode line=1 column=1 name=x type=i32 mutable=false",
            "    initializer:",
            "      IntegerNode line=1 column=46 value=1",
            "  ExitNode line=2 column=1",
            "    value:",
            "      IdentifierNode line=2 column=33 name=x",
        ]))

    def test_dump_is_stable_between_calls(self):
        program = parse("якшо реально реально\n  базарь 1\nа нє\n  базарь 2\nотакої\n")
        self.assertEqual(program.dump(), program.dump())

    def test_dump_of_deep_left_chain_does_not_recurse(self):
        program = parse("базарь " + " плюс ".join(["1"] * 5000))
        self.assertEqual(len(program.dump().splitlines()), 3 + 4 * 4999 + 1)


class IdentifierTest(unittest.TestCase):
    def test_ukrainian_names_in_declarations_and_expressions(self):
        program = parse("зуб даю Їжак тіпа дрібняк це 1\nбазарь Їжак плюс ґанок_Є")
        self.assertEqual(program.statements[0].name, "Їжак")
        value = program.statements[1].value
        self.assertEqual((value.left.name, value.right.name), ("Їжак", "ґанок_Є"))
        # базарь: 12 bytes; space; Їжак: 8 bytes (columns 14..21); space; плюс at 23.
        self.assertEqual((value.left.column, value.column), (14, 23))

    def test_former_russian_words_are_ordinary_names(self):
        for word in ("мелочь", "если", "иначе", "конец", "базара", "либо", "ещё", "и",
                     "типа", "это", "теперь", "переобулся", "расходимся", "всё", "слухи"):
            with self.subTest(word=word):
                declaration = parse(f"зуб даю {word} тіпа дрібняк це 1").statements[0]
                self.assertEqual(declaration.name, word)
                self.assertEqual(parse(f"базарь {word}").statements[0].value.name, word)

    def test_every_reserved_word_is_rejected_as_a_name(self):
        for word in sorted(KEYWORDS):
            with self.subTest(word=word):
                with self.assertRaises(CompilationError) as context:
                    parse(f"зуб даю {word} тіпа дрібняк це 1")
                self.assertEqual((context.exception.line, context.exception.column), (1, 15))
                self.assertIn("зарезервоване слово", context.exception.message)
            with self.subTest(word=word, statement="assignment"):
                with self.assertRaises(CompilationError):
                    parse(f"перевзувся {word} тепер 1")

    def test_latin_a_in_tipa_is_not_the_keyword(self):
        parse("зуб даю x тіпа дрібняк це 1")
        with self.assertRaises(CompilationError) as context:
            parse("зуб даю x тіпa дрібняк це 1")             # final Latin a
        self.assertEqual((context.exception.line, context.exception.column), (1, 17))
        self.assertIn("Де «тіпа»", context.exception.message)
        self.assertIn("суто кирилицею", context.exception.message)

    def test_latin_a_is_a_legal_name_but_cyrillic_a_is_not(self):
        parse("зуб даю a тіпа дрібняк це 1")
        with self.assertRaises(CompilationError):
            parse("зуб даю а тіпа дрібняк це 1")


class BoundaryTest(unittest.TestCase):
    def assert_error(self, source, line, column, fragment=""):
        with self.assertRaises(CompilationError) as context:
            parse(source)
        error = context.exception
        self.assertEqual((error.line, error.column), (line, column), error.message)
        self.assertIn(fragment, error.message)

    def test_final_newline_is_optional_only_at_top_level(self):
        parse("базарь 1")
        parse("якшо реально a\n базарь 1\nотакої")
        self.assert_error("якшо реально a\n базарь 1", 2, 16, "Де «отакої»")

    def test_missing_operand_at_eof_after_cyrillic(self):
        # базарь: 12 bytes; " ж": 3; " плюс": 9; EOF at byte column 25.
        self.assert_error("базарь ж плюс", 1, 25, "кінець файлу")

    def test_missing_operand_at_end_of_crlf_line(self):
        self.assert_error("базарь ж плюс\r\n", 1, 25, "кінець рядка")

    def test_comparison_cannot_be_chained(self):
        self.assert_error("базарь a рівно b не рівно c", 1, 29, "в ланцюжок не ліпи")
        parse("базарь (a рівно b) не рівно c")

    def test_always_true_condition_needs_the_literal(self):
        self.assert_error("якшо реально\n базарь 1\nотакої", 1, 24, "якшо реально реально")
        statement = parse("якшо реально реально\n базарь 1\nотакої").statements[0]
        self.assertEqual(statement.condition.value, True)

    def test_closers_must_be_on_their_own_lines(self):
        self.assert_error("якшо реально a\n базарь 1 отакої\nотакої", 2, 17)
        self.assert_error("якшо реально a\n базарь 1\nотакої базарь 2", 3, 14)

    def test_single_closer_ends_the_whole_if_with_else(self):
        statement = parse("якшо реально a\n базарь 1\nа нє\n базарь 2\nотакої\nбазарь 3").statements
        self.assertEqual([type(node) for node in statement], [IfNode, PrintNode])
        self.assertIsNotNone(statement[0].else_body)

    def test_nested_if_has_its_own_closer(self):
        source = ("якшо реально a\n"
                  " якшо реально b\n"
                  "  базарь 1\n"
                  " отакої\n"
                  "а нє\n"
                  " базарь 2\n"
                  "отакої")
        outer = parse(source).statements[0]
        inner = outer.then_body.statements[0]
        self.assertIsInstance(inner, IfNode)
        self.assertIsNone(inner.else_body)             # а нє belongs to the outer condition
        self.assertIsNotNone(outer.else_body)
        # One отакої for two conditions leaves the outer one unclosed.
        self.assert_error("якшо реально a\n якшо реально b\n  базарь 1\nотакої", 4, 13,
                          "рядка 1:1")
        self.assert_error("якшо реально a\n базарь 1\nа нє\n якшо реально b\n  базарь 2\nотакої\n",
                          7, 1, "рядка 1:1")

    def test_else_is_two_words_on_one_line(self):
        self.assert_error("якшо реально a\n базарь 1\nа\n базарь 2\nотакої", 3, 3, "чекаю «нє»")
        self.assert_error("якшо реально a\n базарь 1\nа\nнє\n базарь 2\nотакої", 3, 3, "чекаю «нє»")
        self.assert_error("якшо реально a\n базарь 1\nа нє базарь 2\nотакої", 3, 9, "«А нє» займає")

    def test_orphan_duplicate_and_standalone_else_words(self):
        self.assert_error("а нє\n", 1, 1, "«А нє» без «якшо»")
        self.assert_error("якшо реально a\n базарь 1\nотакої\nа нє\n базарь 2\nотакої", 4, 1, "«А нє» без «якшо»")
        self.assert_error("якшо реально a\n базарь 1\nа нє\n базарь 2\nа нє\n базарь 3\nотакої",
                          5, 1, "Знову «а нє»")
        self.assert_error("нє\n", 1, 1, "Голе «нє»")
        self.assert_error("якшо реально a\n базарь 1\nнє\nотакої", 3, 1, "Голе «нє»")

    def test_ne_with_ye_is_not_a_negation_operator(self):
        for source in ("базарь нє реально", "базарь нє", "зуб даю b тіпа базар це нє гон",
                       "базарь a і ше нє b"):
            with self.subTest(source=source):
                with self.assertRaises(CompilationError) as context:
                    parse(source)
                self.assertIn("«Нє» саме по собі", context.exception.message)

    def test_ne_without_rivno_is_an_error(self):
        self.assert_error("базарь a не b", 1, 21, "«Не» без «рівно»")

    def test_orphan_closer(self):
        self.assert_error("отакої\n", 1, 1, "«Отакої» без «якшо реально»")
        self.assert_error("якшо реально a\n базарь 1\nотакої\nотакої\n", 4, 1)

    def test_empty_blocks_are_rejected(self):
        self.assert_error("якшо реально реально\nотакої", 2, 1, "Блок «якшо реально» пустий")
        self.assert_error("якшо реально реально\n базарь 1\nа нє\n чутки: пусто\nотакої", 5, 1,
                          "Блок «а нє» пустий")

    def test_former_russian_phrases_are_not_statements(self):
        for source in ("зуб даю x типа мелочь это 1",
                       "мутная тема x тіпа дрібняк це 1",
                       "мутна тєма x тіпа дрібняк це 1\nпереобулся x теперь 2",
                       "если реально реально\n базарь 1\nконец базара",
                       "якшо реально реально\n базарь 1\nиначе\n базарь 2\nотакої",
                       "якшо реально реально\n базарь 1\nконец базара",
                       "всё расходимся 0",
                       "базарь 1 и ещё 2",
                       "базарь a либо b"):
            with self.subTest(source=source):
                with self.assertRaises((CompilationError, LexError)):
                    parse(source)
        with self.assertRaises(LexError):
            parse("слухи: це вже не коментар")

    def test_removed_synonyms_are_not_accepted(self):
        for source in ("кажи 1", "якщо реально реально\n базарь 1\nотакої",
                       "зуб даю x типа дрібняк це 1", "зуб даю x тіпа дрібняк це 1\nперевзувся x теперь 2"):
            with self.subTest(source=source):
                with self.assertRaises(CompilationError):
                    parse(source)

    def test_reserved_words_cannot_be_names(self):
        self.assert_error("зуб даю базар тіпа базар це гон", 1, 15, "зарезервоване слово")
        self.assert_error("перевзувся гон тепер 1", 1, 22, "зарезервоване слово")

    def test_semantic_errors_are_not_syntax_errors(self):
        # Parsing checks only grammar; these rules belong to semantic analysis.
        for source in ("зуб даю x тіпа дрібняк це 2147483648\nперевзувся x тепер 1",
                       "якшо реально 1\n базарь невідомий\nотакої",
                       "зуб даю b тіпа базар це 1 плюс реально",
                       "всьо розходимось гон\nбазарь 1"):
            with self.subTest(source=source):
                parse(source)

    def test_nesting_limit_is_reported_as_compilation_error(self):
        depth = MAX_NESTING
        parse("базарь " + "(" * depth + "1" + ")" * depth)
        too_deep = "базарь " + "(" * (depth + 1) + "1" + ")" * (depth + 1)
        self.assert_error(too_deep, 1, 14 + depth, "ліміт компілятора")
        nested_ifs = "якшо реально a\n" * (depth + 1) + "базарь 1\n" + "отакої\n" * (depth + 1)
        self.assert_error(nested_ifs, depth + 1, 1, "ліміт компілятора")
        parse("якшо реально a\n" * depth + "базарь 1\n" + "отакої\n" * depth)


if __name__ == "__main__":
    unittest.main()
