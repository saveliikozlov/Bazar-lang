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
programs/NAME.txt: a real program. Each recorded session, NAME.in or NAME_*.in,
    is the standard input of a native binary built with llc and clang, whose
    stdout must equal the session's .expected exactly, with exit code 0 and
    empty stderr. lli is not used here: the binary is the deliverable.
tests/optimize/NAME.bazar: --optimize --ast prints exactly NAME.ast, and the
    program behaves as NAME.expected says both with and without --optimize
    (NAME.in and NAME.error as in tests/run).

Every check except tests/optimize runs twice: without the flag and with
--optimize. With the flag, a tests/valid fixture prints NAME.optimized.ast when
the optimizer changes its tree and NAME.ast when it does not. The fixtures that
deliberately use undeclared names stop in the semantic pass before the
optimizer, so they exit 1 with exactly NAME.optimized.err.

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


def run_compile(source, cwd, optimized=False):
    """Compile source to cwd/out.ll; return the result and whether out.ll exists."""
    output = Path(cwd) / "out.ll"
    output.unlink(missing_ok=True)
    flags = ["--optimize"] if optimized else []
    result = subprocess.run([sys.executable, str(COMPILER), *flags, str(source), str(output)],
                            capture_output=True, cwd=cwd, timeout=60)
    return result, output.exists()


def check_valid(source, cwd, optimized=False):
    if optimized:
        return check_valid_optimized(source, cwd)
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


def check_valid_optimized(source, cwd):
    """The same fixture with the flag after the file name.

    NAME.optimized.ast is the tree when the optimizer changes it; without it the
    tree must still equal NAME.ast. A front-end fixture that uses undeclared
    names cannot reach the optimizer, so NAME.optimized.err pins its one
    semantic error line instead.
    """
    tree_file = source.with_suffix(".optimized.ast")
    error_file = source.with_suffix(".optimized.err")
    result = subprocess.run([sys.executable, str(COMPILER), "--ast", str(source), "--optimize"],
                            capture_output=True, cwd=cwd, timeout=60)
    if error_file.exists():
        expected = error_file.read_bytes()
        if result.returncode != 1:
            return f"код виходу {result.returncode}, а чекали 1"
        if result.stdout:
            return f"зайвий stdout: {show(result.stdout)}"
        if result.stderr != expected:
            return f"stderr не збігається з {error_file.name}" + first_difference(expected, result.stderr)
        return None
    expected_file = tree_file if tree_file.exists() else source.with_suffix(".ast")
    if not expected_file.exists():
        return f"нема очікуваного файлу {expected_file.name}"
    if result.returncode != 0:
        return f"код виходу {result.returncode}, stderr: {show(result.stderr)}"
    if result.stderr:
        return f"зайвий stderr: {show(result.stderr)}"
    expected = expected_file.read_bytes()
    if result.stdout != expected:
        return f"AST не збігається з {expected_file.name}" + first_difference(expected, result.stdout)
    return None


def check_invalid(source, cwd, optimized=False):
    expected_file = source.with_suffix(".err")
    if not expected_file.exists():
        return f"нема очікуваного файлу {expected_file.name}"
    expected = expected_file.read_bytes()
    result, wrote_output = run_compile(source, cwd, optimized)
    if result.returncode != 1:
        return f"код виходу {result.returncode}, а чекали 1"
    if result.stdout:
        return "stdout не порожній"
    if wrote_output:
        return "після помилки лишився вихідний файл"
    if result.stderr != expected:
        return f"чекали {show(expected)!r}, а отримали {show(result.stderr)!r}"
    return None


def check_example(source, cwd, optimized=False):
    result, _ = run_compile(source, cwd, optimized)
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


def build_binary(module, cwd):
    """Build a compiled .ll module with llc and clang; return its path or a problem string."""
    llc, clang = find_tool("llc"), find_tool("clang")
    if not (llc and clang):
        return "нема ні lli, ні llc з clang: задай LLVM_BIN"
    obj, binary = Path(cwd) / "program.o", Path(cwd) / "program"
    for command in ([llc, "-relocation-model=pic", "-filetype=obj", str(module), "-o", str(obj)], [clang, str(obj), "-o", str(binary)]):
        built = subprocess.run(command, capture_output=True, timeout=60)
        if built.returncode != 0:
            return f"{Path(command[0]).name} впав: {show(built.stderr)}"
    return binary


def run_program(module, stdin, cwd):
    """Run a compiled .ll module; return the CompletedProcess or a problem string."""
    lli = find_tool("lli")
    if lli:
        return subprocess.run([lli, str(module)], stdin=stdin, capture_output=True, cwd=cwd, timeout=60)
    binary = build_binary(module, cwd)
    if isinstance(binary, str):
        return binary
    return subprocess.run([str(binary)], stdin=stdin, capture_output=True, cwd=cwd, timeout=60)


