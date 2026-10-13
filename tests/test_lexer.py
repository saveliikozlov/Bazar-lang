"""Byte-oriented lexer unit tests: UTF-8 validation, tokens, and positions."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lexer import (  # noqa: E402
    EOF, IDENT, INTEGER, KEYWORD, KEYWORDS, LPAREN, NEWLINE, NEWLINE_TEXT, RPAREN,
    LexError, Token, lex,
)

NEW_KEYWORDS = ("желєзобетонно зуб даю мутна тєма тіпа це дрібняк крупняк базар перевзувся тепер базарь "
                "всьо розходимось якшо реально а нє отакої гон або і ше рівно не більше "
                "менше плюс мінус на ділити").split()

# Former Russian vocabulary absent from the new keywords is deliberately
# retained here to verify that these words are now ordinary identifiers.
FORMER_ONLY_WORDS = ("мутная тема типа это мелочь переобулся теперь всё расходимся если иначе "
                     "конец базара либо ещё и ровно больше меньше минус делить слухи").split()

UKRAINIAN_LETTERS = "ІіЇїЄєҐґ"


def kinds(data):
    return [token.kind for token in lex(data)]


class Utf8ValidationTest(unittest.TestCase):
    def assert_error(self, data, line, column, fragment):
        with self.assertRaises(LexError) as context:
            lex(data)
        error = context.exception
        self.assertEqual((error.line, error.column), (line, column))
        self.assertIn(fragment, error.message)

    def test_rejects_invalid_bytes_inside_comments(self):
        prefix = "чутки: ".encode()          # 12 bytes; invalid byte at column 13
        cases = {
            b"\x80": "байт продовження",
            b"\xc0\xaf": "надлишкова",
            b"\xc1\xbf": "надлишкова",
            b"\xe0\x80\xaf": "надлишкова",
            b"\xf0\x80\x80\xaf": "надлишкова",
            b"\xed\xa0\x80": "сурогат",
            b"\xed\xbf\xbf": "сурогат",
            b"\xf4\x90\x80\x80": "вища за U+10FFFF",
            b"\xf5\x80\x80\x80": "тут не місце",
            b"\xff": "тут не місце",
            b"\xd0\x41": "обірвалась",
            b"\xe2\x82": "файл скінчився",
        }
        for bad, fragment in cases.items():
            with self.subTest(bad=bad):
                self.assert_error(prefix + bad, 1, 13, fragment)

    def test_accepts_boundary_scalar_values_in_comments(self):
        for good in ("\u0080", "߿", "ࠀ", "퟿", "", "￿",
                     "\U00010000", "\U0010ffff", "😎"):
            with self.subTest(good=good):
                self.assertEqual(kinds(("чутки:" + good).encode()), [EOF])

    def test_invalid_bytes_after_ukrainian_letters_use_byte_columns(self):
        # ґї occupies 4 bytes, space 1; invalid byte at column 6.
        self.assert_error("ґї ".encode() + b"\xff", 1, 6, "тут не місце")
        self.assert_error("ґ".encode() + b"\xd1", 1, 3, "файл скінчився")

    def test_rejects_byte_order_mark(self):
        self.assert_error(b"\xef\xbb\xbf\xd0\xb1", 1, 1, "BOM")

    def test_byte_order_mark_later_is_an_ordinary_bad_character(self):
        self.assert_error(b"x \xef\xbb\xbf", 1, 3, "U+FEFF")

    def test_lone_cr_is_rejected_also_inside_comment(self):
        self.assert_error("чутки: a\rb\n".encode(), 1, 14, "Самотній CR")
        self.assert_error(b"x\r", 1, 2, "Самотній CR")

    def test_error_position_after_cyrillic_is_byte_based(self):
        # ж occupies 2 bytes, so '+' is at byte column 4.
        self.assert_error("ж +".encode(), 1, 4, "'+'")


class TokenTest(unittest.TestCase):
    def test_token_positions_are_byte_columns(self):
        tokens = lex("\tзуб  даю ж\n  (12)\r\nx".encode())
        self.assertEqual(tokens, [
            Token(KEYWORD, "зуб", 1, 2),
            Token(KEYWORD, "даю", 1, 10),
            Token(IDENT, "ж", 1, 17),
            Token(NEWLINE, NEWLINE_TEXT, 1, 19),
            Token(LPAREN, "(", 2, 3),
            Token(INTEGER, "12", 2, 4),
            Token(RPAREN, ")", 2, 6),
            Token(NEWLINE, NEWLINE_TEXT, 2, 7),     # CR from CRLF
            Token(IDENT, "x", 3, 1),
            Token(EOF, "", 3, 2),
        ])

    def test_new_phrase_words_are_positioned_by_bytes(self):
        tokens = lex("а нє\nі ше ґ".encode())
        self.assertEqual(tokens[:2], [Token(KEYWORD, "а", 1, 1), Token(KEYWORD, "нє", 1, 4)])
        self.assertEqual(tokens[3:], [Token(KEYWORD, "і", 2, 1), Token(KEYWORD, "ше", 2, 4),
                                      Token(IDENT, "ґ", 2, 9), Token(EOF, "", 2, 11)])

    def test_eof_position(self):
        self.assertEqual(lex(b""), [Token(EOF, "", 1, 1)])
        self.assertEqual(lex(b"\n")[-1], Token(EOF, "", 2, 1))
        self.assertEqual(lex(b"\r\n")[-1], Token(EOF, "", 2, 1))
        self.assertEqual(lex("чутки: 😎".encode())[-1], Token(EOF, "", 1, 17))
        self.assertEqual(lex("їє  ".encode())[-1], Token(EOF, "", 1, 7))

    def test_comment_is_skipped_but_newline_kept(self):
        self.assertEqual(kinds("x чутки: y\n".encode()), [IDENT, NEWLINE, EOF])
        self.assertEqual(kinds("чутки:\r\n".encode()), [NEWLINE, EOF])

    def test_comment_marker_requires_whole_word_and_colon(self):
        for source in ("чутки :", "чутки", "чутки\n", "чутки це"):
            with self.subTest(source=source):
                with self.assertRaises(LexError):
                    lex(source.encode())
        with self.assertRaises(LexError) as context:
            lex("aчутки: x".encode())
        self.assertEqual(context.exception.column, 12)       # colon
        with self.assertRaises(LexError) as context:
            lex("Чутки: x".encode())                          # case-sensitive
        self.assertEqual(context.exception.column, 11)
        self.assertEqual(lex("чутки2".encode())[0], Token(IDENT, "чутки2", 1, 1))

    def test_former_comment_word_is_not_a_comment_any_more(self):
        # The former keyword is an identifier; a following colon is unexpected.
        with self.assertRaises(LexError) as context:
            lex("слухи: x".encode())
        self.assertEqual(context.exception.column, 11)
        self.assertEqual(lex("слухи".encode())[0], Token(IDENT, "слухи", 1, 1))

    def test_every_new_reserved_word_is_a_keyword(self):
        self.assertEqual(KEYWORDS, frozenset(NEW_KEYWORDS))
        for word in NEW_KEYWORDS:
            with self.subTest(word=word):
                self.assertEqual(lex(word.encode())[0], Token(KEYWORD, word, 1, 1))

    def test_every_word_of_a_phrase_is_reserved_separately(self):
        for word in ("а", "нє", "і", "ше", "даю", "тєма", "розходимось", "отакої"):
            with self.subTest(word=word):
                self.assertIn(word, KEYWORDS)

    def test_former_only_words_are_ordinary_identifiers(self):
        for word in FORMER_ONLY_WORDS:
            with self.subTest(word=word):
                self.assertEqual(lex(word.encode())[0], Token(IDENT, word, 1, 1))

    def test_whole_word_is_read_before_keyword_lookup(self):
        for word in ("дрібняк_2", "базарний", "наш", "зуби", "якшоЖ", "Якшо", "отакоїж",
                     "ашка", "нєт", "іше", "ше2", "а1", "_і", "всі", "Отакої", "не_рівно"):
            with self.subTest(word=word):
                self.assertEqual(lex(word.encode())[0], Token(IDENT, word, 1, 1))

    def test_latin_lookalike_is_not_a_keyword(self):
        self.assertEqual(lex("тіпа".encode())[0].kind, KEYWORD)
        self.assertEqual(lex("тіпa".encode())[0], Token(IDENT, "тіпa", 1, 1))   # Latin a
        self.assertEqual(lex("a".encode())[0].kind, IDENT)                       # Latin a
        self.assertEqual(lex("а".encode())[0].kind, KEYWORD)                     # Cyrillic а

    def test_every_ukrainian_letter_is_a_word_letter_in_both_cases(self):
        for letter in UKRAINIAN_LETTERS:
            for text in (f"x{letter}y", f"{letter}{letter}", f"_{letter}9"):
                with self.subTest(text=text):
                    self.assertEqual(lex(text.encode())[0], Token(IDENT, text, 1, 1))
            if letter != "і":                      # standalone і is a keyword
                self.assertEqual(lex(letter.encode())[0], Token(IDENT, letter, 1, 1))
        self.assertEqual(lex("і".encode())[0], Token(KEYWORD, "і", 1, 1))

    def test_previous_cyrillic_letters_are_still_word_letters(self):
        every_letter = "".join(chr(code) for code in range(0x410, 0x450)) + "Ёё"
        self.assertEqual(lex(every_letter.encode())[0], Token(IDENT, every_letter, 1, 1))

    def test_identifier_alphabet_allows_mixed_scripts(self):
        self.assertEqual(lex("Ab_9ЯяЁёІіЇїЄєҐґ".encode())[0],
                         Token(IDENT, "Ab_9ЯяЁёІіЇїЄєҐґ", 1, 1))
        self.assertEqual(lex("кіт_cat".encode())[0], Token(IDENT, "кіт_cat", 1, 1))

    def test_other_letters_are_errors(self):
        for bad in ("љ", "Љ", "ў", "ӂ", "é", "ß", "α", "١", "’"):
            with self.subTest(bad=bad):
                with self.assertRaises(LexError) as context:
                    lex(("x" + bad + "y").encode())
                self.assertEqual(context.exception.column, 2)

    def test_apostrophe_between_letters_is_part_of_identifier(self):
        for name in ("з'їзд", "мʼясо", "п'ять_2", "O'Neil", "а'б"):
            with self.subTest(name=name):
                self.assertEqual(lex(name.encode())[0], Token(IDENT, name, 1, 1))
        # A complete word is classified, so a keyword before an apostrophe is not reserved.
        self.assertEqual(lex("на'ш".encode())[0].kind, IDENT)

    def test_misplaced_apostrophes_are_errors(self):
        # (source, column of the offending apostrophe)
        for source, column in (("'а", 1), ("ʼа", 1), ("м'", 3), ("м' я", 3), ("м''я", 3),
                               ("x1'y", 3), ("_'a", 2), ("м'1", 3), ("м'_", 3), ("1'а", 2)):
            with self.subTest(source=source):
                with self.assertRaises(LexError) as context:
                    lex(source.encode())
                self.assertEqual(context.exception.column, column)

    def test_no_unicode_normalisation(self):
        # Precomposed ї is allowed; і followed by a combining diaeresis is not.
        self.assertEqual(lex("ї".encode())[0].kind, IDENT)
        with self.assertRaises(LexError):
            lex("ї".encode())

    def test_integers(self):
        self.assertEqual(lex(b"007")[0], Token(INTEGER, "007", 1, 1))
        self.assertEqual(kinds(b"1(2)"), [INTEGER, LPAREN, INTEGER, RPAREN, EOF])
        for bad in ("12abc", "12_3", "0x1F", "10L", "5ж", "5ї", "5ґ"):
            with self.subTest(bad=bad):
                with self.assertRaises(LexError) as context:
                    lex(("  " + bad).encode())
                self.assertEqual(context.exception.column, 3)    # first digit

    def test_digits_after_letters_are_part_of_identifier(self):
        self.assertEqual(lex(b"x12")[0], Token(IDENT, "x12", 1, 1))

    def test_rejects_other_characters(self):
        for bad in "+-*/=!<>;:,.\"'{}[]\x00\x0b\x0c\x7f":
            with self.subTest(bad=bad):
                with self.assertRaises(LexError):
                    lex(bad.encode())


if __name__ == "__main__":
    unittest.main()
