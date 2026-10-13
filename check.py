"""Run every source fixture through the real CLI and compare frozen expectations.

    python3 check.py

tests/valid/NAME.bazar: exit 0, exact NAME.ast on stdout, empty stderr.
tests/invalid/NAME.bazar: exit 1, empty stdout, exact single-line NAME.err on stderr.
examples/NAME.bazar: exit 0 and empty stderr.

Expectations are never written or regenerated. CLI invocations run from a
temporary directory, independently of the current working directory.
Orphan .ast/.err files without matching .bazar sources also fail. Exit 0
requires every check to pass. Output is UTF-8 regardless of locale.
"""

from pathlib import Path
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
    result = run_compiler(source, cwd)
    if result.returncode != 1:
        return f"код виходу {result.returncode}, а чекали 1"
    if result.stdout:
        return "stdout не порожній"
    if result.stderr != expected:
        return f"чекали {show(expected)!r}, а отримали {show(result.stderr)!r}"
    return None


def check_example(source, cwd):
    result = run_compiler(source, cwd)
    if result.returncode != 0 or result.stderr:
        return f"код виходу {result.returncode}, stderr: {show(result.stderr)}"
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
            for orphan in orphans(folder, suffix) if suffix else ():
                total += 1
                failures += 1
                report(f"ПРОВАЛ {orphan.relative_to(ROOT).as_posix()}: файл-сирота, джерела .bazar для нього нема")
    report(f"\nPassed {total - failures} of {total}; failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
