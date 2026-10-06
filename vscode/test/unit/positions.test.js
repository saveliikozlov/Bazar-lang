'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { byteColumnToUtf16, errorRange, splitLines } = require('../../src/positions');

test("byte columns: ASCII, Cyrillic, emoji, and tabs", () => {
  assert.strictEqual(byteColumnToUtf16('abc', 1), 0);
  assert.strictEqual(byteColumnToUtf16('abc', 3), 2);
  assert.strictEqual(byteColumnToUtf16('зуб даю', 1), 0);
  assert.strictEqual(byteColumnToUtf16('зуб даю', 7), 3); // three letters, two bytes each
  assert.strictEqual(byteColumnToUtf16('зуб даю', 8), 4);
  assert.strictEqual(byteColumnToUtf16('\tx', 2), 1);
  // 😀 = four UTF-8 bytes, two UTF-16 units
  assert.strictEqual(byteColumnToUtf16('😀x', 5), 2);
  assert.strictEqual(byteColumnToUtf16('a😀зx', 1 + 1 + 4 + 2), 1 + 2 + 1);
});

test("columns inside characters round down; out-of-bounds columns use line end", () => {
  assert.strictEqual(byteColumnToUtf16('зуб', 2), 0);
  assert.strictEqual(byteColumnToUtf16('😀', 3), 0);
  assert.strictEqual(byteColumnToUtf16('abc', 4), 3);
  assert.strictEqual(byteColumnToUtf16('abc', 99), 3);
  assert.strictEqual(byteColumnToUtf16('', 1), 0);
});

test("splitLines: LF, CRLF, and EOF", () => {
  assert.deepStrictEqual(splitLines('a\r\nb\n'), [
    { start: 0, end: 2, contentEnd: 1 },
    { start: 3, end: 4, contentEnd: 4 },
    { start: 5, end: 5, contentEnd: 5 },
  ]);
});

test("errorRange underlines the word at the error position", () => {
  // Test тіпа on line 2 rather than using базарь 1 плюс !.
  const text = 'a\nзуб даю x тіпа\n';
  const r = errorRange(text, 2, 1 + 2 * 3 + 1 + 2 * 3 + 1 + 1 + 1); // byte column of тіпа
  assert.deepStrictEqual(r, { startLine: 1, startCharacter: 10, endLine: 1, endCharacter: 14 });
});

test("emoji in a preceding comment does not shift the next line", () => {
  const text = 'чутки: 😀😀\nзуб x\n';
  const r = errorRange(text, 2, 8); // зуб = six bytes, space, x
  assert.strictEqual(r.startLine, 1);
  assert.strictEqual(r.startCharacter, 4);
  assert.strictEqual(r.endCharacter, 5);
});

test("errorRange: emoji before a token on the same line", () => {
  const text = 'a😀 bb';
  // bytes: a(1), 😀(4), space(1); bb starts at column 7
  const r = errorRange(text, 1, 7);
  assert.deepStrictEqual(r, { startLine: 0, startCharacter: 4, endLine: 0, endCharacter: 6 });
});

test("errorRange: punctuation and astral characters", () => {
  assert.deepStrictEqual(errorRange('x = 1', 1, 3), { startLine: 0, startCharacter: 2, endLine: 0, endCharacter: 3 });
  assert.deepStrictEqual(errorRange('a 😀', 1, 3), { startLine: 0, startCharacter: 2, endLine: 0, endCharacter: 4 });
});

test("errorRange: CRLF line end underlines the preceding word", () => {
  const text = 'зуб даю x тіпа\r\nдалі\r\n';
  // CR follows зуб(6) + space + даю(6) + space + x(1) + space + тіпа(8): byte column 25
  const r = errorRange(text, 1, 25);
  assert.deepStrictEqual(r, { startLine: 0, startCharacter: 10, endLine: 0, endCharacter: 14 });
});

test("errorRange: trailing spaces before line end are skipped", () => {
  assert.deepStrictEqual(errorRange('базарь  \t\nx', 1, 16), { startLine: 0, startCharacter: 0, endLine: 0, endCharacter: 6 });
});

test("errorRange: EOF after LF or on an empty line has zero width", () => {
  const text = 'якшо реально реально\nбазарь 1\n';
  assert.deepStrictEqual(errorRange(text, 3, 1), { startLine: 2, startCharacter: 0, endLine: 2, endCharacter: 0 });
});

test("errorRange: EOF without final LF uses the preceding word", () => {
  assert.deepStrictEqual(errorRange('базарь', 1, 13), { startLine: 0, startCharacter: 0, endLine: 0, endCharacter: 6 });
});

test("errorRange: out-of-bounds lines clamp to the final line", () => {
  assert.deepStrictEqual(errorRange('x', 9, 1), { startLine: 0, startCharacter: 0, endLine: 0, endCharacter: 1 });
});

test("errorRange: EOF after emoji underlines the whole surrogate pair", () => {
  const full = { startLine: 2, startCharacter: 7, endLine: 2, endCharacter: 9 };
  assert.deepStrictEqual(errorRange('якшо реально реально\nбазарь 1\nчутки: 😀', 3, 17), full);
  assert.deepStrictEqual(errorRange('якшо реально реально\r\nбазарь 1\r\nчутки: 😀', 3, 17), full);
  assert.deepStrictEqual(errorRange('x\nчутки: 😀  \t', 2, 20), { startLine: 1, startCharacter: 7, endLine: 1, endCharacter: 9 });
  assert.deepStrictEqual(errorRange('😀', 1, 5), { startLine: 0, startCharacter: 0, endLine: 0, endCharacter: 2 });
});
