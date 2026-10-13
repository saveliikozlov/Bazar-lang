"""Handwritten Bazar lexer: finite-state machines over source bytes.

Two machines cooperate in one byte-by-byte pass:
* the UTF-8 machine validates all bytes, including comments, and assembles
  Unicode scalar values from multibyte sequences;
* the token machine (START, WORD, APOSTROPHE, INTEGER, COMMENT, CR) receives each scalar
  and its first-byte offset, then emits tokens.

No regular expressions, str.split(), or lexer generators are used. Words
are read completely before keyword lookup, so keywords never match prefixes.

Positions are 1-based. Columns count UTF-8 bytes from the line start: a
Cyrillic letter advances by two, an emoji by four, and a tab by one. LF and
CRLF end a line; the next byte is column 1 of the next line. EOF is positioned
immediately after the last input byte.
"""

from dataclasses import dataclass
import errno
from pathlib import Path
import sys

# Token kinds.
KEYWORD = "keyword"
IDENT = "ident"
INTEGER = "integer"
LPAREN = "lparen"
RPAREN = "rparen"
NEWLINE = "newline"
EOF = "eof"

# Every individual word of every phrase is independently reserved.
KEYWORDS = frozenset((
    "желєзобетонно", "зуб", "даю", "мутна", "тєма", "тіпа", "це",
    "дрібняк", "крупняк", "базар",
    "перевзувся", "тепер", "базарь", "всьо", "розходимось",
    "якшо", "реально", "а", "нє", "отакої",
    "гон", "або", "і", "ше", "рівно", "не", "більше", "менше",
    "плюс", "мінус", "на", "ділити",
))
# Overflow check, first layer: no integer type is wider than крупняк (i64).
# The largest literal is the magnitude of i64's minimum, 2**63, which is only
# valid directly after unary мінус (enforced by the parser).
I64_MAX = "9223372036854775807"
I64_MIN_MAGNITUDE = "9223372036854775808"


def exceeds_i64_magnitude(digits):
    """Compare decimal text with 2**63 without converting it to int."""
    digits = digits.lstrip("0") or "0"
    if len(digits) != len(I64_MIN_MAGNITUDE):
        return len(digits) > len(I64_MIN_MAGNITUDE)
    return digits > I64_MIN_MAGNITUDE


# Also reserved, but not emitted as a token: чутки: starts a comment.
COMMENT_WORD = "чутки"

# NEWLINE text is identical for LF and CRLF source endings.
NEWLINE_TEXT = "\n"

TAB, LF, CR, SPACE = 0x09, 0x0A, 0x0D, 0x20
COLON, LEFT_PAREN, RIGHT_PAREN, UNDERSCORE = 0x3A, 0x28, 0x29, 0x5F
BYTE_ORDER_MARK = 0xFEFF
# Ukrainian apostrophe inside a name: ASCII ' and U+02BC modifier letter apostrophe.
APOSTROPHES = frozenset((0x27, 0x02BC))
APOSTROPHE_MESSAGE = "Апостроф ставлять тільки між літерами, як у «з'їзд»."

# Token state machine states.
START, WORD, APOSTROPHE, NUMBER, COMMENT, AFTER_CR = (
    "START", "WORD", "APOSTROPHE", "INTEGER", "COMMENT", "CR")


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    line: int
    column: int


class LexError(Exception):
    def __init__(self, line, column, message):
        self.line = line
        self.column = column
        self.message = message
        super().__init__(f"line {line}:{column}: {message}")


# І/і, Ї/ї, Є/є, Ґ/ґ are outside the А-Я/а-я ranges.
UKRAINIAN_LETTERS = frozenset((0x0406, 0x0456, 0x0407, 0x0457,
                               0x0404, 0x0454, 0x0490, 0x0491))


def is_digit(cp):
    return 0x30 <= cp <= 0x39


def is_letter(cp):
    """ASCII letters, А-Я / а-я, Ё/ё, and Ukrainian І/і, Ї/ї, Є/є, Ґ/ґ."""
    return (0x41 <= cp <= 0x5A or 0x61 <= cp <= 0x7A
            or 0x0410 <= cp <= 0x044F or cp == 0x0401 or cp == 0x0451
            or cp in UKRAINIAN_LETTERS)


def is_word_start(cp):
    return is_letter(cp) or cp == UNDERSCORE


def is_word_part(cp):
    return is_word_start(cp) or is_digit(cp)


def describe_character(cp):
    if 0x21 <= cp <= 0x7E:
        return f"'{chr(cp)}'"
    return f"U+{cp:04X}"


