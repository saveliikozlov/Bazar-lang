'use strict';
// Bazar keyword dictionary: one source for hover, the full reference,
// and completion documentation. Pure functions without vscode dependencies.
// Grammar productions are verbatim grammar.ebnf fragments, verified by tests.
const { WORD_CHAR } = require('./positions');

const NOT_EXECUTED = "The parser currently checks syntax only: values are not evaluated, and types and mutability are not checked. These are intended semantics.";

const P = {
  constant: 'constant_declaration = "желєзобетонно", IDENT, "тіпа", type, "це", expression ;',
  immutable: 'immutable_declaration = "зуб", "даю", IDENT, "тіпа", type, "це", expression ;',
  mutable: 'mutable_declaration = "мутна", "тєма", IDENT, "тіпа", type, "це", expression ;',
  type: 'type = "дрібняк" | "крупняк" | "базар" ;',
  assignment: 'assignment = "перевзувся", IDENT, "тепер", expression ;',
  print: 'print_statement = "базарь", expression ;',
  exit: 'exit_statement = "всьо", "розходимось", expression ;',
  if: 'if_statement = "якшо", "реально", expression, NEWLINE, block, [ "а", "нє", NEWLINE, block ], "отакої" ;',
  or: 'or_expression = and_expression, { "або", and_expression } ;',
  and: 'and_expression = comparison, { "і", "ше", comparison } ;',
  comparison: 'comparison = additive, [ comparison_operator, additive ] ;',
  comparisonOperator: 'comparison_operator = "рівно" | "не", "рівно" | "більше" | "менше" ;',
  additiveOperator: 'additive_operator = "плюс" | "мінус" ;',
  multiplicativeOperator: 'multiplicative_operator = "на" | "ділити", "на" ;',
  unary: 'unary = "мінус", unary | primary ;',
  boolean: 'boolean_literal = "реально" | "гон" ;',
  comment: 'comment = "чутки", ":", { comment_char } ;',
};

const IF_EXAMPLE = [
  'якшо реально 5 більше 3',
  '    базарь 1',
  'а нє',
  '    базарь 0',
  'отакої',
].join('\n');

// kind: phrase = multiword construct; keyword = word with its own meaning;
// fragment = phrase component; comment = the чутки: marker.
// semantic: include the note that execution and type checks are not implemented.
const PHRASES = [
  {
    id: 'зуб даю', kind: 'phrase', words: ['зуб', 'даю'],
    meaning: "Declares an immutable variable: literally a promise that the value will not change. Equivalent: `let name: T = e`. Both words stay on one line and may be separated by spaces or tabs.",
    productions: [P.immutable],
    syntax: "зуб даю NAME тіпа TYPE це EXPR",
    example: 'зуб даю зарплата тіпа крупняк це 100',
    semantic: true,
  },
  {
    id: 'мутна тєма', kind: 'phrase', words: ['мутна', 'тєма'],
    meaning: "Declares a mutable variable: literally a shady business that can still change. Equivalent: `let mut name: T = e`. Assign a new value with `перевзувся`.",
    productions: [P.mutable],
    syntax: "мутна тєма NAME тіпа TYPE це EXPR",
    example: 'мутна тєма залишок тіпа крупняк це 80',
    semantic: true,
  },
  {
    id: 'якшо реально', kind: 'phrase', words: ['якшо', 'реально'],
    meaning: "Starts a condition. The expression follows on the same line, then a statement block, an optional `а нє` branch, and the closing `отакої`. Equivalent: `if e { … } else { … }`. Since the true literal is also `реально`, an always-true condition is `якшо реально реально`.",
    productions: [P.if],
    syntax: 'якшо реально EXPR ⏎ BLOCK [ а нє ⏎ BLOCK ] отакої',
    example: IF_EXAMPLE,
    semantic: true,
  },
  {
    id: 'а нє', kind: 'phrase', words: ['а', 'нє'],
    meaning: "The else branch: its block is intended to run when the condition is false. The phrase occupies its own line inside `якшо реально` … `отакої`. One `отакої` closes the whole condition. This is not logical NOT; `нє` is not an expression operator.",
    productions: [P.if],
    syntax: 'якшо реально EXPR ⏎ BLOCK а нє ⏎ BLOCK отакої',
    example: IF_EXAMPLE,
    semantic: true,
  },
  {
    id: 'всьо розходимось', kind: 'phrase', words: ['всьо', 'розходимось'],
    meaning: "Exits the program with an expression result; literally everyone, go home. Equivalent: `exit(e)`. Optional and allowed wherever a statement is allowed.",
    productions: [P.exit],
    syntax: 'всьо розходимось EXPR',
    example: 'всьо розходимось 0',
    semantic: true,
  },
  {
    id: 'і ше', kind: 'phrase', words: ['і', 'ше'],
    meaning: "Logical AND (`and`), literally and also. Left-associative; binds more tightly than `або` and less tightly than comparisons.",
    productions: [P.and],
    syntax: 'EXPR і ше EXPR',
    example: 'базарь 1 більше 0 і ше 2 більше 1',
    semantic: true,
  },
  {
    id: 'не рівно', kind: 'phrase', words: ['не', 'рівно'],
    meaning: "Not-equal comparison (`!=`). Only one comparison is allowed per expression level, so `a менше b менше c` is a syntax error.",
    productions: [P.comparison, P.comparisonOperator],
    syntax: 'EXPR не рівно EXPR',
    example: 'базарь 1 не рівно 2',
    semantic: true,
  },
  {
    id: 'ділити на', kind: 'phrase', words: ['ділити', 'на'],
    meaning: "Integer division (`/`). Left-associative, with the same precedence as multiplication `на`.",
    productions: [P.multiplicativeOperator],
    syntax: 'EXPR ділити на EXPR',
    example: 'базарь 8 ділити на 2',
    semantic: true,
  },
];

