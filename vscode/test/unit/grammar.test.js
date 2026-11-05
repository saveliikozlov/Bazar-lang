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
  const c = await map('желєзобетонно ЛІМІТ тіпа крупняк це 1');
  assert.strictEqual(c['желєзобетонно'], 'keyword.declaration.bazar');
  assert.strictEqual(c['ЛІМІТ'], 'variable.other.bazar');
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

test("loops: openers, closer, break, and range words only in a header", async () => {
  const loop = 'keyword.control.loop.bazar';
  assert.deepStrictEqual((await scopes('крутимось поки реально')).map((t) => t[1]),
    [loop, loop, 'constant.language.boolean.bazar']);
  const header = await map('крутимось к тіпа дрібняк від 1 по 10');
  assert.strictEqual(header['крутимось'], loop);
  assert.strictEqual(header['від'], loop);
  assert.strictEqual(header['по'], loop);
  assert.strictEqual((await map('докрутились'))['докрутились'], loop);
  assert.strictEqual((await map('харе'))['харе'], loop);
  // від and по are ordinary names outside a loop header
  assert.strictEqual((await map('базарь від'))['від'], 'variable.other.bazar');
  assert.strictEqual((await map('базарь по'))['по'], 'variable.other.bazar');
  assert.strictEqual((await map('крутимосьб'))['крутимосьб'], 'variable.other.bazar');
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

test("Latin lookalikes are ordinary identifiers; only double quotes make strings", async () => {
  // тіпa with a final Latin a
  const m = await map('тіпa x');
  assert.strictEqual(m['тіпa'], 'variable.other.bazar');
  const all = await scopes('зуб даю \'b\'');
  assert.ok(!all.some((t) => /string/.test(t[1])));
  assert.ok((await scopes('базарь "a"')).some((t) => /string/.test(t[1])));
});

test("Stage 2: functions, structures, strings, and read", async () => {
  const f = await map('маю дєло сума(а1 тіпа дрібняк) на виході дрібняк');
  assert.strictEqual(f['маю'], 'keyword.declaration.function.bazar');
  assert.strictEqual(f['дєло'], 'keyword.declaration.function.bazar');
  assert.strictEqual(f['на'], 'keyword.declaration.function.bazar');
  assert.strictEqual(f['виході'], 'keyword.declaration.function.bazar');
  assert.strictEqual(f['сума'], 'variable.other.bazar');
  const s = await map('такі діла Точка');
  assert.strictEqual(s['такі'], 'keyword.declaration.struct.bazar');
  assert.strictEqual(s['діла'], 'keyword.declaration.struct.bazar');
  const r = await map('тримай склепай Точка(ану кажи, 2 на 3).х');
  assert.strictEqual(r['тримай'], 'keyword.control.return.bazar');
  assert.strictEqual(r['склепай'], 'keyword.other.new.bazar');
  assert.strictEqual(r['ану'], 'support.function.read.bazar');
  assert.strictEqual(r['на'], 'keyword.operator.arithmetic.bazar');
  assert.strictEqual((await map('порішали'))['порішали'], 'keyword.declaration.bazar');
  const tokens = await scopes('базарь "чутки: не коментар \\" тут" чутки: коментар');
  assert.deepStrictEqual(tokens.find(([text]) => text.startsWith('чутки: не')), ['чутки: не коментар ', 'string.quoted.double.bazar']);
  assert.deepStrictEqual(tokens.find(([text]) => text === '\\"'), ['\\"', 'constant.character.escape.bazar']);
  assert.strictEqual(tokens[tokens.length - 1][1], 'comment.line.bazar');
});

test("arrays: types, literals, всюди, indexes, and з only in a loop header", async () => {
  const d = await scopes('мутна тєма м тіпа [дрібняк; 3] це [всюди 0]');
  const at = (text, nth = 0) => d.filter(([t]) => t === text)[nth][1];
  assert.strictEqual(at('['), 'punctuation.section.brackets.begin.bazar');
  assert.strictEqual(at(']'), 'punctuation.section.brackets.end.bazar');
  assert.strictEqual(at(';'), 'punctuation.separator.bazar');
  assert.strictEqual(at('дрібняк'), 'storage.type.bazar');
  assert.strictEqual(at('всюди'), 'keyword.other.new.bazar');
  assert.strictEqual(at('3'), 'constant.numeric.integer.bazar');
  const i = await map('базарь м[к].розмір');
  assert.strictEqual(i['м'], 'variable.other.bazar');
  assert.strictEqual(i['к'], 'variable.other.bazar');
  const loop = await map('крутимось е тіпа дрібняк з м');
  assert.strictEqual(loop['з'], 'keyword.control.loop.bazar');
  // з is an ordinary name outside a loop header
  assert.strictEqual((await map('базарь з'))['з'], 'variable.other.bazar');
  assert.strictEqual((await map('всюдиб'))['всюдиб'], 'variable.other.bazar');
});

test("може and вийде: types, values, checks, and the fallback", async () => {
  const t = await map('зуб даю р тіпа вийде дрібняк або облом крупняк це облом(404)');
  assert.strictEqual(t['вийде'], 'storage.type.bazar');
  assert.strictEqual(t['облом'], 'constant.language.variant.bazar');
  assert.strictEqual(t['або'], 'keyword.operator.logical.bazar');
  const v = await map('базарь шось(1) рівно нема або з.вийшло');
  assert.strictEqual(v['шось'], 'constant.language.variant.bazar');
  assert.strictEqual(v['нема'], 'constant.language.variant.bazar');
  assert.strictEqual(v['вийшло'], 'constant.language.variant.bazar');
  assert.strictEqual((await map('зуб даю з тіпа може дрібняк це нема'))['може'], 'storage.type.bazar');
  assert.strictEqual((await map('базарь шосьб'))['шосьб'], 'variable.other.bazar');
});

test("розбери: match words, guards, and patterns", async () => {
  const match = 'keyword.control.match.bazar';
  assert.strictEqual((await map('розбери з'))['розбери'], match);
  const arm = await map('випадок шось(х) якшо реально х більше 0');
  assert.strictEqual(arm['випадок'], match);
  assert.strictEqual(arm['шось'], 'constant.language.variant.bazar');
  assert.strictEqual(arm['якшо'], 'keyword.control.conditional.bazar');
  assert.strictEqual(arm['х'], 'variable.other.bazar');
  assert.strictEqual((await map('розібрали'))['розібрали'], match);
  assert.strictEqual((await map('розберика'))['розберика'], 'variable.other.bazar');
});

test("?: the propagation operator after calls, names, and chains", async () => {
  const tokens = await scopes('тримай шось(м.перша()? плюс з??)');
  const marks = tokens.filter(([text]) => text.includes('?'));
  assert.ok(marks.length >= 2);
  for (const [, scope] of marks) assert.strictEqual(scope, 'keyword.operator.try.bazar');
  assert.ok((await scopes('базарь "чому?"')).every(([, scope]) => scope !== 'keyword.operator.try.bazar'));
  assert.ok((await scopes('чутки: шо там?')).every(([, scope]) => scope !== 'keyword.operator.try.bazar'));
});
