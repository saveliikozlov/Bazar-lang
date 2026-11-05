"""Bazar compiler: lexer, parser, semantic analysis, and LLVM IR generation.

    python3 compiler.py --ast <input.bazar | input.txt>
    python3 compiler.py <input.bazar | input.txt> <output.ll>

--ast prints the AST after parsing. The second form also runs the semantic
pass and writes the LLVM module to output.ll.

--optimize, anywhere on the command line, runs the optimizer on the checked
tree before code generation; together with --ast it prints the tree after it.

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
from optimizer import optimize
from semantic import analyze

TOO_DEEP = "Вираз завеликий: компілятор не може пройти таке глибоке дерево. Розбий його на кілька рядків."

USAGE = ("Запускай так: python3 compiler.py [--optimize] --ast <input.bazar> "
         "або python3 compiler.py [--optimize] <input.bazar> <output.ll>")


def read_source(path):
    try:
        return Path(path).read_bytes()
    except OSError as error:
        write_text(sys.stderr, f"Файл '{path}' не читається: {describe_os_error(error)}. Перевір шлях і доступ.\n")
        return None


def print_ast(path, optimized=False):
    data = read_source(path)
    if data is None:
        return 2
    try:
        tree = parse_program(data)
        if optimized:
            optimize(tree, analyze(tree))
    except (LexError, CompilationError) as error:
        write_text(sys.stderr, compilation_error_line(error))
        return 1
    except RecursionError:
        write_text(sys.stderr, compilation_error_line(CompilationError(1, 1, TOO_DEEP)))
        return 1
    # The tree is complete before output starts, so errors never leave a
    # partial dump. Lines are streamed because deep trees produce large dumps.
    output = sys.stdout.buffer
    for line in tree.dump_lines():
        output.write(line.encode("utf-8"))
        output.write(b"\n")
    output.flush()
    return 0


def compile_file(source_path, output_path, optimized=False):
    data = read_source(source_path)
    if data is None:
        return 2
    try:
        tree = parse_program(data)
        info = analyze(tree)
        if optimized:
            optimize(tree, info)
    except (LexError, CompilationError) as error:
        write_text(sys.stderr, compilation_error_line(error))
        return 1
    except RecursionError:
        write_text(sys.stderr, compilation_error_line(CompilationError(1, 1, TOO_DEEP)))
        return 1
    # Imported here so that --ast works without llvmlite installed.
    try:
        from codegen import generate
    except ImportError:
        write_text(sys.stderr, "От фігня, llvmlite-у нема. Запусти через .venv/bin/python або постав "
                               "його командою «pip install -r requirements.txt», тьфу ти нути.\n")
        return 2
    try:
        text = generate(tree, info)
    except RecursionError:
        write_text(sys.stderr, compilation_error_line(CompilationError(1, 1, TOO_DEEP)))
        return 1
    try:
        Path(output_path).write_text(text, encoding="utf-8")
    except OSError as error:
        write_text(sys.stderr, f"Файл '{output_path}' не записується: {describe_os_error(error)}.\n")
        return 2
    return 0


def main(argv):
    flags = [argument for argument in argv if argument.startswith("--")]
    paths = [argument for argument in argv if not argument.startswith("--")]
    optimized = "--optimize" in flags
    if len(set(flags)) == len(flags) and set(flags) <= {"--ast", "--optimize"}:
        if "--ast" in flags and len(paths) == 1:
            return print_ast(paths[0], optimized)
        if "--ast" not in flags and len(paths) == 2:
            return compile_file(paths[0], paths[1], optimized)
    write_text(sys.stderr, USAGE + "\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
