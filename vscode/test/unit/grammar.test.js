'use strict';
// Real TextMate tokenizer (vscode-textmate + Oniguruma) for source.bazar.
const test = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const vsctm = require('vscode-textmate');
const oniguruma = require('vscode-oniguruma');

const wasm = fs.readFileSync(require.resolve('vscode-oniguruma/release/onig.wasm')).buffer;
const grammarPath = path.join(__dirname, '..', '..', 'syntaxes', 'bazar.tmLanguage.json');

let grammarPromise;
function loadGrammar() {
  grammarPromise ??= (async () => {
    await oniguruma.loadWASM(wasm);
    const registry = new vsctm.Registry({
      onigLib: Promise.resolve({
        createOnigScanner: (sources) => new oniguruma.OnigScanner(sources),
        createOnigString: (s) => new oniguruma.OnigString(s),
      }),
      loadGrammar: async (scope) => (scope === 'source.bazar'
        ? vsctm.parseRawGrammar(fs.readFileSync(grammarPath, 'utf8'), grammarPath) : null),
    });
    return registry.loadGrammar('source.bazar');
  })();
  return grammarPromise;
}

// Map nonempty token text to its most specific scope, excluding source.bazar.
async function scopes(line) {
  const grammar = await loadGrammar();
  const { tokens } = grammar.tokenizeLine(line, vsctm.INITIAL);
  return tokens
    .map((t) => [line.slice(t.startIndex, t.endIndex), t.scopes.slice(1).pop()])
    .filter(([text]) => text.trim() !== '');
}
const map = async (line) => Object.fromEntries(await scopes(line));

test("declarations, types, Booleans, and numbers", async () => {
  const m = await map('зуб даю ціна тіпа дрібняк це 12');
  assert.strictEqual(m['зуб'], 'keyword.declaration.bazar');
  assert.strictEqual(m['даю'], 'keyword.declaration.bazar');
  assert.strictEqual(m['ціна'], 'variable.other.bazar');
  assert.strictEqual(m['дрібняк'], 'storage.type.bazar');
  assert.strictEqual(m['12'], 'constant.numeric.integer.bazar');
  const b = await map('мутна тєма ok тіпа базар це гон');
  assert.strictEqual(b['мутна'], 'keyword.declaration.bazar');
  assert.strictEqual(b['базар'], 'storage.type.bazar');
  assert.strictEqual(b['гон'], 'constant.language.boolean.bazar');
});

test("keyword prefixes in identifiers are not highlighted as keywords", async () => {
  for (const word of ['дрібняк_2', 'базарний', 'зубастий', 'якшо1', 'реальна', 'нєма', 'гонка', 'а1', 'ший', 'плюсик']) {
    const m = await map(word);
    assert.strictEqual(m[word], 'variable.other.bazar', word);
  }
  const embedded = await map('xзуб мізуб зуб_');
  assert.deepStrictEqual(Object.keys(embedded), ['xзуб', 'мізуб', 'зуб_']);
  assert.deepStrictEqual([...new Set(Object.values(embedded))], ['variable.other.bazar']);
});

test("conditions: phrases, individual words, and closing word", async () => {
  const m = await map('якшо реально реально');
  assert.deepStrictEqual((await scopes('якшо реально реально')).map((t) => t[1]), [
    'keyword.control.conditional.bazar', 'keyword.control.conditional.bazar', 'constant.language.boolean.bazar',
  ]);
  assert.ok(m);
  assert.deepStrictEqual((await scopes('а нє')).map((t) => t[1]), ['keyword.control.conditional.bazar', 'keyword.control.conditional.bazar']);
  assert.strictEqual((await map('отакої'))['отакої'], 'keyword.control.conditional.bazar');
  // standalone а or нє is not a complete condition phrase
  assert.strictEqual((await map('а'))['а'], 'variable.other.bazar');
  assert.strictEqual((await map('якшо реальне'))['реальне'], 'variable.other.bazar');
});

test("output, exit, and operators", async () => {
  assert.strictEqual((await map('базарь 1'))['базарь'], 'support.function.print.bazar');
  assert.deepStrictEqual((await scopes('всьо розходимось 0')).map((t) => t[1]),
    ['keyword.control.exit.bazar', 'keyword.control.exit.bazar', 'constant.numeric.integer.bazar']);
  const m = await map('(1 плюс 2 мінус 3 на 4 ділити на 5)');
  assert.strictEqual(m['плюс'], 'keyword.operator.arithmetic.bazar');
  assert.strictEqual(m['мінус'], 'keyword.operator.arithmetic.bazar');
  assert.strictEqual(m['на'], 'keyword.operator.arithmetic.bazar');
  assert.strictEqual(m['ділити'], 'keyword.operator.arithmetic.bazar');
  assert.strictEqual(m['('], 'punctuation.section.parens.begin.bazar');
  assert.strictEqual(m[')'], 'punctuation.section.parens.end.bazar');
  const c = await map('1 не рівно 2 більше 3 менше 4 рівно 5');
  for (const word of ['не', 'рівно', 'більше', 'менше']) assert.strictEqual(c[word], 'keyword.operator.comparison.bazar');
  const l = await map('a і ше b або c');
  assert.strictEqual(l['і'], 'keyword.operator.logical.bazar');
  assert.strictEqual(l['ше'], 'keyword.operator.logical.bazar');
  assert.strictEqual(l['або'], 'keyword.operator.logical.bazar');
});

test("comments: arbitrary text and emoji do not highlight internal keywords", async () => {
  const t = await scopes('базарь 1 чутки: зуб даю 😀 ??? " \'');
  assert.deepStrictEqual(t.map((x) => x[1]).slice(2), ['punctuation.definition.comment.bazar', 'comment.line.bazar']);
  const whole = await scopes('чутки: перевзувся 😀');
  assert.strictEqual(whole[0][1], 'punctuation.definition.comment.bazar');
  assert.strictEqual(whole[1][1], 'comment.line.bazar');
  // bare чутки or a comment-marker substring inside another word is not a comment
  assert.strictEqual((await map('чутки'))['чутки'], 'variable.other.bazar');
  assert.strictEqual((await map('мічутки: x'))['мічутки'], 'variable.other.bazar');
});

test("numbers require whole words; digits within identifiers are not numbers", async () => {
  assert.strictEqual((await map('007'))['007'], 'constant.numeric.integer.bazar');
  assert.ok(!Object.values(await map('12abc')).includes('constant.numeric.integer.bazar'));
  assert.strictEqual((await map('x2'))['x2'], 'variable.other.bazar');
});

test("Latin lookalikes are ordinary identifiers rather than keywords or strings", async () => {
  // тіпa with a final Latin a
  const m = await map('тіпa x');
  assert.strictEqual(m['тіпa'], 'variable.other.bazar');
  const all = [].concat(...await Promise.all(['зуб даю "a" \'b\''].map(scopes)));
  assert.ok(!all.some((t) => /string/.test(t[1])));
});
