/* Lógica pura do gerador e do score (sem DOM): testável em Node e no navegador.
 *
 * - Aleatoriedade: crypto.getRandomValues com rejeição (sem viés de módulo),
 *   embaralhamento parcial de Fisher-Yates.
 * - Filtros por amostragem com rejeição: o resultado é UNIFORME dentro do
 *   conjunto de jogos aceitos (a heurística anterior de montar o jogo linha a
 *   linha não era uniforme dentro da classe).
 * - Nenhum filtro altera a chance de acerto de um jogo; só muda o conjunto de
 *   combinações elegíveis.
 */
(function (raiz, fabrica) {
  if (typeof module === "object" && module.exports) module.exports = fabrica();
  else raiz.Gerador = fabrica();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const LIMITE_DATA = 31;
  const MAX_TENTATIVAS = 5000;

  /* ---------- aleatoriedade ---------- */

  /** Fonte padrão: uint32 criptográfico (navegador e Node >= 19). */
  function uint32Cripto() {
    const buf = new Uint32Array(1);
    globalThis.crypto.getRandomValues(buf);
    return buf[0];
  }

  /** Inteiro uniforme em [0, max) sem viés de módulo (rejeição). */
  function inteiro(max, uint32 = uint32Cripto) {
    if (!Number.isInteger(max) || max <= 0 || max > 0x100000000) {
      throw new RangeError("max deve estar em 1..2^32");
    }
    const limite = Math.floor(0x100000000 / max) * max;
    let x = uint32();
    while (x >= limite) x = uint32();
    return x % max;
  }

  /** k elementos distintos e uniformes de `lista` (Fisher-Yates parcial). */
  function amostra(lista, k, uint32 = uint32Cripto) {
    if (k > lista.length) throw new RangeError("k maior que a lista");
    const copia = lista.slice();
    for (let i = 0; i < k; i++) {
      const j = i + inteiro(copia.length - i, uint32);
      [copia[i], copia[j]] = [copia[j], copia[i]];
    }
    return copia.slice(0, k);
  }

  /* ---------- métricas e score (espelha src/core/scoring.py) ---------- */

  const ehPrimo = (n) => {
    if (n < 2) return false;
    for (let i = 2; i * i <= n; i++) if (n % i === 0) return false;
    return true;
  };
  const PRIMOS = new Set(Array.from({ length: 99 }, (_, i) => i + 2).filter(ehPrimo));
  const METRICA = { linhas: "max_linha", concentracao: "max_digito" };

  const somar = (v) => v.reduce((s, x) => s + x, 0);

  /** Blocos (quadrantes) da malha: ceil(linhas/2) x ceil(colunas/2). */
  function quadrantesMalha(perfil) {
    const universo = perfil.universo;
    const colunas = perfil.colunas;
    const linhas = Math.ceil(universo / colunas);
    const meioL = Math.ceil(linhas / 2);
    const meioC = Math.ceil(colunas / 2);
    const blocos = [];
    for (const [l0, l1] of [[0, meioL], [meioL, linhas]]) {
      for (const [c0, c1] of [[0, meioC], [meioC, colunas]]) {
        const bloco = new Set();
        for (let i = l0; i < l1; i++) {
          for (let j = c0; j < c1; j++) {
            const indice = i * colunas + j;
            if (indice < universo) bloco.add(perfil.inicio + indice);
          }
        }
        blocos.push(bloco);
      }
    }
    return blocos;
  }

  const cacheBlocos = new WeakMap();
  function blocosDe(perfil) {
    if (!cacheBlocos.has(perfil)) cacheBlocos.set(perfil, quadrantesMalha(perfil));
    return cacheBlocos.get(perfil);
  }

  function assinatura(contagem) {
    return [...contagem.values()].sort((a, b) => b - a).join("-");
  }

  function padraoLinhas(perfil, dezenas) {
    if (perfil.posicional) return "";
    const contagem = new Map();
    for (const d of dezenas) {
      const linha = Math.floor((d - perfil.inicio) / perfil.colunas);
      contagem.set(linha, (contagem.get(linha) || 0) + 1);
    }
    return assinatura(contagem);
  }

  function metricasJogo(perfil, dezenas, anterior) {
    const valores = dezenas.map(Number);
    const soma = somar(valores);
    const pares = valores.filter((v) => v % 2 === 0).length;
    const primos = new Set(valores.filter((v) => PRIMOS.has(v))).size;
    if (perfil.posicional) {
      const contagem = new Map();
      for (const v of valores) contagem.set(v, (contagem.get(v) || 0) + 1);
      const repeticao = anterior ? valores.filter((v, i) => v === anterior[i]).length : 0;
      return {
        soma, pares, primos,
        max_digito: Math.max(0, ...contagem.values()),
        repeticao,
        padrao_linhas: assinatura(contagem),
      };
    }
    const contagem = new Map();
    for (const d of valores) {
      const linha = Math.floor((d - perfil.inicio) / perfil.colunas);
      contagem.set(linha, (contagem.get(linha) || 0) + 1);
    }
    const cobertos = blocosDe(perfil).filter((b) => valores.some((d) => b.has(d))).length;
    const ordenado = [...valores].sort((a, b) => a - b);
    let consecutivos = 0;
    for (let i = 1; i < ordenado.length; i++) if (ordenado[i] === ordenado[i - 1] + 1) consecutivos++;
    const ant = new Set(anterior || []);
    return {
      soma, pares, primos,
      max_linha: Math.max(0, ...contagem.values()),
      quadrantes: cobertos,
      consecutivos,
      repeticao: valores.filter((d) => ant.has(d)).length,
      primeiro: ordenado[0] || 0,
      ultimo: ordenado[ordenado.length - 1] || 0,
      amplitude: ordenado.length ? ordenado[ordenado.length - 1] - ordenado[0] : 0,
      padrao_linhas: assinatura(contagem),
    };
  }

  function bloqueioRigido(perfil, m) {
    const c = perfil.corte || {};
    if (m.soma < c.soma[0] || m.soma > c.soma[1]) return `SOMA(${m.soma})`;
    if (!perfil.posicional) {
      if (m.primeiro > c.primeiro || m.ultimo < c.ultimo) return `EXTREMOS[${m.primeiro}-${m.ultimo}]`;
      if (m.amplitude < c.amplitude) return `AMPLITUDE(${m.amplitude})`;
      if (m.max_linha > c.max_linha) return `CONCENTRACAO_LINHA(${m.max_linha})`;
      if (m.quadrantes < c.quadrantes) return `QUADRANTES(${m.quadrantes})`;
      if (m.consecutivos > c.consecutivos) return `CONSECUTIVOS(${m.consecutivos})`;
    }
    if (m.repeticao > c.repeticao) return `REP_ANTERIOR(${m.repeticao})`;
    return null;
  }

  /** Score de tipicidade (0..perfil.maximo). Não mede chance de acerto. */
  function pontuarJogo(perfil, dezenas, anterior) {
    const m = metricasJogo(perfil, dezenas, anterior);
    const bloqueio = bloqueioRigido(perfil, m);
    if (bloqueio) return { score: 0, aprovado: false, status: `REJ (0pts: ${bloqueio})`, metricas: m };

    let score = 0;
    const falhas = [];
    for (const criterio of perfil.criterios) {
      const valor = m[METRICA[criterio] || criterio];
      const ideal = perfil.ideal[criterio];
      const ok = perfil.ok[criterio];
      if (ideal && valor >= ideal[0] && valor <= ideal[1]) score += 20;
      else if (ok && valor >= ok[0] && valor <= ok[1]) score += 10;
      else if (!perfil.posicional && criterio !== "pares" && criterio !== "primos") score += 5;
      else falhas.push(`${criterio.toUpperCase()}(${valor})`);
    }
    const aprovado = score >= perfil.limiar;
    return {
      score, aprovado, metricas: m,
      status: aprovado ? `APROV (${score}pts)` : `REJ (${score}pts: ${falhas.join("/") || "FORA_DAS_FAIXAS"})`,
    };
  }

  /* ---------- geração ---------- */

  function sorteioAleatorio(info, tamanho, uint32) {
    if (info.posicional) {
      return Array.from({ length: info.sorteadas }, () => inteiro(10, uint32));
    }
    const universo = [];
    for (let d = info.min; d <= info.max; d++) universo.push(d);
    return amostra(universo, tamanho, uint32).sort((a, b) => a - b);
  }

  /** Índice de popularidade: nº de dezenas <= 31 (datas de aniversário). */
  const indicePopularidade = (dezenas) => dezenas.filter((d) => d <= LIMITE_DATA).length;

  /** Limite de dezenas <= 31 aceito pelo filtro "evitar datas": piso do esperado ao acaso. */
  function limiteDatas(info, tamanho) {
    const universo = info.max - info.min + 1;
    return Math.floor((tamanho * LIMITE_DATA) / universo);
  }

  const elegivelEvitarDatas = (info) => !info.posicional && info.max - info.min + 1 > LIMITE_DATA;

  /**
   * Gera um jogo por amostragem com rejeição.
   * opcoes: { estrategia: "aleatorio"|"padroes"|"aprovado", evitarDatas, anterior,
   *           perfil, tamanho, uint32 }
   * Devolve { dezenas, tentativas, esgotou }.
   */
  function gerarJogo(info, opcoes = {}) {
    const tamanho = opcoes.tamanho || info.aposta_min || info.sorteadas;
    const perfil = opcoes.perfil || info.perfil;
    const top3 = new Set(info.padroes_top3 || []);
    const usarPadroes = opcoes.estrategia === "padroes" && !info.posicional && top3.size > 0 && tamanho === info.sorteadas;
    const usarScore = opcoes.estrategia === "aprovado" && perfil;
    const evitar = Boolean(opcoes.evitarDatas) && elegivelEvitarDatas(info);
    const teto = evitar ? limiteDatas(info, tamanho) : Infinity;

    let ultimo = null;
    for (let t = 1; t <= MAX_TENTATIVAS; t++) {
      const dezenas = sorteioAleatorio(info, tamanho, opcoes.uint32);
      ultimo = dezenas;
      if (usarPadroes && !top3.has(padraoLinhas(perfil, dezenas))) continue;
      if (evitar && indicePopularidade(dezenas) > teto) continue;
      if (usarScore && !pontuarJogo(perfil, dezenas, opcoes.anterior).aprovado) continue;
      return { dezenas, tentativas: t, esgotou: false };
    }
    return { dezenas: ultimo, tentativas: MAX_TENTATIVAS, esgotou: true };
  }

  /** Gera `quantidade` jogos distintos entre si. */
  function gerarJogos(info, quantidade, opcoes = {}) {
    const vistos = new Set();
    const jogos = [];
    let esgotou = false;
    for (let i = 0; i < quantidade; i++) {
      let r = null;
      for (let repeticao = 0; repeticao < 50; repeticao++) {
        r = gerarJogo(info, opcoes);
        if (!vistos.has(r.dezenas.join(","))) break;
      }
      vistos.add(r.dezenas.join(","));
      esgotou = esgotou || r.esgotou;
      jogos.push(r);
    }
    return { jogos, esgotou };
  }

  /* ---------- probabilidade (exata, BigInt) ---------- */

  function combinacoes(n, k) {
    if (k < 0 || k > n) return 0n;
    let r = 1n;
    for (let i = 1n; i <= BigInt(k); i++) r = (r * (BigInt(n) - BigInt(k) + i)) / i;
    return r;
  }

  /** Denominador N de "1 em N" para acertar TODAS as dezenas sorteadas com um jogo de tamanho m. */
  function umEm(info, tamanho) {
    if (info.posicional) return 10n ** BigInt(info.sorteadas);
    const universo = info.max - info.min + 1;
    const casos = combinacoes(universo, info.sorteadas);
    const meus = combinacoes(tamanho, info.sorteadas);
    return meus === 0n ? 0n : (casos + meus / 2n) / meus;
  }

  return {
    inteiro, amostra, metricasJogo, pontuarJogo, padraoLinhas, quadrantesMalha,
    gerarJogo, gerarJogos, indicePopularidade, limiteDatas, elegivelEvitarDatas,
    combinacoes, umEm, MAX_TENTATIVAS, LIMITE_DATA,
  };
});