def check_run(source, cwd, optimized=False):
    expected_file = source.with_suffix(".expected")
    if not expected_file.exists():
        return f"нема очікуваного файлу {expected_file.name}"
    result, wrote_output = run_compile(source, cwd, optimized)
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


def check_optimized(source, cwd):
    """The tree after --optimize, then the same behaviour with and without the flag."""
    expected_file = source.with_suffix(".ast")
    if not expected_file.exists():
        return f"нема очікуваного файлу {expected_file.name}"
    result = subprocess.run([sys.executable, str(COMPILER), "--optimize", "--ast", str(source)],
                            capture_output=True, cwd=cwd, timeout=60)
    if result.returncode != 0 or result.stderr:
        return f"код виходу {result.returncode}, stderr: {show(result.stderr)}"
    expected = expected_file.read_bytes()
    if result.stdout != expected:
        return f"дерево не збігається з {expected_file.name}" + first_difference(expected, result.stdout)
    plain = check_run(source, cwd)
    if plain:
        return f"без прапорця: {plain}"
    optimized = check_run(source, cwd, optimized=True)
    return f"з --optimize: {optimized}" if optimized else None


def check_session(source, session, cwd, optimized=False):
    """Compile a real program, build the native binary, and replay one recorded session."""
    expected_file = session.with_suffix(".expected")
    if not expected_file.exists():
        return f"нема очікуваного файлу {expected_file.name}"
    result, wrote_output = run_compile(source, cwd, optimized)
    if result.returncode != 0 or result.stderr or not wrote_output:
        return f"не скомпілювалось, код {result.returncode}, stderr: {show(result.stderr)}"
    binary = build_binary(Path(cwd) / "out.ll", cwd)
    if isinstance(binary, str):
        return binary
    with open(session, "rb") as stdin:
        run = subprocess.run([str(binary)], stdin=stdin, capture_output=True, cwd=cwd, timeout=60)
    if run.returncode != 0 or run.stderr:
        return f"програма вийшла з кодом {run.returncode}, stderr: {show(run.stderr)}"
    expected = expected_file.read_bytes()
    if run.stdout != expected:
        return f"вивід не збігається з {expected_file.name}" + first_difference(expected, run.stdout)
    return None


def program_sessions(source):
    """The recorded sessions of a real program: NAME.in and NAME_*.in."""
    return [source.with_suffix(".in")] * source.with_suffix(".in").exists() + sorted(
        source.parent.glob(source.stem + "_*.in"))


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
    found = []
    for path in sorted(directory.glob("*" + suffix)):
        stem = path.name[:-len(suffix)].removesuffix(".optimized")
        if not (directory / (stem + ".bazar")).exists():
            found.append(path)
    return found


def main():
    # folder, check, expectation suffixes, whether the check also runs with --optimize
    groups = (
        ("tests/valid", check_valid, (".ast", ".optimized.err"), True),
        ("tests/invalid", check_invalid, (".err",), True),
        ("examples", check_example, (), True),
        ("tests/run", check_run, (".expected", ".in", ".error"), True),
        ("tests/optimize", check_optimized, (".ast", ".expected", ".in", ".error"), False),
    )
    total = failures = 0

    def report(line):
        write_text(sys.stdout, line + "\n")

    def run_check(name, check, *arguments):
        nonlocal total, failures
        total += 1
        try:
            problem = check(*arguments)
        except subprocess.TimeoutExpired:
            problem = "не вклався в час: схоже, цикл ніколи не докрутиться"
        if problem is None:
            report(f"PASS   {name}")
        else:
            failures += 1
            report(f"ПРОВАЛ {name}: {problem}")

    with tempfile.TemporaryDirectory() as cwd:
        for folder, check, suffixes, with_flag in groups:
            sources = sorted((ROOT / folder).glob("*.bazar"))
            if not sources:
                report(f"ПРОВАЛ {folder}: жодного *.bazar не знайшов, шо перевіряти?")
                failures += 1
                continue
            for source in sources:
                name = source.relative_to(ROOT).as_posix()
                run_check(name, check, source, cwd)
                if with_flag:
                    run_check(f"{name} --optimize", check, source, cwd, True)
            for orphan in (o for s in suffixes for o in orphans(folder, s)):
                total += 1
                failures += 1
                report(f"ПРОВАЛ {orphan.relative_to(ROOT).as_posix()}: файл-сирота, джерела .bazar для нього нема")
        for source in sorted((ROOT / "programs").glob("*.txt")):
            sessions = program_sessions(source)
            if len(sessions) < 2:
                total += 1
                failures += 1
                report(f"ПРОВАЛ {source.relative_to(ROOT).as_posix()}: треба хоча б дві записані сесії")
            for session in sessions:
                name = session.relative_to(ROOT).as_posix()
                run_check(name, check_session, source, session, cwd)
                run_check(f"{name} --optimize", check_session, source, session, cwd, True)
    report(f"\nPassed {total - failures} of {total}; failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
