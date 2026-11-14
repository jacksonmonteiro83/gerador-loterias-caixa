"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const G = require("../../dashboard/gerador.js");

const megaInfo = () => ({
  min: 1, max: 60, sorteadas: 6, aposta_min: 6, posicional: false,
  padroes_top3: ["2-2-1-1", "2-1-1-1-1", "3-1-1-1"],
  perfil: null,
});

function sequencia(valores) {
  let i = 0;
  return () => valores[i++ % valores.length];
}

test("inteiro rejeita a faixa viesada do módulo (sem viés)", () => {
  // max=3: 2^32 = 3*1431655765 + 1 -> o único valor rejeitado é 4294967295
  const uint32 = sequencia([4294967295, 7]);
  assert.equal(G.inteiro(3, uint32), 7 % 3);
});

test("inteiro valida argumentos", () => {
  assert.throws(() => G.inteiro(0), RangeError);
  assert.throws(() => G.inteiro(1.5), RangeError);
});

test("inteiro é uniforme (qui-quadrado, 10 faces, 200k lançamentos)", () => {
  const n = 200000, faces = 10, cont = new Array(faces).fill(0);
  for (let i = 0; i < n; i++) cont[G.inteiro(faces)]++;
  const esperado = n / faces;
  const qui2 = cont.reduce((s, o) => s + (o - esperado) ** 2 / esperado, 0);
  // gl = 9; p = 0.0001 -> 33.7. Falha espúria ~1e-4.
  assert.ok(qui2 < 33.7, `qui2=${qui2}`);
});

test("amostra devolve k distintos e cada dezena entra com prob. k/N", () => {
  const lista = Array.from({ length: 60 }, (_, i) => i + 1);
  const cont = new Array(61).fill(0);
  const n = 30000;
  for (let i = 0; i < n; i++) {
    const a = G.amostra(lista, 6);
    assert.equal(new Set(a).size, 6);
    for (const d of a) cont[d]++;
  }
  const p = 6 / 60, esperado = n * p, dp = Math.sqrt(n * p * (1 - p));
  for (let d = 1; d <= 60; d++) assert.ok(Math.abs(cont[d] - esperado) < 5 * dp, `dezena ${d}`);
});

test("gerarJogos: jogos distintos, ordenados e dentro do universo", () => {
  const { jogos } = G.gerarJogos(megaInfo(), 20, { estrategia: "aleatorio" });
  assert.equal(new Set(jogos.map((j) => j.dezenas.join(","))).size, 20);
  for (const { dezenas } of jogos) {
    assert.equal(dezenas.length, 6);
    assert.deepEqual([...dezenas].sort((a, b) => a - b), dezenas);
    assert.ok(dezenas.every((d) => d >= 1 && d <= 60));
  }
});

test("estratégia padrões: só devolve padrões do top 3", () => {
  const info = megaInfo();
  const perfil = { posicional: false, inicio: 1, colunas: 10 };
  const { jogos, esgotou } = G.gerarJogos(info, 50, { estrategia: "padroes", perfil });
  assert.equal(esgotou, false);
  for (const { dezenas } of jogos) {
    assert.ok(info.padroes_top3.includes(G.padraoLinhas(perfil, dezenas)));
  }
});

test("evitar datas respeita o teto de dezenas <= 31", () => {
  const info = megaInfo();
  assert.equal(G.limiteDatas(info, 6), 3);
  const { jogos } = G.gerarJogos(info, 100, { evitarDatas: true });
  for (const { dezenas } of jogos) assert.ok(G.indicePopularidade(dezenas) <= 3);
});

test("evitar datas não se aplica a universos <= 31 nem à Super Sete", () => {
  assert.equal(G.elegivelEvitarDatas({ min: 1, max: 25, posicional: false }), false);
  assert.equal(G.elegivelEvitarDatas({ min: 0, max: 9, posicional: true }), false);
  assert.equal(G.elegivelEvitarDatas({ min: 1, max: 60, posicional: false }), true);
});

