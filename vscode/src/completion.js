'use strict';
// Pure Bazar completion logic without a vscode dependency. Returns suggestions
// with replacement ranges; extension.js converts them to CompletionItem objects.
const { WORD_CHAR } = require('./positions');
const { getEntry, hoverMarkdown } = require('./dictionary');

const W = `[${WORD_CHAR}]`;
const COMMENT_START_RE = new RegExp(`(?:^|[^${WORD_CHAR}])чутки:`);
const DECLARATION_RE = new RegExp(`(?<![${WORD_CHAR}])(?:зуб[ \\t]+даю|мутна[ \\t]+тєма)[ \\t]+([A-Za-z_\\u0401\\u0451\\u0410-\\u044F\\u0406\\u0456\\u0407\\u0457\\u0404\\u0454\\u0490\\u0491][${WORD_CHAR}]*)`, 'g');
const NEW_NAME_RE = new RegExp(`(?:^|[^${WORD_CHAR}])(?:зуб[ \\t]+даю|мутна[ \\t]+тєма)[ \\t]+[${WORD_CHAR}]*$`);

const TYPES = '${2|дрібняк,крупняк,базар|}';

// kind: statement | keyword | type | constant | operator.
// words: phrase words used to calculate the replacement range.
// dict: dictionary entry ID (defaults to label) used for documentation.
const ENTRIES = [
  { label: 'зуб даю', words: ['зуб', 'даю'], kind: 'statement', detail: 'immutable variable',
    snippet: `зуб даю \${1:name} тіпа ${TYPES} це \${3:0}` },
  { label: 'мутна тєма', words: ['мутна', 'тєма'], kind: 'statement', detail: 'mutable variable',
    snippet: `мутна тєма \${1:name} тіпа ${TYPES} це \${3:0}` },
  { label: 'перевзувся … тепер', dict: 'перевзувся', words: ['перевзувся'], kind: 'statement', detail: 'assignment',
    snippet: 'перевзувся ${1:name} тепер ${2:0}' },
  { label: 'якшо реально', words: ['якшо', 'реально'], kind: 'statement', detail: 'condition closed by отакої',
    snippet: 'якшо реально ${1:реально}\n\t${2:базарь 1}\nотакої' },
  { label: 'якшо реально … а нє', dict: 'якшо реально', words: ['якшо', 'реально'], kind: 'statement', detail: 'condition with an а нє branch',
    snippet: 'якшо реально ${1:реально}\n\t${2:базарь 1}\nа нє\n\t${3:базарь 0}\nотакої' },
  { label: 'а нє', words: ['а', 'нє'], kind: 'statement', detail: 'else branch', snippet: 'а нє' },
  { label: 'отакої', words: ['отакої'], kind: 'statement', detail: 'close the condition', snippet: 'отакої' },
  { label: 'базарь', words: ['базарь'], kind: 'statement', detail: 'print a value',
    snippet: 'базарь ${1:0}' },
  { label: 'всьо розходимось', words: ['всьо', 'розходимось'], kind: 'statement', detail: 'exit with an integer result',
    snippet: 'всьо розходимось ${1:0}' },
  { label: 'чутки:', words: ['чутки'], kind: 'statement', detail: 'comment through line end',
    snippet: 'чутки: ${1:comment}' },
  { label: 'тіпа', words: ['тіпа'], kind: 'keyword', detail: 'type follows the name', snippet: 'тіпа' },
  { label: 'це', words: ['це'], kind: 'keyword', detail: 'initial value follows the type', snippet: 'це' },
  { label: 'дрібняк', words: ['дрібняк'], kind: 'type', detail: 'i32', snippet: 'дрібняк' },
  { label: 'крупняк', words: ['крупняк'], kind: 'type', detail: 'i64', snippet: 'крупняк' },
  { label: 'базар', words: ['базар'], kind: 'type', detail: 'bool', snippet: 'базар' },
  { label: 'реально', words: ['реально'], kind: 'constant', detail: 'true', snippet: 'реально' },
  { label: 'гон', words: ['гон'], kind: 'constant', detail: 'false', snippet: 'гон' },
  { label: 'плюс', words: ['плюс'], kind: 'operator', detail: 'addition', snippet: 'плюс' },
  { label: 'мінус', words: ['мінус'], kind: 'operator', detail: 'subtraction, unary minus', snippet: 'мінус' },
  { label: 'на', words: ['на'], kind: 'operator', detail: 'multiplication', snippet: 'на' },
  { label: 'ділити на', words: ['ділити', 'на'], kind: 'operator', detail: 'integer division', snippet: 'ділити на' },
  { label: 'рівно', words: ['рівно'], kind: 'operator', detail: 'equal to', snippet: 'рівно' },
  { label: 'не рівно', words: ['не', 'рівно'], kind: 'operator', detail: 'not equal to', snippet: 'не рівно' },
  { label: 'більше', words: ['більше'], kind: 'operator', detail: 'greater than', snippet: 'більше' },
  { label: 'менше', words: ['менше'], kind: 'operator', detail: 'less than', snippet: 'менше' },
  { label: 'і ше', words: ['і', 'ше'], kind: 'operator', detail: 'logical AND', snippet: 'і ше' },
  { label: 'або', words: ['або'], kind: 'operator', detail: 'logical OR', snippet: 'або' },
];

