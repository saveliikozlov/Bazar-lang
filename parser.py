"""Recursive-descent Bazar parser: one method per grammar.ebnf production.

Read lexer.lex() tokens through peek(), consuming through eat()/expect_*().
There is no backtracking; choices use one token of lookahead.

Errors use the token where parsing fails. Missing words at line end point
to NEWLINE (LF, or CR for CRLF). At EOF, the position is immediately after
the final byte.
"""

from ast_nodes import (
    AssignmentNode, BinaryNode, BlockNode, BooleanNode, ConstantDeclarationNode, DeclarationNode,
    ExitNode, IdentifierNode, IfNode, IntegerNode, PrintNode, ProgramNode,
    UnaryNode,
)
from lexer import (EOF, I64_MIN_MAGNITUDE, IDENT, INTEGER, KEYWORD, KEYWORDS, LPAREN, NEWLINE,
                   RPAREN, lex)

TYPE_NAMES = {"дрібняк": "i32", "крупняк": "i64", "базар": "bool"}

# Latin letters resembling Cyrillic can hide a substitution, such as
# тіпa with a final Latin a.
LATIN_LOOKALIKES = str.maketrans("aceiopxy", "асеіорху")

# Limit combined parenthesis/condition nesting so pathological input raises
# a diagnostic instead of exhausting Python recursion. Not a language rule.
MAX_NESTING = 100


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
        # top_statement = constant_declaration | statement
        if self.at_keyword("желєзобетонно"):
            return self.parse_constant_declaration()
        return self.parse_statement()

    def parse_statement(self):
        token = self.peek()
        if token.kind == KEYWORD:
            if token.text == "желєзобетонно":
                raise self.error("Константа «желєзобетонно» оголошується тільки на верхньому рівні "
                                 "програми, а не всередині «якшо реально».")
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
            if token.text == "якшо":
                return self.parse_if_statement()
            if token.text == "а":
                raise self.error("«А нє» без «якшо»? Ти з ким спориш?")
            if token.text == "нє":
                raise self.error("Голе «нє» нічого не значить: воно живе лише в парі «а нє» "
                                 "всередині «якшо реально».")
            if token.text == "отакої":
                raise self.error("«Отакої» без «якшо реально»? Закривати нічого: спочатку відкрий базар.")
        raise self.unexpected("інструкцію: оголошення, «перевзувся», «якшо реально», "
                              "«базарь» або «всьо розходимось»")

    def parse_constant_declaration(self):
        # "желєзобетонно", IDENT, "тіпа", type, "це", expression
        first = self.eat()
        name, declared_type, initializer = self.parse_declaration_parts("«желєзобетонно»")
        return ConstantDeclarationNode(first.line, first.column, name.text,
                                       declared_type, initializer)

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
        return DeclarationNode(first.line, first.column, name.text,
                               declared_type, mutable, initializer)

    def parse_declaration_parts(self, phrase):
        """Shared declaration suffix: IDENT, тіпа, type, це, expression."""
        name = self.expect_name(phrase)
        self.expect_keyword("тіпа", f"Де «тіпа», шеф? Після «{name.text}» треба вказати тип, а тут {{found}}.")
        declared_type = self.parse_type()
        self.expect_keyword("це", "Де «це»? Після типу чекаю «це» і початкове значення, а тут {found}.")
        return name, declared_type, self.parse_expression()

    def parse_type(self):
        # type = "дрібняк" | "крупняк" | "базар"
        if not self.at_keyword(*TYPE_NAMES):
            raise self.error(f"Який тип, шеф? Чекаю «дрібняк», «крупняк» або «базар», а тут {describe(self.peek())}.")
        return TYPE_NAMES[self.eat().text]

    def parse_assignment(self):
        # "перевзувся", IDENT, "тепер", expression
        first = self.eat()
        name = self.expect_name("«перевзувся»")
        self.expect_keyword("тепер", f"Де «тепер»? Після «{name.text}» чекаю «тепер» і нове значення, а тут {{found}}.")
        return AssignmentNode(first.line, first.column, name.text, self.parse_expression())

    def parse_print_statement(self):
        # "базарь", expression
        first = self.eat()
        return PrintNode(first.line, first.column, self.parse_expression())

    def parse_exit_statement(self):
        # "всьо", "розходимось", expression
        first = self.eat()
        self.expect_keyword("розходимось", "«Всьо» — і шо? Після нього чекаю «розходимось», а тут {found}.")
        return ExitNode(first.line, first.column, self.parse_expression())

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

    def parse_block(self, opener, branch):
        # block = { NEWLINE }, statement, NEWLINE, { NEWLINE | ( statement, NEWLINE ) }
        while self.at(NEWLINE):
            self.eat()
        if self.at_keyword("а", "отакої") or self.at(EOF):
            kind = "«якшо реально»" if branch == "if" else "«а нє»"
            raise self.error(f"Блок {kind} пустий. Хотів шось зробить чи просто зайшов?")
        first = self.peek()
        statements = [self.parse_block_statement(opener)]
        while True:
            if self.at(NEWLINE):
                self.eat()
            elif self.at_keyword("а", "отакої") or self.at(EOF):
                break
            else:
                statements.append(self.parse_block_statement(opener))
        if self.at(EOF):
            raise self.unclosed_if(opener)
        return BlockNode(first.line, first.column, statements)

    def unclosed_if(self, opener):
        return self.error(f"Де «отакої»? Базар із рядка {opener.line}:{opener.column} "
                          f"не закритий, а файл уже скінчився.")

    def parse_block_statement(self, opener):
        """Statement plus NEWLINE; line endings are required inside blocks."""
        statement = self.parse_statement()
        if self.at(EOF):
            raise self.unclosed_if(opener)
        self.expect(NEWLINE, "Після інструкції чекаю кінець рядка, а тут {found}. Одна інструкція — один рядок.")
        return statement

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
        # INTEGER | boolean_literal | IDENT | "(", expression, ")"
        token = self.peek()
        if token.kind == INTEGER:
            self.eat()
            return IntegerNode(token.line, token.column, token.text.lstrip("0") or "0")
        if token.kind == IDENT:
            self.eat()
            return IdentifierNode(token.line, token.column, token.text)
        if self.at_keyword("реально", "гон"):
            return self.parse_boolean_literal()
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

    def parse_boolean_literal(self):
        # "реально" | "гон"
        token = self.eat()
        return BooleanNode(token.line, token.column, token.text == "реально")


def parse_program(data: bytes) -> ProgramNode:
    """Lex and parse the complete source file."""
    return Parser(lex(data)).parse_program()
