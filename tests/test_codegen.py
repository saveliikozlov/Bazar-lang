"""Code generation unit tests: where slots live, and the order of output and run-time errors."""

from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parser import parse_program  # noqa: E402
from semantic import analyze  # noqa: E402

try:
    from codegen import generate
except ImportError:                          # llvmlite is missing
    generate = None


def compile_source(source):
    program = parse_program(source.encode())
    return generate(program, analyze(program))


def function_body(ir_text, name):
    match = re.search(r'define [^\n]*@"' + re.escape(name) + r'"\([^\n]*\n(.*?)\n}', ir_text, re.S)
    return match.group(1)


@unittest.skipIf(generate is None, "llvmlite is not installed")
class SlotTest(unittest.TestCase):
    SOURCE = ("маю дєло ф(к тіпа дрібняк) на виході може дрібняк\n"
              "    мутна тєма великий тіпа [дрібняк; 2000] це [всюди 0]\n"
              "    зуб даю малий тіпа [дрібняк; 4] це [всюди 0]\n"
              "    якшо реально к рівно 0\n        тримай нема\n    отакої\n"
              "    зуб даю з тіпа може дрібняк це шось(к)\n"
              "    перевзувся великий[0] тепер з? плюс малий[0]\n"
              "    тримай шось(1)\nпорішали\nбазарь ф(1)")

    def test_large_slots_are_on_the_heap_and_freed_before_every_return(self):
        body = function_body(compile_source(self.SOURCE), "bz.ф")
        self.assertEqual(body.count('call i8* @"bazar.alloc"'), 1)        # великий: 8000 bytes
        self.assertIn("alloca [4 x i32]", body)                           # малий stays on the stack
        returns = [i for i, line in enumerate(body.splitlines()) if line.strip().startswith("ret")]
        self.assertEqual(len(returns), 3)                                 # тримай нема, ?, тримай шось
        lines = body.splitlines()
        for index in returns:
            self.assertIn('call void @"free"', lines[index - 1])

    def test_small_programs_need_no_heap(self):
        ir_text = compile_source("зуб даю м тіпа [дрібняк; 3] це [1, 2, 3]\nбазарь м")
        self.assertNotIn("bazar.alloc", ir_text)
        self.assertNotIn('@"free"', ir_text)


LLI = shutil.which("lli")


@unittest.skipIf(generate is None or LLI is None, "llvmlite or lli is not installed")
class RunTimeErrorOrderTest(unittest.TestCase):
    def test_printed_output_comes_before_the_error(self):
        source = 'базарь "спершу це"\nзуб даю н тіпа дрібняк це ану кажи\nбазарь 1 ділити на н\n'
        with tempfile.TemporaryDirectory() as folder:
            module = Path(folder) / "program.ll"
            module.write_text(compile_source(source), encoding="utf-8")
            result = subprocess.run([LLI, str(module)], input=b"0\n", stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, timeout=60)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout.decode("utf-8").splitlines(),
                         ["спершу це", "помилка виконання: line 3:16: ділити на нуль не можна"])


if __name__ == "__main__":
    unittest.main()