const documentationCache = new Map();
// Dictionary Markdown for a completion, or undefined if no entry exists.
function documentationFor(entry) {
  const id = entry.dict || entry.label;
  if (!documentationCache.has(id)) {
    const record = getEntry(id);
    documentationCache.set(id, record ? hoverMarkdown(record) : undefined);
  }
  return documentationCache.get(id);
}

function isInComment(linePrefix) {
  return COMMENT_START_RE.test(linePrefix);
}

// Declared names, excluding comments. excludeEnd is the end of the name
// currently being typed, which must not suggest itself.
function declaredNames(text, excludeEnd) {
  const names = new Set();
  const lines = text.split('\n');
  let offset = 0;
  for (const line of lines) {
    const comment = line.match(COMMENT_START_RE);
    const code = comment ? line.slice(0, comment.index + comment[0].length - 'чутки:'.length) : line;
    for (const match of code.matchAll(DECLARATION_RE)) {
      const end = offset + match.index + match[0].length;
      if (end !== excludeEnd) names.add(match[1]);
    }
    offset += line.length + 1;
  }
  return [...names];
}

// Count characters already typed before the cursor for the phrase words:
// зуб д is replaced with the whole phrase, avoiding a duplicate зуб.
function matchPhrase(linePrefix, words) {
  const partialMatch = linePrefix.match(new RegExp(`(${W}*)$`));
  const partial = partialMatch[1].toLowerCase();
  for (let done = words.length - 1; done >= 0; done -= 1) {
    if (!words[done].startsWith(partial)) continue;
    if (done === 0) {
      return { length: partial.length };
    }
    const head = words.slice(0, done).join('[ \\t]+');
    const re = new RegExp(`(?:^|[^${WORD_CHAR}])(${head}[ \\t]+${W}*)$`, 'i');
    const found = linePrefix.match(re);
    if (found) return { length: found[1].length };
  }
  return null;
}

// Returns [{ label, filterText, insertText, isSnippet, kind, detail, documentation, sortText, replaceLength }].
// replaceLength: number of characters before the cursor to replace.
function complete(linePrefix, documentText, cursorOffset) {
  if (isInComment(linePrefix)) return [];
  const items = [];
  ENTRIES.forEach((entry, index) => {
    const match = matchPhrase(linePrefix, entry.words);
    if (!match) return;
    const words = entry.label === 'чутки:' ? 'чутки:' : entry.words.join(' ');
    items.push({
      label: entry.label,
      filterText: words,
      insertText: entry.snippet,
      isSnippet: /\$\{|\$\d/.test(entry.snippet),
      kind: entry.kind,
      detail: entry.detail,
      documentation: documentationFor(entry),
      sortText: String(index).padStart(3, '0'),
      replaceLength: match.length,
    });
  });
  if (!NEW_NAME_RE.test(linePrefix)) {
    const partial = linePrefix.match(new RegExp(`(${W}*)$`))[1];
    for (const name of declaredNames(documentText, cursorOffset)) {
      if (!name.toLowerCase().startsWith(partial.toLowerCase()) || name === partial) continue;
      items.push({
        label: name, filterText: name, insertText: name, isSnippet: false, kind: 'variable',
        detail: 'variable declared in this file', sortText: `9${name}`, replaceLength: partial.length,
      });
    }
  }
  return items;
}

module.exports = { complete, isInComment, declaredNames, matchPhrase, ENTRIES };