class Lexer:
    def __init__(self, data: bytes):
        self.data = data
        self.tokens = []
        self.state = START
        self.line = 1
        self.line_start = 0          # offset of the line first byte
        self.token_start = 0         # byte offset where the current token began
        self.token_line = 1
        self.token_column = 1
        self.after_letter = False    # WORD: was the previous scalar a letter?
        self.apostrophe_offset = 0

    # -------------------------------------------------- UTF-8 state machine

    def run(self):
        data = self.data
        need = 0           # number of continuation bytes still required
        scalar = 0         # code point being assembled
        sequence_start = 0
        low, high = 0x80, 0xBF   # permitted range for the next continuation byte

        for offset in range(len(data)):
            byte = data[offset]
            if need == 0:
                if byte <= 0x7F:
                    self.feed(byte, offset)
                    continue
                sequence_start = offset
                low, high = 0x80, 0xBF
                if 0xC2 <= byte <= 0xDF:
                    need, scalar = 1, byte & 0x1F
                elif 0xE0 <= byte <= 0xEF:
                    need, scalar = 2, byte & 0x0F
                    if byte == 0xE0:
                        low = 0xA0       # lower values would be overlong three-byte encodings
                    elif byte == 0xED:
                        high = 0x9F      # higher values would be UTF-16 surrogates
                elif 0xF0 <= byte <= 0xF4:
                    need, scalar = 3, byte & 0x07
                    if byte == 0xF0:
                        low = 0x90       # lower values would be overlong four-byte encodings
                    elif byte == 0xF4:
                        high = 0x8F      # higher values would exceed U+10FFFF
                elif byte <= 0xBF:
                    raise self.error_at(offset, f"Мутне кодування UTF-8: байт продовження 0x{byte:02X} висить без початку.")
                elif byte <= 0xC1:
                    raise self.error_at(offset, f"Мутне кодування UTF-8: надлишкова послідовність (байт 0x{byte:02X}), так символ не пишуть.")
                else:
                    raise self.error_at(offset, f"Мутне кодування UTF-8: байту 0x{byte:02X} тут не місце.")
            else:
                if not low <= byte <= high:
                    raise self.error_at(sequence_start, self.bad_continuation(sequence_start, byte))
                scalar = (scalar << 6) | (byte & 0x3F)
                need -= 1
                low, high = 0x80, 0xBF
                if need == 0:
                    self.feed(scalar, sequence_start)

        if need:
            raise self.error_at(sequence_start, "Мутне кодування UTF-8: файл скінчився, а символ не дописаний.")
        self.feed(None, len(data))
        return self.tokens

    def bad_continuation(self, sequence_start, byte):
        lead = self.data[sequence_start]
        if 0x80 <= byte <= 0xBF:
            if lead in (0xE0, 0xF0):
                return "Мутне кодування UTF-8: надлишкова послідовність — зайві байти в символі."
            if lead == 0xED:
                return "Мутне кодування UTF-8: сурогат UTF-16 сюди не тягни."
            if lead == 0xF4:
                return "Мутне кодування UTF-8: кодова точка вища за U+10FFFF — це вже за межами Unicode."
        return "Мутне кодування UTF-8: послідовність обірвалась, символ не дописаний."

    # ------------------------------------------------- token state machine

    def feed(self, cp, offset):
        """Process one scalar beginning at byte offset; None denotes EOF."""
        while True:
            state = self.state

            if state == START:
                column = offset - self.line_start + 1
                if cp is None:
                    self.tokens.append(Token(EOF, "", self.line, column))
                    return
                if cp == SPACE or cp == TAB:
                    return
                if cp == LF:
                    self.tokens.append(Token(NEWLINE, NEWLINE_TEXT, self.line, column))
                    self.new_line(offset + 1)
                    return
                if cp == CR:
                    self.begin(AFTER_CR, offset)
                    return
                if is_word_start(cp):
                    self.begin(WORD, offset)
                    self.after_letter = is_letter(cp)
                    return
                if is_digit(cp):
                    self.begin(NUMBER, offset)
                    return
                if cp == LEFT_PAREN:
                    self.tokens.append(Token(LPAREN, "(", self.line, column))
                    return
                if cp == RIGHT_PAREN:
                    self.tokens.append(Token(RPAREN, ")", self.line, column))
                    return
                if cp in APOSTROPHES:
                    raise self.error_at(offset, APOSTROPHE_MESSAGE)
                if cp == BYTE_ORDER_MARK and offset == 0:
                    raise self.error_at(offset, "BOM (U+FEFF) тут нікому не треба: збережи файл як UTF-8 без BOM.")
                raise self.error_at(offset, f"Шо за символ {describe_character(cp)}? Такого в нашому базарі нема.")

            if state == WORD:
                if cp is not None and is_word_part(cp):
                    self.after_letter = is_letter(cp)
                    return
                if cp is not None and cp in APOSTROPHES:
                    if not self.after_letter:
                        raise self.error_at(offset, APOSTROPHE_MESSAGE)
                    self.state = APOSTROPHE
                    self.apostrophe_offset = offset
                    return
                text = self.data[self.token_start:offset].decode("utf-8")
                if text == COMMENT_WORD:
                    if cp == COLON:
                        self.state = COMMENT
                        return
                    raise LexError(self.token_line, self.token_column,
                                   "«Чутки» без двокрапки не канають: пиши «чутки:» без пробілу перед «:».")
                kind = KEYWORD if text in KEYWORDS else IDENT
                self.emit(kind, text)
                continue                     # reconsider cp in the START state

            if state == APOSTROPHE:
                # An apostrophe stays inside a word only between two letters: з'їзд.
                if cp is not None and is_letter(cp):
                    self.state = WORD
                    self.after_letter = True
                    return
                raise self.error_at(self.apostrophe_offset, APOSTROPHE_MESSAGE)

            if state == NUMBER:
                if cp is not None and is_digit(cp):
                    return
                if cp is not None and is_word_start(cp):
                    raise LexError(self.token_line, self.token_column,
                                   "Число з буквами? Не мути: після цифр букви й '_' не ліплять.")
                digits = self.data[self.token_start:offset].decode("ascii")
                if exceeds_i64_magnitude(digits):
                    raise LexError(self.token_line, self.token_column,
                                   f"Число завелике, шеф: у Базарі найбільше ціле — {I64_MAX} "
                                   f"(межа «крупняк»), більше ніде не влізе.")
                self.emit(INTEGER, digits)
                continue

            if state == COMMENT:
                if cp is None or cp == LF or cp == CR:
                    self.state = START
                    continue                 # the newline still produces a token
                return

            # state == AFTER_CR
            if cp != LF:
                raise LexError(self.token_line, self.token_column,
                               "Самотній CR не канає: після нього має бути LF. Лишай LF або CRLF.")
            self.tokens.append(Token(NEWLINE, NEWLINE_TEXT, self.token_line, self.token_column))
            self.new_line(offset + 1)
            self.state = START
            return

    def begin(self, state, offset):
        self.state = state
        self.token_start = offset
        self.token_line = self.line
        self.token_column = offset - self.line_start + 1

    def emit(self, kind, text):
        self.tokens.append(Token(kind, text, self.token_line, self.token_column))
        self.state = START

    def new_line(self, next_offset):
        self.line += 1
        self.line_start = next_offset

    def error_at(self, offset, message):
        return LexError(self.line, offset - self.line_start + 1, message)