const KEYWORDS = [
  {
    id: 'желєзобетонно', kind: 'keyword', words: ['желєзобетонно'],
    meaning: "Declares a compile-time constant: literally rock-solid, set in reinforced concrete. Equivalent: `const NAME: T = e`. Allowed only at the top level of a program, not inside `якшо реально`. The value is a constant expression: literals, operators, parentheses and earlier constants, but no variables. Unlike `зуб даю`, which may be initialized from any run-time value, a constant's value is known before the program runs.",
    productions: [P.constant],
    syntax: "желєзобетонно NAME тіпа TYPE це CONST_EXPR",
    example: 'желєзобетонно ЛІМІТ тіпа крупняк це 1000 на 1000',
    semantic: true,
  },
  {
    id: 'тіпа', kind: 'keyword', words: ['тіпа'],
    meaning: "Declaration connector between the name and its type. It is used only within `желєзобетонно`, `зуб даю` or `мутна тєма`, never by itself.",
    productions: [P.constant, P.immutable, P.mutable],
    syntax: "зуб даю NAME тіпа TYPE це EXPR",
    example: 'зуб даю x тіпа дрібняк це 1',
  },
  {
    id: 'це', kind: 'keyword', words: ['це'],
    meaning: "Declaration connector between the type and the initial value. It is used only within `желєзобетонно`, `зуб даю` or `мутна тєма`. Assignment uses `тепер` instead.",
    productions: [P.constant, P.immutable, P.mutable],
    syntax: "мутна тєма NAME тіпа TYPE це EXPR",
    example: 'мутна тєма x тіпа дрібняк це 1',
  },
  {
    id: 'дрібняк', kind: 'keyword', words: ['дрібняк'],
    meaning: "The intended signed 32-bit integer type (`i32`), literally small change. Appears after `тіпа`.",
    productions: [P.type],
    syntax: 'тіпа дрібняк',
    example: 'зуб даю x тіпа дрібняк це 1',
    semantic: true,
  },
  {
    id: 'крупняк', kind: 'keyword', words: ['крупняк'],
    meaning: "The intended signed 64-bit integer type (`i64`), literally big money. Appears after `тіпа`.",
    productions: [P.type],
    syntax: 'тіпа крупняк',
    example: 'зуб даю бабки тіпа крупняк це 100',
    semantic: true,
  },
  {
    id: 'базар', kind: 'keyword', words: ['базар'],
    meaning: "Boolean type (`bool`), with values `реально` and `гон`. Appears after `тіпа`. The similar word `базарь` is the output statement.",
    productions: [P.type],
    syntax: 'тіпа базар',
    example: 'зуб даю ок тіпа базар це реально',
    semantic: true,
  },
  {
    id: 'перевзувся', kind: 'keyword', words: ['перевзувся'],
    meaning: "Assignment: a variable changes its value, literally changes shoes or position. Equivalent: `name = e`. Follow it with a name, `тепер`, and an expression.",
    productions: [P.assignment],
    syntax: "перевзувся NAME тепер EXPR",
    example: 'перевзувся залишок тепер залишок мінус 15',
    semantic: true,
  },
  {
    id: 'тепер', kind: 'keyword', words: ['тепер'],
    meaning: "Assignment connector between the variable name and its new value, literally now. Used only inside a `перевзувся` statement.",
    productions: [P.assignment],
    syntax: "перевзувся NAME тепер EXPR",
    example: 'перевзувся залишок тепер 5',
  },
  {
    id: 'базарь', kind: 'keyword', words: ['базарь'],
    meaning: "Prints the value of an expression, literally talk. Equivalent: `print(e)`. Do not confuse it with type `базар`.",
    productions: [P.print],
    syntax: 'базарь EXPR',
    example: 'базарь залишок',
    semantic: true,
  },
  {
    id: 'отакої', kind: 'keyword', words: ['отакої'],
    meaning: "Closes the ENTIRE condition, including an optional `а нє` branch, rather than each branch separately. Each nested condition has its own `отакої`. Occupies a separate line.",
    productions: [P.if],
    syntax: 'якшо реально EXPR ⏎ BLOCK [ а нє ⏎ BLOCK ] отакої',
    example: IF_EXAMPLE,
  },
  {
    id: 'реально', kind: 'keyword', words: ['реально'],
    meaning: "Has two roles: the Boolean true literal, and the second word of the condition opener `якшо реально`. In `якшо реально реально`, the first occurrence belongs to the phrase and the second is the literal.",
    productions: [P.boolean, P.if],
    syntax: 'реально',
    example: 'зуб даю ок тіпа базар це реально',
    semantic: true,
  },
  {
    id: 'гон', kind: 'keyword', words: ['гон'],
    meaning: "The Boolean false literal, colloquially a lie.",
    productions: [P.boolean],
    syntax: 'гон',
    example: 'зуб даю ок тіпа базар це гон',
    semantic: true,
  },
  {
    id: 'або', kind: 'keyword', words: ['або'],
    meaning: "Logical OR (`or`). Left-associative; has the lowest operator precedence and binds less tightly than `і ше`.",
    productions: [P.or],
    syntax: 'EXPR або EXPR',
    example: 'базарь реально або гон',
    semantic: true,
  },
  {
    id: 'рівно', kind: 'keyword', words: ['рівно'],
    meaning: "Equality comparison (`==`). Only one comparison is allowed per expression level. Preceded by `не`, it forms `не рівно`.",
    productions: [P.comparison, P.comparisonOperator],
    syntax: 'EXPR рівно EXPR',
    example: 'базарь 2 рівно 2',
    semantic: true,
  },
  {
    id: 'більше', kind: 'keyword', words: ['більше'],
    meaning: "Greater-than comparison (`>`). Only one comparison is allowed per expression level.",
    productions: [P.comparison, P.comparisonOperator],
    syntax: 'EXPR більше EXPR',
    example: 'базарь 5 більше 3',
    semantic: true,
  },
  {
    id: 'менше', kind: 'keyword', words: ['менше'],
    meaning: "Less-than comparison (`<`). Only one comparison is allowed per expression level.",
    productions: [P.comparison, P.comparisonOperator],
    syntax: 'EXPR менше EXPR',
    example: 'базарь 3 менше 5',
    semantic: true,
  },
  {
    id: 'плюс', kind: 'keyword', words: ['плюс'],
    meaning: "Addition (`+`). Left-associative; binds less tightly than multiplication and division.",
    productions: [P.additiveOperator],
    syntax: 'EXPR плюс EXPR',
    example: 'базарь 2 плюс 3',
    semantic: true,
  },
  {
    id: 'мінус', kind: 'keyword', words: ['мінус'],
    meaning: "Has two roles: binary subtraction (`-`) after an operand, and unary numeric negation before an operand. Unary minus is right-associative: `мінус мінус x` means `-(-x)`. Integer literals have no sign; `мінус 5` applies unary minus to `5`.",
    productions: [P.additiveOperator, P.unary],
    syntax: 'EXPR мінус EXPR  |  мінус EXPR',
    example: 'базарь 7 мінус 2\nбазарь мінус 5',
    semantic: true,
  },
  {
    id: 'на', kind: 'keyword', words: ['на'],
    meaning: "Multiplication (`*`), as in `2 на 3`. Left-associative; binds more tightly than `плюс` and `мінус`. Also the second word of `ділити на`; outside that phrase it means multiplication.",
    productions: [P.multiplicativeOperator],
    syntax: 'EXPR на EXPR',
    example: 'базарь 2 на 3',
    semantic: true,
  },
];

