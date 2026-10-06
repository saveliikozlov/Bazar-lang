"""Compilation failure counters: thresholds, persistence, and storage failures."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diagnostics import FINAL_MESSAGE, SPICY_ENV, STATE_ENV  # noqa: E402
from lexer import LexError, lex  # noqa: E402
from parser import CompilationError, parse_program  # noqa: E402

COMPILER = ROOT / "compiler.py"
LEXER = ROOT / "lexer.py"

SYNTAX_SOURCE = "базарь\n".encode()
SYNTAX_ERROR = ("line 1:13: Де значення? Тут має бути число, «реально», «гон», ім'я або «(», "
                "а не кінець рядка.")
LEX_SOURCE = "базарь ;\n".encode()
LEX_ERROR = "line 1:14: Шо за символ ';'? Такого в нашому базарі нема."
SWEAR_ROOTS = ("бля", "хуй", "пізд", "їба")


class CounterTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.state = self.directory / "state" / "failures.sqlite3"
        self.syntax = self.write("syntax.bazar", SYNTAX_SOURCE)
        self.lexical = self.write("lexical.bazar", LEX_SOURCE)

    def write(self, name, data):
        path = self.directory / name
        path.write_bytes(data)
        return str(path)

    def environment(self, state=None, ascii_only=False, spicy=True):
        env = dict(os.environ)
        env[STATE_ENV] = str(state or self.state)
        if spicy:
            env[SPICY_ENV] = "1"
        else:
            env.pop(SPICY_ENV, None)
        if ascii_only:
            env.update(PYTHONIOENCODING="ascii", LC_ALL="C", LANG="C")
            env.pop("PYTHONUTF8", None)
        return env

    def run_script(self, script, *arguments, **options):
        return subprocess.run([sys.executable, str(script), *arguments], capture_output=True,
                              cwd=str(self.directory), timeout=60, env=self.environment(**options))

    def compile(self, path, **options):
        return self.run_script(COMPILER, "--ast", path, **options)

    def seed(self, lifetime, counter):
        self.state.parent.mkdir(exist_ok=True)
        with sqlite3.connect(str(self.state)) as connection:
            connection.execute("CREATE TABLE failures (id INTEGER PRIMARY KEY, "
                               "lifetime_failures INTEGER NOT NULL, message_counter INTEGER NOT NULL)")
            connection.execute("INSERT INTO failures VALUES (1, ?, ?)", (lifetime, counter))
        connection.close()

    def stored(self):
        connection = sqlite3.connect(str(self.state))
        try:
            return connection.execute(
                "SELECT lifetime_failures, message_counter FROM failures").fetchall()
        finally:
            connection.close()

    def body(self, result, position):
        """Check output streams and prefix, then return the message body."""
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")
        text = result.stderr.decode("utf-8")
        self.assertEqual(text.count("\n"), 1)
        self.assertTrue(text.endswith("\n"))
        prefix = f"compilation error: {position} "
        self.assertTrue(text.startswith(prefix), text)
        return text[len(prefix):-1]

    def assert_plain(self, result, error=SYNTAX_ERROR):
        self.assertEqual(result.stderr.decode("utf-8"), f"compilation error: {error}\n")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, b"")

    def assert_swear(self, result, error=SYNTAX_ERROR):
        position, message = error.split(": ", 1)
        body = self.body(result, position + ":")
        self.assertTrue(body.endswith(" " + message), body)
        swear = body[:-len(message) - 1]
        self.assertIn("!", swear)
        self.assertTrue(any(root in swear.lower() for root in SWEAR_ROOTS), swear)
        self.assertNotIn("*", swear)

    def assert_final(self, result, error=SYNTAX_ERROR):
        position = error.split(": ", 1)[0]
        self.assertEqual(self.body(result, position + ":"), FINAL_MESSAGE)

    def test_message_counter_boundaries(self):
        cases = (((0, 9), "plain", (1, 10)),
                 ((0, 10), "swear", (1, 9)),
                 ((20, 39), "swear", (21, 38)),
                 ((39, 9), "plain", (40, 10)),
                 ((39, 10), "swear", (40, 9)),
                 ((40, 9), "final", (41, 10)),
                 ((40, 10), "final", (41, 11)),
                 ((41, 0), "final", (42, 1)))
        check = {"plain": self.assert_plain, "swear": self.assert_swear, "final": self.assert_final}
        for saved, tier, after in cases:
            with self.subTest(saved=saved):
                self.state.unlink(missing_ok=True)
                self.seed(*saved)
                check[tier](self.compile(self.syntax))
                self.assertEqual(self.stored(), [after])

    def test_forty_one_failures_from_scratch(self):
        """Compiler/lexer and lexical/syntax failures share one persistent counter."""
        self.assertFalse(self.state.exists())
        runs = ((COMPILER, "--ast", self.syntax, SYNTAX_ERROR),
                (LEXER, self.lexical, LEX_ERROR),
                (COMPILER, "--ast", self.lexical, LEX_ERROR))
        for failure in range(1, 42):
            script, *arguments, error = runs[failure % len(runs)]
            result = self.run_script(script, *arguments)
            with self.subTest(failure=failure):
                if failure == 41:
                    self.assert_final(result, error)
                elif 11 <= failure <= 39 and failure % 2 == 1:
                    self.assert_swear(result, error)
                else:
                    self.assert_plain(result, error)
        self.assertEqual(self.stored(), [(41, 11)])

    def test_final_message_for_every_failure_after_forty(self):
        self.seed(40, 0)
        runs = ((COMPILER, "--ast", self.syntax, SYNTAX_ERROR),
                (COMPILER, "--ast", self.lexical, LEX_ERROR),
                (LEXER, self.lexical, LEX_ERROR))
        for script, *arguments, error in runs:
            with self.subTest(script=script.name, error=error):
                self.assert_final(self.run_script(script, *arguments), error)
        self.assertEqual(self.stored(), [(43, 3)])

    def test_every_tier_is_utf8_in_an_ascii_environment(self):
        for saved, check in (((0, 0), self.assert_plain), ((0, 10), self.assert_swear),
                             ((40, 0), self.assert_final)):
            with self.subTest(saved=saved):
                self.state.unlink(missing_ok=True)
                self.seed(*saved)
                check(self.compile(self.syntax, ascii_only=True))

    def test_success_usage_and_file_errors_do_not_count(self):
        valid = self.write("valid.bazar", "базарь 1\n".encode())
        runs = ((COMPILER, "--ast", valid), (LEXER, valid), (COMPILER,), (LEXER,),
                (COMPILER, "--ast", "missing.bazar"), (LEXER, "missing.bazar"))
        for script, *arguments in runs:
            self.assertIn(self.run_script(script, *arguments).returncode, (0, 2))
        self.assertFalse(self.state.exists())
        self.seed(12, 10)
        for script, *arguments in runs:
            self.run_script(script, *arguments)
        self.assertEqual(self.stored(), [(12, 10)])

    def test_counters_are_disabled_by_default(self):
        self.seed(40, 10)
        for spicy in ("", "0", "yes", None):
            with self.subTest(spicy=spicy):
                env = self.environment(spicy=False)
                if spicy is not None:
                    env[SPICY_ENV] = spicy
                for script, *arguments, error in ((COMPILER, "--ast", self.syntax, SYNTAX_ERROR),
                                                  (LEXER, self.lexical, LEX_ERROR)):
                    result = subprocess.run([sys.executable, str(script), *arguments],
                                            capture_output=True, cwd=str(self.directory),
                                            timeout=60, env=env)
                    self.assert_plain(result, error)
        self.assertEqual(self.stored(), [(40, 10)])

    def test_missing_state_is_created_on_first_failure(self):
        self.assertFalse(self.state.parent.exists())
        self.assert_plain(self.compile(self.syntax))
        self.assertEqual(self.stored(), [(1, 1)])

    def test_broken_state_keeps_the_original_error(self):
        garbage = self.directory / "garbage.sqlite3"
        garbage.write_bytes(b"not a database at all\n" * 100)
        not_a_directory = self.directory / "file"
        not_a_directory.write_bytes(b"")
        for state in (garbage, self.directory, not_a_directory / "failures.sqlite3"):
            with self.subTest(state=state):
                self.assert_plain(self.compile(self.syntax, state=state))
                self.assert_plain(self.run_script(LEXER, self.lexical, state=state), LEX_ERROR)
        self.assertEqual(garbage.read_bytes(), b"not a database at all\n" * 100)

    def test_invalid_values_are_left_alone(self):
        for values in ((-1, 5), (5, -1), ("багато", 5), (5, 2.5), (None, 5)):
            with self.subTest(values=values):
                self.state.unlink(missing_ok=True)
                self.state.parent.mkdir(exist_ok=True)
                connection = sqlite3.connect(str(self.state))
                connection.execute("CREATE TABLE failures (lifetime_failures, message_counter)")
                connection.execute("INSERT INTO failures VALUES (?, ?)", values)
                connection.commit()
                connection.close()
                self.assert_plain(self.compile(self.syntax))
                self.assertEqual(self.stored(), [values])
        for rows in ((), ((1, 1), (2, 2))):
            with self.subTest(rows=rows):
                self.state.unlink()
                connection = sqlite3.connect(str(self.state))
                connection.execute("CREATE TABLE failures (lifetime_failures, message_counter)")
                connection.executemany("INSERT INTO failures VALUES (?, ?)", rows)
                connection.commit()
                connection.close()
                self.assert_plain(self.compile(self.syntax))
                self.assertEqual(self.stored(), list(rows))

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can write anywhere")
    def test_read_only_state_keeps_the_original_error(self):
        self.seed(30, 10)
        self.state.chmod(0o444)
        self.addCleanup(self.state.chmod, 0o644)
        self.assert_plain(self.compile(self.syntax))
        self.assertEqual(self.stored(), [(30, 10)])

    def test_simultaneous_failures_are_all_counted(self):
        self.seed(0, 0)
        processes = [subprocess.Popen([sys.executable, str(COMPILER), "--ast", self.syntax],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      cwd=str(self.directory), env=self.environment())
                     for _ in range(16)]
        outputs = [process.communicate(timeout=60) for process in processes]
        self.assertTrue(all(process.returncode == 1 for process in processes))
        self.assertTrue(all(stdout == b"" for stdout, _ in outputs))
        plain = f"compilation error: {SYNTAX_ERROR}\n".encode()
        # 1..10 ordinary; 11th swears (11 -> 9), followed by 10, 11 -> 9, 10, 11 -> 9, 10.
        self.assertEqual(sum(stderr != plain for _, stderr in outputs), 3)
        self.assertEqual(self.stored(), [(16, 10)])

    def test_library_calls_do_not_touch_the_counter(self):
        previous = os.environ.get(STATE_ENV)
        os.environ[STATE_ENV] = str(self.state)
        self.addCleanup(lambda: os.environ.pop(STATE_ENV) if previous is None
                        else os.environ.__setitem__(STATE_ENV, previous))
        for _ in range(15):
            with self.assertRaises(CompilationError) as caught:
                parse_program(SYNTAX_SOURCE)
            self.assertEqual(str(caught.exception), SYNTAX_ERROR)
            with self.assertRaises(LexError) as caught:
                lex(LEX_SOURCE)
            self.assertEqual(str(caught.exception), LEX_ERROR)
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
