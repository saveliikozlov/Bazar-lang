"""Bazar compiler frontend: lexer, parser, and AST dump.

    python3 compiler.py --ast <input.bazar | input.txt>

Exit codes:
    0: valid syntax; AST dump and final LF on stdout.
    1: lexical or syntax error; empty stdout and one stderr line:
           compilation error: line L:C: MESSAGE
       The error body depends on failure counters; see diagnostics.py.
    2: invalid arguments or unreadable input.

Semantic checking and code generation are not implemented.
"""

from pathlib import Path
import sys

from diagnostics import compilation_error_line
from lexer import LexError, describe_os_error, write_text
from parser import CompilationError, parse_program

USAGE = "Запускай так: python3 compiler.py --ast <input.bazar>"


def main(argv):
    if len(argv) != 2 or argv[0] != "--ast":
        write_text(sys.stderr, USAGE + "\n")
        return 2
    path = Path(argv[1])
    try:
        data = path.read_bytes()
    except OSError as error:
        write_text(sys.stderr, f"Файл '{path}' не читається: {describe_os_error(error)}. Перевір шлях і доступ.\n")
        return 2
    try:
        tree = parse_program(data)
    except (LexError, CompilationError) as error:
        write_text(sys.stderr, compilation_error_line(error))
        return 1
    # The tree is complete before output starts, so errors never leave a
    # partial dump. Lines are streamed because deep trees produce large dumps.
    output = sys.stdout.buffer
    for line in tree.dump_lines():
        output.write(line.encode("utf-8"))
        output.write(b"\n")
    output.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
