"""Bridge between the VS Code extension and the Bazar parsing library.

Read one stdin JSON object {"text": "..."}; call parse_program(); emit one
stdout JSON line:
    {"ok": true}
    {"ok": false, "error": {"kind": "lex"|"syntax", "line": L, "column": C, "message": "..."}}
    {"ok": false, "fatal": {"code": "...", "detail": "..."}}

Positions are 1-based, with UTF-8 byte columns matching the compiler.
User programs are not executed and AST dumps are not emitted.
"""

import json
import os
import sys

sys.dont_write_bytecode = True


def emit(payload):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def fatal(code, detail):
    emit({"ok": False, "fatal": {"code": code, "detail": detail}})
    return 0


def main():
    if sys.version_info < (3, 9):
        return fatal("python-version", "%d.%d" % sys.version_info[:2])
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdin.reconfigure(encoding="utf-8")
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    try:
        from lexer import LexError
        from parser import CompilationError, parse_program
    except Exception as error:  # missing or damaged backend
        return fatal("import", "%s: %s" % (type(error).__name__, error))
    try:
        request = json.loads(sys.stdin.read())
        text = request["text"]
        if not isinstance(text, str):
            raise TypeError("text має бути рядком")
    except Exception as error:
        return fatal("request", "%s: %s" % (type(error).__name__, error))

    # surrogatepass turns a lone JS surrogate into invalid UTF-8,
    # allowing the lexer to report it at the original byte position.
    data = text.encode("utf-8", "surrogatepass")
    try:
        parse_program(data)
    except (LexError, CompilationError) as error:
        kind = "lex" if isinstance(error, LexError) else "syntax"
        emit({"ok": False, "error": {"kind": kind, "line": error.line,
                                      "column": error.column, "message": error.message}})
        return 0
    except RecursionError:
        return fatal("recursion", "вхід надто глибокий для розбору")
    emit({"ok": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