// Words that exist only as phrase components.
function fragment(word, phraseId, meaning) {
  return { id: word, kind: 'fragment', words: [word], partOf: phraseId, meaning };
}

const FRAGMENTS = [
  fragment('зуб', 'зуб даю', "First word of `зуб даю`. Reserved: it cannot name a variable and has no standalone meaning."),
  fragment('даю', 'зуб даю', "Second word of `зуб даю`. Reserved: it has no standalone meaning and cannot name a variable."),
  fragment('мутна', 'мутна тєма', "First word of `мутна тєма`. Reserved: it has no standalone meaning and cannot name a variable."),
  fragment('тєма', 'мутна тєма', "Second word of `мутна тєма`. Reserved: it has no standalone meaning and cannot name a variable."),
  fragment('якшо', 'якшо реально', "First word of `якшо реально`. Reserved: a condition starts only with the complete phrase."),
  fragment('а', 'а нє', "First word of `а нє`. Reserved, not a standalone connective or variable name. Cyrillic `а` and Latin `a` are different characters."),
  fragment('нє', 'а нє', "Second word of `а нє`. This is not logical NOT: it is absent from expressions and has no standalone meaning."),
  fragment('всьо', 'всьо розходимось', "First word of `всьо розходимось`. Reserved: it has no standalone meaning and cannot name a variable."),
  fragment('розходимось', 'всьо розходимось', "Second word of `всьо розходимось`. Reserved: it has no standalone meaning and cannot name a variable."),
  fragment('і', 'і ше', "First word of `і ше`. Reserved, with no standalone meaning. Ukrainian `і`, Latin `i`, and Cyrillic `и` are different characters."),
  fragment('ше', 'і ше', "Second word of `і ше`. Reserved: it has no standalone meaning and cannot name a variable."),
  fragment('не', 'не рівно', "First word of `не рівно`. It is not logical negation and is not used on its own in expressions."),
  fragment('ділити', 'ділити на', "First word of `ділити на`. Has no standalone meaning; division requires the complete phrase."),
];

