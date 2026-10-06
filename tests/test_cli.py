"""End-to-end compiler.py --ast tests for output streams and exit codes."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from diagnostics import SPICY_ENV, STATE_ENV  # noqa: E402
COMPILER = ROOT / "compiler.py"
LEXER = ROOT / "lexer.py"


class CliTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def run_script(self, script, *arguments, env=None):
        """Always isolate failure state, even when the environment specifies a path."""
        env = dict(os.environ if env is None else env)
        env[STATE_ENV] = str(Path(self.directory.name) / "failures.sqlite3")
        env.pop(SPICY_ENV, None)
        return subprocess.run([sys.executable, str(script), *arguments],
                              capture_output=True, cwd=self.directory.name, timeout=60, env=env)

    def run_cli(self, *arguments, env=None):
        return self.run_script(COMPILER, *arguments, env=env)

    def ascii_environment(self):
        """Build an environment where Python would otherwise use ASCII output."""
        env = dict(os.environ)
        env.update(PYTHONIOENCODING="ascii", LC_ALL="C", LANG="C")
        env.pop("PYTHONUTF8", None)
        return env

    def write(self, name, data):
        path = Path(self.directory.name) / name
        path.write_bytes(data)
        return str(path)

    def assert_one_line_error(self, result, code):
        self.assertEqual(result.returncode, code)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr.count(b"\n"), 1)
        self.assertTrue(result.stderr.endswith(b"\n"))
        self.assertNotIn(b"Traceback", result.stderr)

    def test_success_prints_only_the_tree(self):
        path = self.write("input.txt", "базарь 1".encode())
        result = self.run_cli("--ast", path)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(result.stdout.decode(),
                         "ProgramNode line=1 column=1\n  PrintNode line=1 column=1\n"
                         "    value:\n      IntegerNode line=1 column=14 value=1\n")

    def test_error_is_one_line_on_stderr(self):
        path = self.write("bad.bazar", "зуб даю x тіпа дрібняк це\n".encode())
        result = self.run_cli("--ast", path)
        self.assert_one_line_error(result, 1)
        self.assertEqual(result.stderr.decode(),
                         "compilation error: line 1:45: Де значення? Тут має бути число, "
                         "«реально», «гон», ім'я або «(», а не кінець рядка.\n")

    def test_lexical_error_in_raw_bytes(self):
        path = self.write("bad.bazar", b"\xd0\xb1 \xc0\x80\n")
        result = self.run_cli("--ast", path)
        self.assert_one_line_error(result, 1)
        self.assertTrue(result.stderr.startswith("compilation error: line 1:4: Мутне кодування UTF-8".encode()))

    def test_old_russian_phrase_is_rejected_with_one_line(self):
        path = self.write("old.bazar", "если реально реально\n    базарь 1\nконец базара\n".encode())
        result = self.run_cli("--ast", path)
        self.assert_one_line_error(result, 1)
        self.assertTrue(result.stderr.startswith("compilation error: line 1:1: ".encode()))

    def test_usage_errors(self):
        for arguments in ((), ("x.bazar",), ("--tokens", "x.bazar"), ("--ast",),
                          ("--ast", "a", "b")):
            with self.subTest(arguments=arguments):
                result = self.run_cli(*arguments)
                self.assert_one_line_error(result, 2)
                self.assertIn("Запускай так".encode(), result.stderr)

    def test_file_errors_are_localized(self):
        cases = (("missing.bazar", "такого файлу нема"),
                 (self.directory.name, "це тека, а не файл"))
        for argument, fragment in cases:
            with self.subTest(argument=argument):
                result = self.run_cli("--ast", argument)
                self.assert_one_line_error(result, 2)
                self.assertIn("не читається".encode(), result.stderr)
                self.assertIn(fragment.encode(), result.stderr)
                self.assertNotIn(b"No such file", result.stderr)
                self.assertNotIn(b"directory", result.stderr)

    def test_utf8_output_does_not_depend_on_the_environment(self):
        env = self.ascii_environment()
        valid = self.write("ґанок.bazar", "зуб даю їжак тіпа дрібняк це 1\n".encode())
        result = self.run_cli("--ast", valid, env=env)
        self.assertEqual(result.returncode, 0)
        self.assertIn("name=їжак".encode(), result.stdout)
        bad = self.write("bad.bazar", "базарь ;\n".encode())
        result = self.run_cli("--ast", bad, env=env)
        self.assert_one_line_error(result, 1)
        self.assertEqual(result.stderr.decode("utf-8"),
                         "compilation error: line 1:14: Шо за символ ';'? Такого в нашому базарі нема.\n")
        result = self.run_cli("--ast", "нема_такого_файлу.bazar", env=env)
        self.assert_one_line_error(result, 2)
        self.assertIn("нема_такого_файлу.bazar".encode(), result.stderr)
        self.assertIn("такого файлу нема".encode(), result.stderr)
        result = self.run_cli(env=env)
        self.assert_one_line_error(result, 2)
        result.stderr.decode("utf-8")

    def test_lexer_script_has_the_same_guarantees(self):
        env = self.ascii_environment()
        path = self.write("tokens.bazar", "ґанок\n".encode())
        result = self.run_script(LEXER, path, env=env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.decode("utf-8").splitlines()[0], "1:1 ident    'ґанок'")
        for arguments, code in ((("missing.bazar",), 2), ((), 2)):
            result = self.run_script(LEXER, *arguments, env=env)
            self.assert_one_line_error(result, code)
            result.stderr.decode("utf-8")
        bad = self.write("bad.bazar", "$\n".encode())
        result = self.run_script(LEXER, bad, env=env)
        self.assert_one_line_error(result, 1)
        self.assertTrue(result.stderr.startswith(b"compilation error: line 1:1: "))


if __name__ == "__main__":
    unittest.main()
