"""Recursive-descent Bazar parser: one method per grammar.ebnf production.

Read lexer.lex() tokens through peek(), consuming through eat()/expect_*().
There is no backtracking; choices use one token of lookahead.

Errors use the token where parsing fails. Missing words at line end point
to NEWLINE (LF, or CR for CRLF). At EOF, the position is immediately after
the final byte.
"""

from ast_nodes import (
    ArrayFillNode, ArrayLiteralNode, ArrayTypeNode, AssignmentNode, BinaryNode, BlockNode, BooleanNode,
    BreakNode, CallNode, CallStatementNode, ConstantDeclarationNode, DeclarationNode, ExitNode,
    FieldAccessNode, FieldAssignmentNode, FieldNode, ForEachNode, ForNode, FunctionNode, IdentifierNode,
    BindingPatternNode, IfNode, IndexNode, LiteralPatternNode, MatchArmNode, MatchNode, OrPatternNode,
    StructurePatternNode, VariantPatternNode, WildcardPatternNode, IntegerNode, MemberCallNode, NamedTypeNode, NewObjectNode, OptionTypeNode,
    ParameterNode, PrintNode, ProgramNode, ReadNode, ResultTypeNode, ReturnNode, StringNode, StructureNode,
    UnaryNode, VariantNode, WhileNode,
)
from lexer import (COMMA, DOT, EOF, I64_MIN_MAGNITUDE, IDENT, INTEGER, KEYWORD, KEYWORDS, LBRACKET, LPAREN,
                   NEWLINE, RBRACKET, RPAREN, SEMICOLON, STRING, lex)

TYPE_NAMES = {"дрібняк": "i32", "крупняк": "i64", "базар": "bool"}
# The four values of може and вийде, with their canonical AST names.
VARIANTS = {"шось": "some", "нема": "none", "вийшло": "ok", "облом": "err"}

# Latin letters resembling Cyrillic can hide a substitution, such as
# тіпa with a final Latin a.
LATIN_LOOKALIKES = str.maketrans("aceiopxy", "асеіорху")

# Limit combined parenthesis/condition nesting so pathological input raises
# a diagnostic instead of exhausting Python recursion. Not a language rule.
MAX_NESTING = 100

# A block ends when one of these words starts a line.
BLOCK_CLOSERS = ("а", "отакої", "порішали", "докрутились", "випадок", "розібрали")
# The pattern _ matches anything; everywhere else it is an ordinary name.
WILDCARD = "_"


class CompilationError(Exception):
    def __init__(self, line, column, message):
        self.line = line
        self.column = column
        self.message = message
        super().__init__(f"line {line}:{column}: {message}")


def describe(token):
    """Describe a token in a Ukrainian diagnostic."""
    if token.kind == NEWLINE:
        return "кінець рядка"
    if token.kind == EOF:
        return "кінець файлу"
    if token.kind == IDENT:
        fixed = token.text.translate(LATIN_LOOKALIKES)
        if fixed != token.text and fixed in KEYWORDS and not token.text.isascii():
            return (f"ім'я «{token.text}» (латинську літеру підсунули замість кириличної: "
                    f"треба «{fixed}» суто кирилицею)")
        return f"ім'я «{token.text}»"
    if token.kind == INTEGER:
        return f"число {token.text}"
    if token.kind == STRING:
        return "рядок у лапках"
    return f"«{token.text}»"