const COMMENT = {
  id: 'чутки:', kind: 'comment', words: ['чутки'],
  meaning: "Starts a comment through the end of the line, literally rumors. The complete word `чутки` must be immediately followed by a colon: `чутки :` and bare `чутки` are lexical errors. In `xчутки:`, the word is `xчутки`. The ending newline is not part of the comment.",
  productions: [P.comment],
  syntax: 'чутки: TEXT',
  example: 'чутки: time to count the money',
};

const ENTRIES = [...PHRASES, ...KEYWORDS, ...FRAGMENTS, COMMENT];

const BY_ID = new Map(ENTRIES.map((entry) => [entry.id, entry]));
// Individual word -> its own entry when it has an independent meaning;
// otherwise map to the phrase component entry.
const BY_WORD = new Map();
for (const entry of [...KEYWORDS, ...FRAGMENTS]) BY_WORD.set(entry.words[0], entry);
BY_WORD.set('чутки', COMMENT);
const PHRASES_LONGEST_FIRST = [...PHRASES].sort((a, b) => b.words.length - a.words.length);

const WORD_RE = new RegExp(`[${WORD_CHAR}]+`, 'g');
const GAP_RE = /^[ \t]+$/;

function getEntry(id) {
  return BY_ID.get(id);
}

// Maximal word-character sequences before the comment marker, matching lexer rules.
// comment is the чутки: range when a comment is present.
function tokenize(line) {
  const tokens = [];
  let comment = null;
  for (const match of line.matchAll(WORD_RE)) {
    const end = match.index + match[0].length;
    if (match[0] === 'чутки' && line[end] === ':') {
      comment = { start: match.index, end: end + 1 };
      break;
    }
    tokens.push({ text: match[0], start: match.index, end });
  }
  return { tokens, comment };
}

