"""Usefulness algorithm unit tests: missing cases, unreachable rows, and witnesses."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bazar_types import BOOL, I32, OptionType, ResultType  # noqa: E402
from exhaustiveness import Alt, Con, Wild, show, useful  # noqa: E402

W = Wild()
NONE = Con(("none",))


def some(pattern):
    return Con(("some",), (pattern,))


def ok(pattern):
    return Con(("ok",), (pattern,))


def err(pattern):
    return Con(("err",), (pattern,))


def boolean(value):
    return Con(("bool", value))


def integer(value):
    return Con(("int", value))


def missing(t, *patterns):
    """The first value no pattern matches, as text, or None when they cover everything."""
    witness = useful([(pattern,) for pattern in patterns], (W,), [t], {})
    return None if witness is None else show(witness[0])


NESTED = OptionType(ResultType(I32, BOOL))


class ExhaustivenessTest(unittest.TestCase):
    def test_complete_matches(self):
        self.assertIsNone(missing(NESTED, some(W), NONE))
        self.assertIsNone(missing(NESTED, some(ok(W)), some(err(Alt((boolean(True), boolean(False))))), NONE))
        self.assertIsNone(missing(BOOL, boolean(False), boolean(True)))
        self.assertIsNone(missing(I32, integer(0), W))

    def test_witnesses_name_a_missing_value(self):
        self.assertEqual(missing(NESTED, NONE), "шось(_)")
        self.assertEqual(missing(NESTED, some(ok(W)), NONE), "шось(облом(_))")
        self.assertEqual(missing(NESTED, some(ok(W)), some(err(boolean(True))), NONE), "шось(облом(гон))")
        self.assertEqual(missing(BOOL, boolean(True)), "гон")

    def test_integers_need_a_wildcard(self):
        self.assertEqual(missing(I32, integer(0), integer(1)), "2")
        self.assertEqual(missing(I32), "_")

    def test_unreachable_rows(self):
        self.assertIsNone(useful([(some(W),)], (some(ok(integer(5))),), [NESTED], {}))
        self.assertIsNone(useful([(W,)], (NONE,), [NESTED], {}))
        self.assertIsNotNone(useful([(some(ok(W)),)], (some(err(W)),), [NESTED], {}))

    def test_show_spells_patterns_as_written(self):
        self.assertEqual(show(Con(("struct", "Точка"), (integer(-3), W))), "Точка(мінус 3, _)")
        self.assertEqual(show(Alt((NONE, some(W)))), "нема або шось(_)")


if __name__ == "__main__":
    unittest.main()
