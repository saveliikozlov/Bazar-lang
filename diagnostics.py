"""Optional persistent failure counters and CLI diagnostic selection.

Counters are disabled by default: every CLI error uses the original
diagnostic and no state is read or written. Set BAZAR_SPICY=1 to enable them.

When enabled, one SQLite file per OS user is shared by compiler.py and lexer.py:
* lifetime_failures counts all failures and only increases;
* message_counter increases per failure and drops by two after a swear message.

Increment both counters first. If lifetime_failures > 40, use FINAL_MESSAGE
without a decrement. Otherwise, message_counter > 10 prepends an uncensored
exclamation containing ! and subtracts two; otherwise use the original text.

Storage defaults to ~/.bazar/compiler_failures.sqlite3, overridden by
BAZAR_FAILURE_COUNTER_FILE. A single BEGIN IMMEDIATE transaction prevents
lost increments under concurrency. Unavailable or corrupt storage falls back
to the original message without modifying the file. Library lex() and
parse_program() calls know nothing about counters.
"""

import os
from pathlib import Path
import sqlite3

SPICY_ENV = "BAZAR_SPICY"
STATE_ENV = "BAZAR_FAILURE_COUNTER_FILE"
FINAL_MESSAGE = "Вась... Ну тут вже все."
FINAL_AFTER = 40
SWEAR_AFTER = 10
SWEAR_DISCOUNT = 2

PLAIN = "plain"
SWEAR = "swear"
FINAL = "final"

# Swearing refers to the code/situation; the original diagnostic follows.
SWEAR_PREFIXES = (
    "Блять, знову криво!",
    "Шо за хуйня в коді!",
    "Піздєц, а не програма!",
    "Їбаний насос, ну скільки можна!",
)


class CounterUnavailable(Exception):
    """Counter storage could not be located or contains invalid data."""


def state_path():
    override = os.environ.get(STATE_ENV)
    if override:
        return Path(override)
    try:
        home = Path.home()
    except (KeyError, RuntimeError) as error:
        raise CounterUnavailable("нема домашньої теки") from error
    return home / ".bazar" / "compiler_failures.sqlite3"


def next_state(lifetime, counter):
    """Transform pre-failure state into the resulting (lifetime, counter, tier)."""
    lifetime += 1
    counter += 1
    if lifetime > FINAL_AFTER:
        return lifetime, counter, FINAL
    if counter > SWEAR_AFTER:
        return lifetime, counter - SWEAR_DISCOUNT, SWEAR
    return lifetime, counter, PLAIN


def read_state(connection):
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'failures'").fetchone()
    if table is None:
        connection.execute("CREATE TABLE failures (id INTEGER PRIMARY KEY, "
                           "lifetime_failures INTEGER NOT NULL, message_counter INTEGER NOT NULL)")
        connection.execute("INSERT INTO failures VALUES (1, 0, 0)")
        return 0, 0
    rows = connection.execute("SELECT lifetime_failures, message_counter FROM failures").fetchall()
    if len(rows) != 1 or not all(type(value) is int and value >= 0 for value in rows[0]):
        raise CounterUnavailable("лічильники зіпсовані")
    return rows[0]


def count_failure(path):
    """Atomically record a failure and return (lifetime, counter, tier)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        lifetime, counter, tier = next_state(*read_state(connection))
        connection.execute("UPDATE failures SET lifetime_failures = ?, message_counter = ?",
                           (lifetime, counter))
        connection.execute("COMMIT")
    finally:
        connection.close()  # rolls back any uncommitted transaction
    return lifetime, counter, tier


def counters_enabled():
    return os.environ.get(SPICY_ENV) == "1"


def failure_message(message):
    """Select the CLI error body according to persistent failure counters."""
    if not counters_enabled():
        return message
    try:
        lifetime, _, tier = count_failure(state_path())
    except (CounterUnavailable, OSError, sqlite3.Error, OverflowError, UnicodeError):
        return message
    if tier == FINAL:
        return FINAL_MESSAGE
    if tier == SWEAR:
        return f"{SWEAR_PREFIXES[lifetime % len(SWEAR_PREFIXES)]} {message}"
    return message


def compilation_error_line(error):
    """Format stderr with the original fixed prefix and position."""
    return f"compilation error: line {error.line}:{error.column}: {failure_message(error.message)}\n"