// Segment words into the longest complete phrase separated by spaces/tabs,
// or individual words. Matching stays within one physical line.
function segments(line, tokens) {
  const result = [];
  let i = 0;
  while (i < tokens.length) {
    let matched = null;
    for (const phrase of PHRASES_LONGEST_FIRST) {
      const n = phrase.words.length;
      if (i + n > tokens.length) continue;
      let ok = true;
      for (let k = 0; k < n && ok; k += 1) {
        ok = tokens[i + k].text === phrase.words[k]
          && (k === 0 || GAP_RE.test(line.slice(tokens[i + k - 1].end, tokens[i + k].start)));
      }
      if (ok) { matched = phrase; break; }
    }
    if (matched) {
      const parts = tokens.slice(i, i + matched.words.length);
      result.push({ entry: matched, parts, start: parts[0].start, end: parts[parts.length - 1].end });
      i += matched.words.length;
    } else {
      const entry = BY_WORD.get(tokens[i].text);
      if (entry) result.push({ entry, parts: [tokens[i]], start: tokens[i].start, end: tokens[i].end });
      i += 1;
    }
  }
  return result;
}

// Find a dictionary entry at character (UTF-16) in a line without its newline.
// Returns { entry, start, end } or null. The range covers the entire phrase.
function findAt(line, character) {
  const { tokens, comment } = tokenize(line);
  if (comment && character >= comment.start && character < comment.end) {
    return { entry: COMMENT, start: comment.start, end: comment.end };
  }
  for (const segment of segments(line, tokens)) {
    if (segment.parts.some((token) => character >= token.start && character < token.end)) {
      return { entry: segment.entry, start: segment.start, end: segment.end };
    }
  }
  return null;
}

// Escape ordinary Markdown text while retaining inline code.
function escapeMarkdown(text) {
  return text.replace(/[\\`*_{}[\]()#+!|<>~.-]/g, '\\$&');
}

function inline(text) {
  return text.split('`').map((part, index) => (index % 2 === 1 ? `\`${part}\`` : escapeMarkdown(part))).join('');
}

const KIND_LABELS = {
  phrase: 'multiword phrase',
  keyword: 'keyword',
  fragment: 'phrase component',
  comment: 'comment',
};

function fence(language, body) {
  return `\`\`\`${language}\n${body}\n\`\`\``;
}

function bodyMarkdown(entry) {
  const parts = [inline(entry.meaning)];
  if (entry.semantic) parts.push(inline(NOT_EXECUTED));
  const owner = entry.partOf ? BY_ID.get(entry.partOf) : null;
  const productions = owner ? owner.productions : entry.productions;
  if (owner) parts.push(inline(`This word cannot be used on its own: it is part of «${owner.id}».`));
  parts.push(`**Grammar**\n\n${fence('ebnf', productions.join('\n'))}`);
  const syntax = owner ? owner.syntax : entry.syntax;
  parts.push(`**Syntax:** \`${syntax}\``);
  parts.push(`**${owner ? 'Complete phrase example' : 'Example'}:**\n\n${fence('bazar', owner ? owner.example : entry.example)}`);
  return parts.join('\n\n');
}

// Markdown for keyword hover and completion documentation.
function hoverMarkdown(entry) {
  return `**${escapeMarkdown(entry.id)}** · ${KIND_LABELS[entry.kind]}\n\n${bodyMarkdown(entry)}`;
}

// Full reference: every entry in one Markdown document.
function referenceMarkdown() {
  const section = (title, entries) => [`## ${title}`, ...entries.map((entry) => `### ${escapeMarkdown(entry.id)}\n\n*${KIND_LABELS[entry.kind]}*\n\n${bodyMarkdown(entry)}`)].join('\n\n');
  return [
    '# Bazar Keyword Dictionary',
    inline('All reserved words and phrases from the Bazar grammar. Words match exactly and case-sensitively. Phrase words may be separated by spaces or tabs, never a newline. This reference works without Python or a project.'),
    inline(NOT_EXECUTED),
    section('Phrases', PHRASES),
    section('Keywords', KEYWORDS),
    section('Phrase Components', FRAGMENTS),
    section('Comments', [COMMENT]),
  ].join('\n\n') + '\n';
}

module.exports = {
  ENTRIES, PHRASES, KEYWORDS, FRAGMENTS, COMMENT, NOT_EXECUTED,
  getEntry, tokenize, findAt, escapeMarkdown, hoverMarkdown, referenceMarkdown,
};