def lex(data: bytes) -> list[Token]:
    """Tokenize the complete input, always ending with one EOF token."""
    return Lexer(data).run()


def write_text(stream, text):
    """Write UTF-8 bytes directly, independently of locale.

    surrogateescape preserves paths containing undecodable bytes in
    error messages."""
    stream.buffer.write(text.encode("utf-8", "surrogateescape"))
    stream.flush()


OS_ERROR_TEXT = {
    errno.ENOENT: "такого файлу нема",
    errno.EACCES: "доступу нема",
    errno.EPERM: "доступу нема",
    errno.EISDIR: "це тека, а не файл",
    errno.ENOTDIR: "десь у шляху замість теки лежить файл",
    errno.ELOOP: "забагато символічних посилань",
    errno.ENAMETOOLONG: "задовге ім'я",
}


def compilation_error_line(error):
    """Format the single stderr line for a lexical or syntax error."""
    return f"compilation error: line {error.line}:{error.column}: {error.message}\n"


def describe_os_error(error):
    """Localized OS error descriptions, independent of system language."""
    return OS_ERROR_TEXT.get(error.errno) or f"помилка системи (errno {error.errno})"


def main():
    if len(sys.argv) != 2:
        write_text(sys.stderr, f"Запускай так: {sys.argv[0]} <input.bazar>\n")
        return 2
    try:
        tokens = lex(Path(sys.argv[1]).read_bytes())
    except LexError as error:
        write_text(sys.stderr, compilation_error_line(error))
        return 1
    except OSError as error:
        write_text(sys.stderr, f"Файл '{sys.argv[1]}' не читається: {describe_os_error(error)}. Перевір шлях і доступ.\n")
        return 2
    for token in tokens:
        write_text(sys.stdout, f"{token.line}:{token.column} {token.kind:8} {token.text!r}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
