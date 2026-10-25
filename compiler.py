"""Bazar compiler: lexer, parser, semantic analysis, and LLVM IR generation.

    python3 compiler.py --ast <input.bazar | input.txt>
    python3 compiler.py <input.bazar | input.txt> <output.ll>

--ast prints the AST after parsing. The second form also runs the semantic
pass and writes the LLVM module to output.ll.

Exit codes:
    0: success; the AST dump on stdout, or output.ll written.
    1: lexical, syntax, or semantic error; empty stdout, no output file, and
       one stderr line:
           compilation error: line L:C: MESSAGE
    2: invalid arguments, unreadable input, or unwritable output.
"""

from pathlib import Path
import sys

from lexer import LexError, compilation_error_line, describe_os_error, write_text
from parser import CompilationError, parse_program
from semantic import analyze

USAGE = ("Запускай так: python3 compiler.py --ast <input.bazar> "
         "або python3 compiler.py <input.bazar> <output.ll>")


def read_source(path):
    try:
        return Path(path).read_bytes()
    except OSError as error:
        write_text(sys.stderr, f"Файл '{path}' не читається: {describe_os_error(error)}. Перевір шлях і доступ.\n")
        return None


def print_ast(path):
    data = read_source(path)
    if data is None:
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


def compile_file(source_path, output_path):
    data = read_source(source_path)
    if data is None:
        return 2
    try:
        tree = parse_program(data)
        analyze(tree)
    except (LexError, CompilationError) as error:
        write_text(sys.stderr, compilation_error_line(error))
        return 1
    # Code generation is the next step; until then a checked program
    # produces no output file.
    return 0


def main(argv):
    if len(argv) == 2 and argv[0] == "--ast":
        return print_ast(argv[1])
    if len(argv) == 2 and not argv[0].startswith("--") and not argv[1].startswith("--"):
        return compile_file(argv[0], argv[1])
    write_text(sys.stderr, USAGE + "\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
