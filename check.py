"""Run every source fixture through the real CLI and compare frozen expectations.

    python3 check.py

tests/valid/NAME.bazar: --ast exits 0, exact NAME.ast on stdout, empty stderr.
    These are front-end fixtures: syntactically valid, and some of the
    Stage 1 ones deliberately use names that were never declared.
tests/invalid/NAME.bazar: compiling exits 1, empty stdout, exact single-line
    NAME.err on stderr, and no output file. Lexical, syntax, and semantic
    errors all go through the full compiler.
examples/NAME.bazar: compiling exits 0 with empty stderr.
tests/run/NAME.bazar: end to end. The program is compiled to NAME.ll, run
    with lli (or built with llc and clang when lli is missing), and its stdout
    must equal NAME.expected exactly. NAME.in, when present, is its standard
    input. Without NAME.error the program must exit 0 with empty stderr;
    with it, the program must exit 1 and print exactly NAME.error to stderr
    (a run-time overflow or division by zero).

LLVM tools are looked up in $LLVM_BIN, then on PATH, then in the Homebrew
folders /opt/homebrew/opt/llvm/bin and /usr/local/opt/llvm/bin.

Expectations are never written or regenerated. CLI invocations run from a
temporary directory, independently of the current working directory.
Orphan .ast/.err files without matching .bazar sources also fail. Exit 0
requires every check to pass. Output is UTF-8 regardless of locale.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from lexer import write_text

ROOT = Path(__file__).resolve().parent
COMPILER = ROOT / "compiler.py"


def show(data):
    return data.decode("utf-8", "replace").strip()


def run_compiler(source, cwd):
    return subprocess.run([sys.executable, str(COMPILER), "--ast", str(source)],
                          capture_output=True, cwd=cwd, timeout=60)


def run_compile(source, cwd):
    """Compile source to cwd/out.ll; return the result and whether out.ll exists."""
    output = Path(cwd) / "out.ll"
    output.unlink(missing_ok=True)
    result = subprocess.run([sys.executable, str(COMPILER), str(source), str(output)],
                            capture_output=True, cwd=cwd, timeout=60)
    return result, output.exists()


def check_valid(source, cwd):
    expected_file = source.with_suffix(".ast")
    if not expected_file.exists():
        return f"нема очікуваного файлу {expected_file.name}"
    expected = expected_file.read_bytes()
    result = run_compiler(source, cwd)
    if result.returncode != 0:
        return f"код виходу {result.returncode}, stderr: {show(result.stderr)}"
    if result.stderr:
        return f"зайвий stderr: {show(result.stderr)}"
    if result.stdout != expected:
        return f"AST не збігається з {expected_file.name}" + first_difference(expected, result.stdout)
    return None


def check_invalid(source, cwd):
    expected_file = source.with_suffix(".err")
    if not expected_file.exists():
        return f"нема очікуваного файлу {expected_file.name}"
    expected = expected_file.read_bytes()
    result, wrote_output = run_compile(source, cwd)
    if result.returncode != 1:
        return f"код виходу {result.returncode}, а чекали 1"
    if result.stdout:
        return "stdout не порожній"
    if wrote_output:
        return "після помилки лишився вихідний файл"
    if result.stderr != expected:
        return f"чекали {show(expected)!r}, а отримали {show(result.stderr)!r}"
    return None


def check_example(source, cwd):
    result, _ = run_compile(source, cwd)
    if result.returncode != 0 or result.stderr:
        return f"код виходу {result.returncode}, stderr: {show(result.stderr)}"
    return None


LLVM_FOLDERS = ("/opt/homebrew/opt/llvm/bin", "/usr/local/opt/llvm/bin")


def find_tool(name):
    folders = [os.environ["LLVM_BIN"]] if os.environ.get("LLVM_BIN") else []
    for folder in folders:
        candidate = Path(folder) / name
        if candidate.exists():
            return str(candidate)
    found = shutil.which(name)
    if found:
        return found
    for folder in LLVM_FOLDERS:
        candidate = Path(folder) / name
        if candidate.exists():
            return str(candidate)
    return None


def run_program(module, stdin, cwd):
    """Run a compiled .ll module; return the CompletedProcess or a problem string."""
    lli = find_tool("lli")
    if lli:
        return subprocess.run([lli, str(module)], stdin=stdin, capture_output=True, cwd=cwd, timeout=60)
    llc, clang = find_tool("llc"), find_tool("clang")
    if not (llc and clang):
        return "нема ні lli, ні llc з clang: задай LLVM_BIN"
    obj, binary = Path(cwd) / "program.o", Path(cwd) / "program"
    for command in ([llc, "-filetype=obj", str(module), "-o", str(obj)], [clang, str(obj), "-o", str(binary)]):
        built = subprocess.run(command, capture_output=True, timeout=60)
        if built.returncode != 0:
            return f"{Path(command[0]).name} впав: {show(built.stderr)}"
    return subprocess.run([str(binary)], stdin=stdin, capture_output=True, cwd=cwd, timeout=60)


def check_run(source, cwd):
    expected_file = source.with_suffix(".expected")
    if not expected_file.exists():
        return f"нема очікуваного файлу {expected_file.name}"
    result, wrote_output = run_compile(source, cwd)
    if result.returncode != 0 or result.stderr:
        return f"не скомпілювалось, код {result.returncode}, stderr: {show(result.stderr)}"
    if not wrote_output:
        return "компілятор не записав .ll"
    input_file = source.with_suffix(".in")
    with open(input_file if input_file.exists() else os.devnull, "rb") as stdin:
        run = run_program(Path(cwd) / "out.ll", stdin, cwd)
    if isinstance(run, str):
        return run
    error_file = source.with_suffix(".error")
    expected_code = 1 if error_file.exists() else 0
    if run.returncode != expected_code:
        return f"програма вийшла з кодом {run.returncode}, а чекали {expected_code}, stderr: {show(run.stderr)}"
    expected_error = error_file.read_bytes() if error_file.exists() else b""
    if run.stderr != expected_error:
        return f"stderr: чекали {show(expected_error)!r}, а отримали {show(run.stderr)!r}"
    expected = expected_file.read_bytes()
    if run.stdout != expected:
        return f"вивід не збігається з {expected_file.name}" + first_difference(expected, run.stdout)
    return None


def first_difference(expected, actual):
    expected_lines = expected.decode("utf-8", "replace").split("\n")
    actual_lines = actual.decode("utf-8", "replace").split("\n")
    for number, (want, got) in enumerate(zip(expected_lines, actual_lines), start=1):
        if want != got:
            return f" у рядку {number}: чекали {want!r}, а отримали {got!r}"
    return f": чекали рядків {len(expected_lines)}, а отримали {len(actual_lines)}"


def orphans(folder, suffix):
    """Find expectation files without matching source fixtures."""
    directory = ROOT / folder
    return [path for path in sorted(directory.glob("*" + suffix))
            if not path.with_suffix(".bazar").exists()]


def main():
    groups = (
        ("tests/valid", check_valid, ".ast"),
        ("tests/invalid", check_invalid, ".err"),
        ("examples", check_example, None),
        ("tests/run", check_run, (".expected", ".in", ".error")),
    )
    total = failures = 0

    def report(line):
        write_text(sys.stdout, line + "\n")

    with tempfile.TemporaryDirectory() as cwd:
        for folder, check, suffix in groups:
            sources = sorted((ROOT / folder).glob("*.bazar"))
            if not sources:
                report(f"ПРОВАЛ {folder}: жодного *.bazar не знайшов, шо перевіряти?")
                failures += 1
                continue
            for source in sources:
                total += 1
                problem = check(source, cwd)
                name = source.relative_to(ROOT).as_posix()
                if problem is None:
                    report(f"PASS   {name}")
                else:
                    failures += 1
                    report(f"ПРОВАЛ {name}: {problem}")
            suffixes = suffix if isinstance(suffix, tuple) else (suffix,) if suffix else ()
            for orphan in (o for s in suffixes for o in orphans(folder, s)):
                total += 1
                failures += 1
                report(f"ПРОВАЛ {orphan.relative_to(ROOT).as_posix()}: файл-сирота, джерела .bazar для нього нема")
    report(f"\nPassed {total - failures} of {total}; failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