class Parser:
    def __init__(self, tokens):
        if not tokens or tokens[-1].kind != EOF:
            raise ValueError("the token list must end with an EOF token")
        self.tokens = tokens
        self.index = 0
        self.nesting = 0

    # ------------------------------------------------------- helper methods

    def peek(self):
        return self.tokens[self.index]

    def eat(self):
        token = self.tokens[self.index]
        if token.kind != EOF:
            self.index += 1
        return token

    def at(self, kind):
        return self.peek().kind == kind

    def at_keyword(self, *words):
        token = self.peek()
        return token.kind == KEYWORD and token.text in words

    def error(self, message, token=None):
        token = token or self.peek()
        return CompilationError(token.line, token.column, message)

    def unexpected(self, expected):
        return self.error(f"Не той базар: чекаю {expected}, а тут {describe(self.peek())}.")

    def expect_keyword(self, word, message):
        """Consume word or raise a diagnostic using the supplied message.

        The {found} placeholder receives the description of the actual token."""
        if not self.at_keyword(word):
            raise self.error(message.format(found=describe(self.peek())))
        return self.eat()

    def expect(self, kind, message):
        if not self.at(kind):
            raise self.error(message.format(found=describe(self.peek())))
        return self.eat()

    def expect_range_word(self, word, message):
        """від and по are names everywhere else: only a loop header reads them as words."""
        token = self.peek()
        if token.kind != IDENT or token.text != word:
            raise self.error(message.format(found=describe(token)))
        return self.eat()

    def expect_name(self, phrase):
        token = self.peek()
        if token.kind == KEYWORD:
            raise self.error(f"«{token.text}» — зарезервоване слово, іменем воно не стане. "
                             f"Вигадай свою кличку для змінної після {phrase}.")
        return self.expect(IDENT, f"Де ім'я змінної? Після {phrase} чекаю назву, а тут {{found}}.")

    def enter(self, opener):
        """Enter one condition/parenthesis nesting level, positioned at opener."""
        self.nesting += 1
        if self.nesting > MAX_NESTING:
            raise self.error(f"Занадто глибоко закопався: понад {MAX_NESTING} рівнів "
                             f"вкладеності (ліміт компілятора).", opener)

    def leave(self):
        self.nesting -= 1

    # ----------------------------------------------------------- statements

    def parse_program(self):
        # program = { NEWLINE }, [ statement, { NEWLINE, [ statement ] } ], EOF ;
        while self.at(NEWLINE):
            self.eat()
        first = self.peek()
        statements = []
        if not self.at(EOF):
            statements.append(self.parse_top_statement())
            while self.at(NEWLINE):
                self.eat()
                if not self.at(NEWLINE) and not self.at(EOF):
                    statements.append(self.parse_top_statement())
            if not self.at(EOF):
                raise self.error(f"Після інструкції чекаю кінець рядка, а тут {describe(self.peek())}. "
                                 f"Одна інструкція — один рядок.")
        return ProgramNode(first.line, first.column, statements)

    def parse_top_statement(self):
        # top_statement = constant_declaration | function_declaration
        #               | structure_declaration | statement
        if self.at_keyword("желєзобетонно"):
            return self.parse_constant_declaration()
        if self.at_keyword("маю"):
            return self.parse_function_declaration()
        if self.at_keyword("такі"):
            return self.parse_structure_declaration()
        return self.parse_statement()

    def parse_statement(self):
        token = self.peek()
        if token.kind == KEYWORD:
            if token.text == "желєзобетонно":
                raise self.error("Константа «желєзобетонно» оголошується тільки на верхньому рівні "
                                 "програми, а не всередині «якшо реально».")
            if token.text == "маю":
                raise self.error("Функцію «маю дєло» оголошують тільки на верхньому рівні програми "
                                 "або в «такі діла», а не всередині іншого тіла.")
            if token.text == "такі":
                raise self.error("Структуру «такі діла» оголошують тільки на верхньому рівні програми.")
            if token.text == "зуб":
                return self.parse_immutable_declaration()
            if token.text == "мутна":
                return self.parse_mutable_declaration()
            if token.text == "перевзувся":
                return self.parse_assignment()
            if token.text == "базарь":
                return self.parse_print_statement()
            if token.text == "всьо":
                return self.parse_exit_statement()
            if token.text == "тримай":
                return self.parse_return_statement()
            if token.text == "якшо":
                return self.parse_if_statement()
            if token.text == "крутимось":
                return self.parse_loop_statement()
            if token.text == "розбери":
                return self.parse_match()
            if token.text == "випадок":
                raise self.error("«Випадок» без «розбери»? Розбирати нічого: спочатку «розбери» значення.")
            if token.text == "розібрали":
                raise self.error("«Розібрали» без «розбери»? Закривати нічого.")
            if token.text == "харе":
                return self.parse_break_statement()
            if token.text == "поки":
                raise self.error("«Поки» саме не ходить: цикл починається з «крутимось поки».")
            if token.text == "докрутились":
                raise self.error("«Докрутились» без «крутимось»? Закривати нічого.")
            if token.text == "а":
                raise self.error("«А нє» без «якшо»? Ти з ким спориш?")
            if token.text == "нє":
                raise self.error("Голе «нє» нічого не значить: воно живе лише в парі «а нє» "
                                 "всередині «якшо реально».")
            if token.text == "отакої":
                raise self.error("«Отакої» без «якшо реально»? Закривати нічого: спочатку відкрий базар.")
            if token.text == "порішали":
                raise self.error("«Порішали» без «маю дєло» чи «такі діла»? Закривати нічого.")
        if token.kind == IDENT and self.tokens[self.index + 1].kind in (LPAREN, DOT, LBRACKET):
            return self.parse_call_statement()
        raise self.unexpected("інструкцію: оголошення, «перевзувся», «якшо реально», "
                              "«базарь» або «всьо розходимось»")

    def parse_constant_declaration(self):
        # "желєзобетонно", IDENT, "тіпа", type, "це", expression
        first = self.eat()
        name, declared_type, initializer = self.parse_declaration_parts("«желєзобетонно»")
        return ConstantDeclarationNode(first.line, first.column, name.text, declared_type, initializer)

    def parse_immutable_declaration(self):
        # "зуб", "даю", IDENT, "тіпа", type, "це", expression
        first = self.eat()
        self.expect_keyword("даю", "Де «даю», шеф? Після «зуб» треба «даю», а тут {found}.")
        return self.parse_declaration_rest(first, "«зуб даю»", mutable=False)

    def parse_mutable_declaration(self):
        # "мутна", "тєма", IDENT, "тіпа", type, "це", expression
        first = self.eat()
        self.expect_keyword("тєма", "Де «тєма»? «Мутна» сама не ходить, після неї треба «тєма», а тут {found}.")
        return self.parse_declaration_rest(first, "«мутна тєма»", mutable=True)

    def parse_declaration_rest(self, first, phrase, mutable):
        name, declared_type, initializer = self.parse_declaration_parts(phrase)
        return DeclarationNode(first.line, first.column, name.text, declared_type, mutable, initializer)

    def parse_declaration_parts(self, phrase):
        """Shared declaration suffix: IDENT, тіпа, type, це, expression."""
        name = self.expect_name(phrase)
        self.expect_keyword("тіпа", f"Де «тіпа», шеф? Після «{name.text}» треба вказати тип, а тут {{found}}.")
        declared_type = self.parse_type()
        self.expect_keyword("це", "Де «це»? Після типу чекаю «це» і початкове значення, а тут {found}.")
        return name, declared_type, self.parse_expression()

    def parse_type(self):
        # type = "дрібняк" | "крупняк" | "базар" | IDENT | array_type
        #      | option_type | result_type
        # The node is positioned at the type: the semantic pass reports an
        # unknown structure name there.
        if self.at(IDENT):
            token = self.eat()              # a structure name, checked by the semantic pass
            return NamedTypeNode(token.line, token.column, token.text)
        if self.at(LBRACKET):
            return self.parse_array_type()
        if self.at_keyword("може", "вийде"):
            return self.parse_variant_type()
        if not self.at_keyword(*TYPE_NAMES):
            raise self.error(f"Який тип, шеф? Чекаю «дрібняк», «крупняк», «базар», назву структури, "
                             f"масив «[тип; розмір]», «може тип» або «вийде тип або облом тип», "
                             f"а тут {describe(self.peek())}.")
        token = self.eat()
        return NamedTypeNode(token.line, token.column, TYPE_NAMES[token.text])

    def parse_array_type(self):
        # array_type = "[", type, ";", expression, "]"
        opener = self.eat()
        self.enter(opener)
        element = self.parse_type()
        self.expect(SEMICOLON, "Скільки штук? Після типу елементів чекаю «;» і розмір масиву, а тут {found}.")
        start = self.index
        size = self.parse_expression()
        size_text = spell(self.tokens[start:self.index])
        self.expect(RBRACKET, f"Дужку «[» з рядка {opener.line}:{opener.column} не закрито: "
                              f"чекаю «]», а тут {{found}}.")
        self.leave()
        return ArrayTypeNode(opener.line, opener.column, element, size, size_text)

    def parse_variant_type(self):
        # option_type = "може", type
        # result_type = "вийде", type, "або", "облом", type
        opener = self.eat()
        self.enter(opener)
        inner = self.parse_type()
        if opener.text == "може":
            node = OptionTypeNode(opener.line, opener.column, inner)
        else:
            self.expect_keyword("або", "У «вийде» два типи: після першого чекаю «або облом» і тип облому, "
                                       "а тут {found}.")
            self.expect_keyword("облом", "Після «вийде … або» чекаю «облом» і тип облому, а тут {found}.")
            node = ResultTypeNode(opener.line, opener.column, inner, self.parse_type())
        self.leave()
        return node

    def parse_assignment(self):
        # "перевзувся", place, "тепер", expression
        first = self.eat()
        name, target = self.parse_place()
        self.expect_keyword("тепер", f"Де «тепер»? Після «{name.text}» чекаю «тепер» і нове значення, а тут {{found}}.")
        value = self.parse_expression()
        if target is None:
            return AssignmentNode(first.line, first.column, name.text, value)
        return FieldAssignmentNode(first.line, first.column, target, value)

    def parse_place(self):
        """place = IDENT, { ".", IDENT | "[", expression, "]" }

        Returns the last name token and a chain of FieldAccessNode and
        IndexNode, or None for a plain variable."""
        name = self.expect_name("«перевзувся»")
        target = None
        while self.at(DOT) or self.at(LBRACKET):
            if target is None:
                target = IdentifierNode(name.line, name.column, name.text)
            if self.at(LBRACKET):
                target = self.parse_index(target)
                continue
            self.eat()
            name = self.expect_field_name()
            target = FieldAccessNode(name.line, name.column, target, name.text)
        if self.at(LPAREN):
            raise self.error("У виклик не присвоюють: після «перевзувся» пиши змінну або поле, "
                             "наприклад «п.х», без дужок.")
        return name, target

    def parse_print_statement(self):
        # "базарь", ( STRING | expression )
        first = self.eat()
        if self.at(STRING):
            token = self.eat()
            return PrintNode(first.line, first.column, StringNode(token.line, token.column, token.text))
        return PrintNode(first.line, first.column, self.parse_expression())

    def parse_exit_statement(self):
        # "всьо", "розходимось", expression
        first = self.eat()
        self.expect_keyword("розходимось", "«Всьо» — і шо? Після нього чекаю «розходимось», а тут {found}.")
        return ExitNode(first.line, first.column, self.parse_expression())

    def parse_return_statement(self):
        # "тримай", expression
        first = self.eat()
        if self.at(NEWLINE) or self.at(EOF):
            raise self.error("«Тримай» — а шо тримати? Після нього чекаю значення.")
        return ReturnNode(first.line, first.column, self.parse_expression())

    def parse_call_statement(self):
        # IDENT, { [ arguments ], ".", IDENT }, arguments
        first = self.peek()
        call = self.parse_chain()
        if not isinstance(call, (CallNode, MemberCallNode)):
            raise self.error("Саме ім'я чи поле — це не інструкція. Окремим рядком можна "
                             "тільки виклик, наприклад «п.посунь(1)».", first)
        return CallStatementNode(first.line, first.column, call)

    def parse_if_statement(self):
        # "якшо", "реально", expression, NEWLINE, block,
        # [ "а", "нє", NEWLINE, block ], "отакої"
        first = self.eat()
        self.expect_keyword("реально", "Де «реально»? «Якшо» без «реально» не ходить, а тут {found}.")
        if self.at(NEWLINE) or self.at(EOF):
            raise self.error("Умову загубив після «якшо реально». "
                             "Для істини пиши «якшо реально реально».")
        self.enter(first)
        condition = self.parse_expression()
        self.expect(NEWLINE, "Умова скінчилась, а далі {found}? Тіло блоку пиши з нового рядка.")
        then_body = self.parse_block(first, "if")
        else_body = None
        if self.at_keyword("а"):
            self.eat()
            self.expect_keyword("нє", "Після «а» чекаю «нє», а тут {found}. «А нє» — одна фраза в одному рядку.")
            self.expect(NEWLINE, "«А нє» займає цілий рядок: після «нє» чекаю кінець рядка, а тут {found}.")
            else_body = self.parse_block(first, "else")
            if self.at_keyword("а"):
                raise self.error("Знову «а нє»? Одному «якшо реально» вистачить одного «а нє».")
        self.expect_keyword("отакої", f"Де «отакої»? Базар із рядка {first.line}:{first.column} "
                                      f"відкрив, а закрити забув, тут {{found}}.")
        self.leave()
        return IfNode(first.line, first.column, condition, then_body, else_body)

    def parse_loop_statement(self):
        # loop_statement = while_loop | for_loop
        first = self.eat()
        if self.at_keyword("поки"):
            return self.parse_while_loop(first)
        return self.parse_for_loop(first)

    def parse_while_loop(self, first):
        # "крутимось", "поки", expression, NEWLINE, block, "докрутились"
        self.eat()
        if self.at(NEWLINE) or self.at(EOF):
            raise self.error("Умову загубив після «крутимось поки». "
                             "Для вічного циклу пиши «крутимось поки реально».")
        self.enter(first)
        condition = self.parse_expression()
        self.expect(NEWLINE, "Умова скінчилась, а далі {found}? Тіло циклу пиши з нового рядка.")
        return WhileNode(first.line, first.column, condition, self.parse_loop_body(first))

    def parse_for_loop(self, first):
        # "крутимось", IDENT, "тіпа", type, "від", expression, "по", expression,
        # NEWLINE, block, "докрутились"
        # or the array loop: "крутимось", IDENT, "тіпа", type, "з", expression,
        # NEWLINE, block, "докрутились"
        name = self.expect_name("«крутимось»")
        self.expect_keyword("тіпа", f"Де «тіпа», шеф? Після лічильника «{name.text}» треба вказати тип, "
                                    f"а тут {{found}}.")
        declared_type = self.parse_type()
        if self.peek().kind == IDENT and self.peek().text == "з":
            return self.parse_for_each_loop(first, name, declared_type)
        self.expect_range_word("від", "Звідки крутимось? Після типу чекаю «від» і початок "
                                      "або «з» і масив, а тут {found}.")
        self.enter(first)
        start = self.parse_expression()
        self.expect_range_word("по", "Докуди крутимось? Після початку чекаю «по» і кінець, а тут {found}.")
        end = self.parse_expression()
        self.expect(NEWLINE, "Заголовок циклу скінчився, а далі {found}? Тіло циклу пиши з нового рядка.")
        body = self.parse_loop_body(first)
        return ForNode(first.line, first.column, name.text, declared_type, start, end, body)

    def parse_for_each_loop(self, first, name, declared_type):
        self.eat()                           # з
        self.enter(first)
        array = self.parse_expression()
        self.expect(NEWLINE, "Заголовок циклу скінчився, а далі {found}? Тіло циклу пиши з нового рядка.")
        body = self.parse_loop_body(first)
        return ForEachNode(first.line, first.column, name.text, declared_type, array, body)

    def parse_loop_body(self, opener):
        """The block of a loop and its closer; ends the nesting level the header entered."""
        body = self.parse_block(opener, "loop")
        self.expect_keyword("докрутились", f"Де «докрутились»? Цикл із рядка {opener.line}:{opener.column} "
                                           f"відкрив, а закрити забув, тут {{found}}.")
        self.leave()
        return body

    def parse_match(self):
        # match_statement = "розбери", expression, NEWLINE, { NEWLINE },
        #                   arm, { arm }, "розібрали"
        first = self.eat()
        if self.at(NEWLINE) or self.at(EOF):
            raise self.error("«Розбери» — а шо розбирати? Після нього чекаю значення.")
        self.enter(first)
        subject = self.parse_expression()
        self.expect(NEWLINE, "Після значення для «розбери» чекаю кінець рядка, а тут {found}. "
                             "Кожен «випадок» пиши з нового рядка.")
        while self.at(NEWLINE):
            self.eat()
        if not self.at_keyword("випадок"):
            if self.at(EOF):
                raise self.unclosed_if(first)
            raise self.error(f"Після «розбери» чекаю хоч один «випадок», а тут {describe(self.peek())}.")
        arms = []
        while self.at_keyword("випадок"):
            arms.append(self.parse_arm(first))
        self.expect_keyword("розібрали", f"Де «розібрали»? «Розбери» з рядка {first.line}:{first.column} "
                                         f"відкрив, а закрити забув, тут {{found}}.")
        self.leave()
        return MatchNode(first.line, first.column, subject, arms)

    def parse_arm(self, opener):
        # arm = "випадок", pattern, [ "якшо", "реально", expression ], NEWLINE, block
        first = self.eat()
        pattern = self.parse_pattern()
        guard = None
        if self.at_keyword("якшо"):
            self.eat()
            self.expect_keyword("реально", "Умова випадку пишеться «якшо реально …», а тут {found}.")
            guard = self.parse_expression()
        self.expect(NEWLINE, "Після зразка чекаю кінець рядка або «якшо реально» з умовою, а тут {found}. "
                             "Тіло випадку пиши з нового рядка.")
        body = self.parse_block(opener, "arm")
        return MatchArmNode(first.line, first.column, pattern, guard, body)

    def parse_pattern(self):
        # pattern = alternative, { "або", alternative }
        first = self.parse_pattern_alternative()
        if not self.at_keyword("або"):
            return first
        alternatives = [first]
        while self.at_keyword("або"):
            self.eat()
            alternatives.append(self.parse_pattern_alternative())
        return OrPatternNode(first.line, first.column, alternatives)

    def parse_pattern_alternative(self):
        # alternative = "_" | IDENT | IDENT, "(", [ pattern, { ",", pattern } ], ")"
        #             | [ "мінус" ], INTEGER | "реально" | "гон"
        #             | "шось", "(", pattern, ")" | "нема" | "вийшло", "(", pattern, ")"
        #             | "облом", "(", pattern, ")" | "(", pattern, ")"
        token = self.peek()
        if token.kind == IDENT:
            self.eat()
            if self.at(LPAREN):
                return StructurePatternNode(token.line, token.column, token.text, self.parse_pattern_list(token))
            if token.text == WILDCARD:
                return WildcardPatternNode(token.line, token.column)
            return BindingPatternNode(token.line, token.column, token.text)
        if token.kind == INTEGER or self.at_keyword("мінус"):
            minus = self.eat() if self.at_keyword("мінус") else None
            digits = self.expect(INTEGER, "Після «мінус» у зразку чекаю число, а тут {found}.")
            if minus is None and digits.text.lstrip("0") == I64_MIN_MAGNITUDE:
                raise self.error(f"Число {I64_MIN_MAGNITUDE} не влазить навіть у «крупняк»: "
                                 f"так можна писати тільки «мінус {I64_MIN_MAGNITUDE}».", digits)
            literal = IntegerNode(digits.line, digits.column, digits.text.lstrip("0") or "0")
            if minus is not None:
                literal = UnaryNode(minus.line, minus.column, "neg", literal)
            return LiteralPatternNode(token.line, token.column, literal)
        if self.at_keyword("реально", "гон"):
            return LiteralPatternNode(token.line, token.column, self.parse_boolean_literal())
        if self.at_keyword(*VARIANTS):
            self.eat()
            variant = VARIANTS[token.text]
            if variant == "none":
                return VariantPatternNode(token.line, token.column, variant, None)
            opener = self.expect(LPAREN, f"Після «{token.text}» у зразку чекаю «(» і зразок у дужках, "
                                         f"а тут {{found}}.")
            self.enter(opener)
            inner = self.parse_pattern()
            self.expect(RPAREN, f"Дужку з рядка {opener.line}:{opener.column} не закрито: чекаю «)», "
                                f"а тут {{found}}.")
            self.leave()
            return VariantPatternNode(token.line, token.column, variant, inner)
        if token.kind == LPAREN:
            self.eat()
            self.enter(token)
            inner = self.parse_pattern()
            self.expect(RPAREN, f"Дужку з рядка {token.line}:{token.column} не закрито: чекаю «)», а тут {{found}}.")
            self.leave()
            return inner
        raise self.error(f"Шо за зразок? Чекаю «_», ім'я, число, «реально», «гон», «шось(…)», «нема», "
                         f"«вийшло(…)», «облом(…)» або структуру «Назва(…)», а тут {describe(token)}.")

    def parse_pattern_list(self, name):
        opener = self.eat()
        self.enter(opener)
        patterns = []
        if not self.at(RPAREN):
            patterns.append(self.parse_pattern())
            while self.at(COMMA):
                self.eat()
                patterns.append(self.parse_pattern())
        self.expect(RPAREN, f"Дужку з рядка {opener.line}:{opener.column} не закрито: "
                            f"чекаю «,» або «)», а тут {{found}}.")
        self.leave()
        return patterns

    def parse_break_statement(self):
        # "харе"
        first = self.eat()
        return BreakNode(first.line, first.column)

    def parse_block(self, opener, branch):
        # block = { NEWLINE }, statement, NEWLINE, { NEWLINE | ( statement, NEWLINE ) }
        while self.at(NEWLINE):
            self.eat()
        if self.at_keyword(*BLOCK_CLOSERS) or self.at(EOF):
            kind = {"if": "«якшо реально»", "else": "«а нє»", "loop": "«крутимось»", "arm": "«випадок»"}[branch]
            raise self.error(f"Блок {kind} пустий. Хотів шось зробить чи просто зайшов?")
        first = self.peek()
        statements = [self.parse_block_statement(opener)]
        while True:
            if self.at(NEWLINE):
                self.eat()
            elif self.at_keyword(*BLOCK_CLOSERS) or self.at(EOF):
                break
            else:
                statements.append(self.parse_block_statement(opener))
        if self.at(EOF):
            raise self.unclosed_if(opener)
        return BlockNode(first.line, first.column, statements)

    def unclosed_if(self, opener):
        if opener.text == "розбери":
            return self.error(f"Де «розібрали»? «Розбери» з рядка {opener.line}:{opener.column} "
                              f"не закрито, а файл уже скінчився.")
        if opener.text == "крутимось":
            return self.error(f"Де «докрутились»? Цикл із рядка {opener.line}:{opener.column} "
                              f"не закритий, а файл уже скінчився.")
        return self.error(f"Де «отакої»? Базар із рядка {opener.line}:{opener.column} "
                          f"не закритий, а файл уже скінчився.")

    def parse_block_statement(self, opener):
        """Statement plus NEWLINE; line endings are required inside blocks."""
        statement = self.parse_statement()
        if self.at(EOF):
            raise self.unclosed_if(opener)
        self.expect(NEWLINE, "Після інструкції чекаю кінець рядка, а тут {found}. Одна інструкція — один рядок.")
        return statement

    # ------------------------------------------- functions and structures

    def parse_function_declaration(self):
        # "маю", "дєло", IDENT, "(", [ parameter, { ",", parameter } ], ")",
        # "на", "виході", type, NEWLINE, block, "порішали"
        first = self.eat()
        self.expect_keyword("дєло", "«Маю» — а шо маєш? Після «маю» чекаю «дєло», а тут {found}.")
        name = self.expect_declared_name("функції", "«маю дєло»")
        opener = self.expect(LPAREN, f"Після «{name.text}» чекаю «(» зі списком параметрів, "
                                     f"навіть порожнім «()», а тут {{found}}.")
        parameters = []
        if not self.at(RPAREN):
            parameters.append(self.parse_parameter())
            while self.at(COMMA):
                self.eat()
                parameters.append(self.parse_parameter())
        self.expect(RPAREN, f"Список параметрів з рядка {opener.line}:{opener.column} не закрито: "
                            f"чекаю «,» або «)», а тут {{found}}.")
        self.expect_keyword("на", "Шо на виході? Після «)» чекаю «на виході» і тип результату, а тут {found}.")
        self.expect_keyword("виході", "Після «на» чекаю «виході» і тип результату, а тут {found}.")
        result_type = self.parse_type()
        self.expect(NEWLINE, "Заголовок «маю дєло» скінчився, а далі {found}? Тіло пиши з нового рядка.")
        self.enter(first)
        body = self.parse_body(first, "функції «" + name.text + "»")
        self.leave()
        self.eat()                           # порішали
        return FunctionNode(first.line, first.column, name.text, parameters, result_type, body)

    def parse_parameter(self):
        # parameter = IDENT, "тіпа", type
        name = self.expect_declared_name("параметра", "«(» або «,»")
        self.expect_keyword("тіпа", f"Де «тіпа», шеф? Після параметра «{name.text}» треба вказати тип, "
                                    f"а тут {{found}}.")
        return ParameterNode(name.line, name.column, name.text, self.parse_type())

    def parse_body(self, opener, what):
        """A function body: a block closed by порішали, which is left unconsumed."""
        while self.at(NEWLINE):
            self.eat()
        if self.at_keyword("порішали") or self.at(EOF):
            if self.at(EOF):
                raise self.unclosed_body(opener)
            raise self.error(f"Тіло {what} пусте. Хоч «тримай» напиши.")
        first = self.peek()
        statements = [self.parse_body_statement(opener)]
        while not self.at_keyword("порішали"):
            if self.at(EOF):
                raise self.unclosed_body(opener)
            if self.at(NEWLINE):
                self.eat()
            else:
                statements.append(self.parse_body_statement(opener))
        return BlockNode(first.line, first.column, statements)

    def parse_body_statement(self, opener):
        if self.at_keyword("а", "отакої"):
            self.parse_statement()           # raises the matching diagnostic
        statement = self.parse_statement()
        if self.at(EOF):
            raise self.unclosed_body(opener)
        self.expect(NEWLINE, "Після інструкції чекаю кінець рядка, а тут {found}. Одна інструкція — один рядок.")
        return statement

    def unclosed_body(self, opener):
        phrase = "маю дєло" if opener.text == "маю" else "такі діла"
        return self.error(f"Де «порішали»? «{phrase}» з рядка {opener.line}:{opener.column} "
                          f"не закрито, а файл уже скінчився.")

    def parse_structure_declaration(self):
        # "такі", "діла", IDENT, NEWLINE, { NEWLINE }, member, NEWLINE,
        # { NEWLINE | ( member, NEWLINE ) }, "порішали"
        first = self.eat()
        self.expect_keyword("діла", "«Такі» — а далі? Після «такі» чекаю «діла», а тут {found}.")
        name = self.expect_declared_name("структури", "«такі діла»")
        self.expect(NEWLINE, f"Після «такі діла {name.text}» чекаю кінець рядка, а тут {{found}}. "
                             f"Поля пиши з нового рядка.")
        fields, methods = [], []
        while True:
            if self.at(NEWLINE):
                self.eat()
            elif self.at(EOF):
                raise self.unclosed_body(first)
            elif self.at_keyword("порішали"):
                break
            else:
                self.parse_member(fields, methods)
                if self.at(EOF):
                    raise self.unclosed_body(first)
                self.expect(NEWLINE, "Після поля чи функції чекаю кінець рядка, а тут {found}.")
        if not fields and not methods:
            raise self.error(f"Структура «{name.text}» пуста. Дай їй хоч одне поле чи функцію.")
        self.eat()                           # порішали
        return StructureNode(first.line, first.column, name.text, fields, methods)

    def parse_member(self, fields, methods):
        # member = field_declaration | function_declaration
        if self.at_keyword("маю"):
            methods.append(self.parse_function_declaration())
        elif self.at_keyword("зуб", "мутна"):
            fields.append(self.parse_field_declaration(len(fields)))
        else:
            raise self.unexpected("поле («зуб даю» чи «мутна тєма»), функцію «маю дєло» або «порішали»")

    def parse_field_declaration(self, index):
        # ( "зуб", "даю" | "мутна", "тєма" ), IDENT, "тіпа", type, [ "це", expression ]
        first = self.eat()
        mutable = first.text == "мутна"
        if mutable:
            self.expect_keyword("тєма", "Де «тєма»? «Мутна» сама не ходить, після неї треба «тєма», а тут {found}.")
        else:
            self.expect_keyword("даю", "Де «даю», шеф? Після «зуб» треба «даю», а тут {found}.")
        name = self.expect_declared_name("поля", "«зуб даю» чи «мутна тєма»")
        self.expect_keyword("тіпа", f"Де «тіпа», шеф? Після поля «{name.text}» треба вказати тип, а тут {{found}}.")
        declared_type = self.parse_type()
        default = None
        if self.at_keyword("це"):
            self.eat()
            default = self.parse_expression()
        return FieldNode(first.line, first.column, name.text, declared_type, mutable, index, default)

    def expect_declared_name(self, what, phrase):
        token = self.peek()
        if token.kind == KEYWORD:
            raise self.error(f"«{token.text}» — зарезервоване слово, назвою {what} воно не стане.")
        return self.expect(IDENT, f"Де назва {what}? Після {phrase} чекаю ім'я, а тут {{found}}.")

    def expect_field_name(self):
        token = self.peek()
        if token.kind == KEYWORD:
            raise self.error(f"«{token.text}» — зарезервоване слово, полем воно не стане.")
        return self.expect(IDENT, "Після «.» чекаю назву поля чи функції, а тут {found}.")

    # ---------------------------------------------------------- expressions

    def parse_expression(self):
        # expression = or_expression
        return self.parse_or_expression()

    def parse_or_expression(self):
        # and_expression, { "або", and_expression }
        node = self.parse_and_expression()
        while self.at_keyword("або"):
            operator = self.eat()
            right = self.parse_and_expression()
            node = BinaryNode(operator.line, operator.column, "or", node, right)
        return node

    def parse_and_expression(self):
        # comparison, { "і", "ше", comparison }
        node = self.parse_comparison()
        while self.at_keyword("і"):
            operator = self.eat()
            self.expect_keyword("ше", "«І» сам нікуди не йде: після нього чекаю «ше», а тут {found}.")
            right = self.parse_comparison()
            node = BinaryNode(operator.line, operator.column, "and", node, right)
        return node

    def parse_comparison(self):
        # additive, [ comparison_operator, additive ]
        node = self.parse_additive()
        found = self.parse_comparison_operator()
        if found is None:
            return node
        operator, name = found
        right = self.parse_additive()
        if self.at_keyword("рівно", "не", "більше", "менше"):
            raise self.error("Порівняння в ланцюжок не ліпи: з'єднай їх через «і ше» / «або» "
                             "або візьми дужки.")
        return BinaryNode(operator.line, operator.column, name, node, right)

    def parse_comparison_operator(self):
        # "рівно" | "не", "рівно" | "більше" | "менше"
        if self.at_keyword("рівно"):
            return self.eat(), "eq"
        if self.at_keyword("не"):
            operator = self.eat()
            self.expect_keyword("рівно", "«Не» без «рівно»? Для нерівності пиши «не рівно», а тут {found}.")
            return operator, "ne"
        if self.at_keyword("більше"):
            return self.eat(), "gt"
        if self.at_keyword("менше"):
            return self.eat(), "lt"
        return None

    def parse_additive(self):
        # multiplicative, { additive_operator, multiplicative }
        node = self.parse_multiplicative()
        while True:
            found = self.parse_additive_operator()
            if found is None:
                return node
            operator, name = found
            right = self.parse_multiplicative()
            node = BinaryNode(operator.line, operator.column, name, node, right)

    def parse_additive_operator(self):
        # "плюс" | "мінус"
        if self.at_keyword("плюс"):
            return self.eat(), "add"
        if self.at_keyword("мінус"):
            return self.eat(), "sub"
        return None

    def parse_multiplicative(self):
        # unary, { multiplicative_operator, unary }
        node = self.parse_unary()
        while True:
            found = self.parse_multiplicative_operator()
            if found is None:
                return node
            operator, name = found
            right = self.parse_unary()
            node = BinaryNode(operator.line, operator.column, name, node, right)

    def parse_multiplicative_operator(self):
        # "на" | "ділити", "на"
        if self.at_keyword("на"):
            return self.eat(), "mul"
        if self.at_keyword("ділити"):
            operator = self.eat()
            self.expect_keyword("на", "«Ділити» на шо? Після нього треба слово «на», а тут {found}.")
            return operator, "div"
        return None

    def parse_unary(self):
        # unary = "мінус", unary | primary
        # Replace right recursion with a loop: collect мінус tokens, parse
        # the primary, then wrap negations from the innermost outward.
        minuses = []
        while self.at_keyword("мінус"):
            minuses.append(self.eat())
        token = self.peek()
        node = self.parse_primary()
        # Overflow check, second layer: 2**63 is i64's minimum only when negated.
        if not minuses and token.kind == INTEGER and node.value == I64_MIN_MAGNITUDE:
            raise self.error(f"Число {I64_MIN_MAGNITUDE} не влазить навіть у «крупняк»: "
                             f"так можна писати тільки «мінус {I64_MIN_MAGNITUDE}».", token)
        for operator in reversed(minuses):
            node = UnaryNode(operator.line, operator.column, "neg", node)
        return node

    def parse_primary(self):
        # INTEGER | boolean_literal | read_expression | object_creation
        # | chain | "(", expression, ")"
        token = self.peek()
        if token.kind == INTEGER:
            self.eat()
            if self.at(DOT):
                raise self.error("Дробових чисел у Базарі нема: тільки цілі, без «.».")
            return IntegerNode(token.line, token.column, token.text.lstrip("0") or "0")
        if token.kind == IDENT:
            return self.parse_chain()
        if self.at_keyword("реально", "гон"):
            return self.parse_boolean_literal()
        if self.at_keyword("ану"):
            return self.parse_read_expression()
        if self.at_keyword("склепай"):
            return self.parse_object_creation()
        if token.kind == LBRACKET:
            return self.parse_array_literal()
        if self.at_keyword(*VARIANTS):
            return self.parse_variant()
        if token.kind == STRING:
            raise self.error("Рядок у лапках можна тільки базарити: «базарь \"...\"». "
                             "У виразах рядків нема.")
        if token.kind == LPAREN:
            self.eat()
            self.enter(token)
            node = self.parse_expression()
            self.expect(RPAREN, f"Дужку з рядка {token.line}:{token.column} не закрито: чекаю «)», а тут {{found}}.")
            self.leave()
            return node
        if token.kind == KEYWORD and token.text == "нє":
            raise self.error("«Нє» саме по собі — не заперечення: логічного НЕ в мові нема.")
        raise self.error(f"Де значення? Тут має бути число, «реально», «гон», ім'я або «(», а не {describe(token)}.")

    def parse_read_expression(self):
        # "ану", "кажи"
        first = self.eat()
        self.expect_keyword("кажи", "«Ану» — і шо? Після «ану» чекаю «кажи», а тут {found}.")
        return ReadNode(first.line, first.column)

    def parse_object_creation(self):
        # "склепай", IDENT, arguments
        first = self.eat()
        name = self.expect_declared_name("структури", "«склепай»")
        if not self.at(LPAREN):
            raise self.error(f"Після «склепай {name.text}» чекаю «(» зі значеннями полів, а тут "
                             f"{describe(self.peek())}.")
        return NewObjectNode(first.line, first.column, name.text, self.parse_arguments())

    def parse_chain(self):
        # IDENT, [ arguments ], { ".", IDENT, [ arguments ] | "[", expression, "]" }
        name = self.eat()
        if self.at(LPAREN):
            node = CallNode(name.line, name.column, name.text, self.parse_arguments())
        else:
            node = IdentifierNode(name.line, name.column, name.text)
        while self.at(DOT) or self.at(LBRACKET):
            if self.at(LBRACKET):
                node = self.parse_index(node)
                continue
            self.eat()
            if self.at_keyword(*VARIANTS):
                # з.шось, з.нема, р.вийшло, р.облом: which value a може or вийде holds.
                check = self.eat()
                if self.at(LPAREN):
                    raise self.error(f"«.{check.text}» — перевірка, а не функція: пиши без дужок.")
                node = FieldAccessNode(check.line, check.column, node, check.text)
                continue
            member = self.expect_field_name()
            if self.at(LPAREN):
                node = MemberCallNode(member.line, member.column, node, member.text, self.parse_arguments())
            else:
                node = FieldAccessNode(member.line, member.column, node, member.text)
        return node

    def parse_variant(self):
        # variant = "шось", "(", expression, ")" | "нема"
        #         | "вийшло", "(", expression, ")" | "облом", "(", expression, ")"
        word = self.eat()
        if word.text == "нема":
            return VariantNode(word.line, word.column, "none", None)
        opener = self.expect(LPAREN, f"Після «{word.text}» чекаю «(» і значення в дужках, а тут {{found}}.")
        self.enter(opener)
        value = self.parse_expression()
        self.expect(RPAREN, f"Дужку з рядка {opener.line}:{opener.column} не закрито: чекаю «)», а тут {{found}}.")
        self.leave()
        return VariantNode(word.line, word.column, VARIANTS[word.text], value)

    def parse_index(self, node):
        # "[", expression, "]" after a chain: one element of an array
        opener = self.eat()
        self.enter(opener)
        index = self.parse_expression()
        self.expect(RBRACKET, f"Дужку «[» з рядка {opener.line}:{opener.column} не закрито: "
                              f"чекаю «]», а тут {{found}}.")
        self.leave()
        return IndexNode(opener.line, opener.column, node, index)

    def parse_array_literal(self):
        # "[", "всюди", expression, "]" | "[", expression, { ",", expression }, "]"
        opener = self.eat()
        self.enter(opener)
        if self.at_keyword("всюди"):
            self.eat()
            node = ArrayFillNode(opener.line, opener.column, self.parse_expression())
            expected = "«]»"
        else:
            if self.at(RBRACKET):
                raise self.error("Порожній масив не канає: дай хоч один елемент або пиши «[всюди ...]».")
            elements = [self.parse_expression()]
            while self.at(COMMA):
                self.eat()
                elements.append(self.parse_expression())
            node = ArrayLiteralNode(opener.line, opener.column, elements)
            expected = "«,» або «]»"
        self.expect(RBRACKET, f"Дужку «[» з рядка {opener.line}:{opener.column} не закрито: "
                              f"чекаю {expected}, а тут {{found}}.")
        self.leave()
        return node

    def parse_arguments(self):
        # "(", [ expression, { ",", expression } ], ")"
        opener = self.eat()
        self.enter(opener)
        arguments = []
        if not self.at(RPAREN):
            arguments.append(self.parse_expression())
            while self.at(COMMA):
                self.eat()
                arguments.append(self.parse_expression())
        self.expect(RPAREN, f"Дужку з рядка {opener.line}:{opener.column} не закрито: "
                            f"чекаю «,» або «)», а тут {{found}}.")
        self.leave()
        return arguments

    def parse_boolean_literal(self):
        # "реально" | "гон"
        token = self.eat()
        return BooleanNode(token.line, token.column, token.text == "реально")


def spell(tokens):
    """Source-like text of a token run: words apart, no space inside brackets or before a comma."""
    text = ""
    for token in tokens:
        if text and not text.endswith(("(", "[")) and token.kind not in (RPAREN, RBRACKET, COMMA):
            text += " "
        text += token.text
    return text


def parse_program(data: bytes) -> ProgramNode:
    """Lex and parse the complete source file."""
    return Parser(lex(data)).parse_program()
