'use strict';
// Convert compiler positions (1-based line and UTF-8 byte column) to
// VS Code ranges (0-based line and UTF-16 offset). Pure functions.

// Word characters: ASCII letters/digits, '_', Cyrillic А-я, Ё/ё, І/і, Ї/ї, Є/є, Ґ/ґ.
// Apostrophes are included: the compiler joins letters with them (з'їзд).
const WORD_CHAR = 'A-Za-z0-9_\\u0401\\u0451\\u0410-\\u044F\\u0406\\u0456\\u0407\\u0457\\u0404\\u0454\\u0490\\u0491\\u0027\\u02BC';
const WORD_CHAR_RE = new RegExp(`[${WORD_CHAR}]`);

function utf8Length(codePoint) {
  if (codePoint <= 0x7f) return 1;
  if (codePoint <= 0x7ff) return 2;
  if (codePoint <= 0xffff) return 3; // lone surrogates also encode as three bytes
  return 4;
}

// Iterate code points; return [code point, UTF-16 width].
function codePointAt(text, index) {
  const cp = text.codePointAt(index);
  return [cp, cp > 0xffff ? 2 : 1];
}

// Split like the lexer: LF ends a line; preceding CR belongs to CRLF.
function splitLines(text) {
  const lines = [];
  let start = 0;
  for (;;) {
    const lf = text.indexOf('\n', start);
    if (lf < 0) {
      lines.push({ start, end: text.length, contentEnd: text.length });
      return lines;
    }
    const contentEnd = lf > start && text[lf - 1] === '\r' ? lf - 1 : lf;
    lines.push({ start, end: lf, contentEnd });
    start = lf + 1;
  }
}

// Convert a 1-based byte column to a UTF-16 offset in content excluding CR/LF.
// Beyond line end/EOF, return content length; inside a multibyte character,
// return the beginning of that character.
function byteColumnToUtf16(content, byteColumn) {
  const target = Math.max(0, byteColumn - 1);
  let bytes = 0;
  let index = 0;
  while (index < content.length) {
    const [cp, units] = codePointAt(content, index);
    const size = utf8Length(cp);
    if (bytes + size > target) return index;
    bytes += size;
    index += units;
  }
  return content.length;
}

// Underline range using 0-based VS Code line/character positions.
// At a word, number, or symbol, underline the token beginning at the position.
// At line end/EOF, underline the last preceding word or symbol if present;
// otherwise return a zero-width range at the exact error position.
function errorRange(text, line, byteColumn) {
  const lines = splitLines(text);
  const lineIndex = Math.min(Math.max(line, 1), lines.length) - 1;
  const { start, contentEnd } = lines[lineIndex];
  const content = text.slice(start, contentEnd);
  const at = byteColumnToUtf16(content, byteColumn);

  let from = at;
  let to = at;
  if (at < content.length) {
    if (WORD_CHAR_RE.test(content[at])) {
      while (to < content.length && WORD_CHAR_RE.test(content[to])) to += 1;
    } else {
      to += codePointAt(content, at)[1];
    }
  } else {
    let end = at;
    while (end > 0 && /[ \t]/.test(content[end - 1])) end -= 1;
    from = end;
    if (end > 0) {
      if (WORD_CHAR_RE.test(content[end - 1])) {
        while (from > 0 && WORD_CHAR_RE.test(content[from - 1])) from -= 1;
      } else {
        from = end - 1;
        if (from > 0 && /[\uDC00-\uDFFF]/.test(content[from]) && /[\uD800-\uDBFF]/.test(content[from - 1])) from -= 1;
      }
      to = end;
    }
  }
  return { startLine: lineIndex, startCharacter: from, endLine: lineIndex, endCharacter: to };
}

module.exports = { WORD_CHAR, WORD_CHAR_RE, utf8Length, splitLines, byteColumnToUtf16, errorRange };