test("filtro impossível esgota as tentativas e sinaliza", () => {
  const info = megaInfo();
  const perfil = {
    posicional: false, inicio: 1, colunas: 10, universo: 60, limiar: 100, maximo: 140,
    corte: { soma: [0, 0], primeiro: 1, ultimo: 1, amplitude: 0, max_linha: 1, quadrantes: 0, consecutivos: 0, repeticao: 0 },
    ideal: {}, ok: {}, criterios: [],
  };
  const r = G.gerarJogo(info, { estrategia: "aprovado", perfil });
  assert.equal(r.esgotou, true);
  assert.equal(r.tentativas, G.MAX_TENTATIVAS);
});

test("umEm: probabilidade exata do prêmio máximo", () => {
  assert.equal(G.umEm({ min: 1, max: 60, sorteadas: 6 }, 6), 50063860n);
  assert.equal(G.umEm({ min: 1, max: 60, sorteadas: 6 }, 7), 7151980n);
  assert.equal(G.umEm({ min: 1, max: 25, sorteadas: 15 }, 15), 3268760n);
  assert.equal(G.umEm({ min: 0, max: 9, sorteadas: 7, posicional: true }, 7), 10000000n);
  assert.equal(G.combinacoes(5, 2), 10n);
});

const megaRep = () => ({ ...megaInfo(), chave: "mega-sena", filtro_repetidas: true });
const anteriorMega = [5, 10, 15, 20, 25, 30];

test("repetidas: 0, 1 e 0-1 respeitam a contagem em relação ao concurso anterior", () => {
  for (const [opcao, aceitas] of [["0", [0]], ["1", [1]], ["0-1", [0, 1]]]) {
    const { jogos, esgotou } = G.gerarJogos(megaRep(), 60, { estrategia: "aleatorio", repetidas: opcao, anterior: anteriorMega });
    assert.equal(esgotou, false);
    for (const { dezenas } of jogos) {
      assert.ok(aceitas.includes(G.repetidasDoAnterior(dezenas, anteriorMega)), `${opcao}: ${dezenas}`);
    }
  }
});

test("repetidas: 'aleatorio' não restringe e modalidades sem o filtro o ignoram", () => {
  const livre = G.gerarJogos(megaRep(), 200, { repetidas: "aleatorio", anterior: anteriorMega });
  const cont = new Set(livre.jogos.map((j) => G.repetidasDoAnterior(j.dezenas, anteriorMega)));
  assert.ok(cont.size > 2, "sem filtro deve aparecer variedade de contagens");
  const lotofacil = { ...megaInfo(), max: 25, sorteadas: 15, aposta_min: 15, padroes_top3: [] };
  const r = G.gerarJogos(lotofacil, 30, { repetidas: "0", anterior: Array.from({ length: 15 }, (_, i) => i + 1) });
  assert.ok(r.jogos.some((j) => G.repetidasDoAnterior(j.dezenas, Array.from({ length: 15 }, (_, i) => i + 1)) > 0));
});

test("repetidas: com o filtro, a distribuição é a hipergeométrica condicionada (uniforme no conjunto aceito)", () => {
  // P(1 | 0 ou 1) = P(1)/(P(0)+P(1)); H(60,6,6): P0 = C(54,6)/C(60,6), P1 = 6*C(54,5)/C(60,6)
  const C = (n, k) => Number(G.combinacoes(n, k));
  const p0 = C(54, 6), p1 = 6 * C(54, 5), esperado = p1 / (p0 + p1);
  const n = 20000;
  const { jogos } = G.gerarJogos(megaRep(), n, { repetidas: "0-1", anterior: anteriorMega });
  // gerarJogos deduplica jogos: o viés é desprezível frente a 50 milhões de combinações
  const uns = jogos.filter((j) => G.repetidasDoAnterior(j.dezenas, anteriorMega) === 1).length / n;
  assert.ok(Math.abs(uns - esperado) < 0.02, `obs ${uns.toFixed(3)} esp ${esperado.toFixed(3)}`);
});

test("elegivelRepetidas: só com o flag e fora da Super Sete", () => {
  assert.equal(G.elegivelRepetidas(megaRep()), true);
  assert.equal(G.elegivelRepetidas(megaInfo()), false);
  assert.equal(G.elegivelRepetidas({ ...megaRep(), posicional: true }), false);
});
