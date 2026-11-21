/* Motor heurístico de pontuação e filtragem da Timemania (aposta de 10 dezenas).
 *
 * Port fiel de `TimemaniaScoringSystem` (validar_jogo_10 e validar_jogo_7) (Python) para JavaScript puro, sem
 * dependências e sem backend: roda no navegador e no Node. A versão Python de
 * referência fica em tests/ref_timemania.py e a paridade é testada em
 * tests/test_timemania_js.py (milhares de jogos, resultados idênticos).
 *
 * validarJogo10 devolve:
 *   - { all: false }                      se algum bloqueio duro (hard block) barrar o jogo;
 *   - { all, score, soma, pares, primos, quadrantes, consecutivos,
 *       rep_anterior, amplitude, padrao_linhas }   caso contrário
 *     (all = score >= THRESHOLD_10). As chaves do resultado seguem o Python.
 */
(function (raiz, fabrica) {
  if (typeof module === "object" && module.exports) module.exports = fabrica();
  else raiz.TimemaniaScoringSystem = fabrica();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  class TimemaniaScoringSystem {
    constructor() {
      this.THRESHOLD_10 = 100;
      this.THRESHOLD_7 = 85;
      this.params = {};
    }

    /** Quadrante 1..4 da malha 8x10: linhas 0-3 / 4-7 × colunas 0-4 / 5-9. */
    mapearQuadrante(n) {
      const linha = Math.floor((n - 1) / 10);
      const coluna = (n - 1) % 10;
      if (linha < 4 && coluna < 5) return 1;
      if (linha < 4 && coluna >= 5) return 2;
      if (linha >= 4 && coluna < 5) return 3;
      return 4;
    }

    /**
     * Valida e pontua um jogo de 10 dezenas contra as 7 dezenas do concurso anterior.
     * (O Python indexa jogo[i + 1] para i < 9, ou seja, exige exatamente 10 dezenas.)
     */
    validarJogo10(jogo10, jogoAnterior7) {
      if (!Array.isArray(jogo10) || jogo10.length !== 10) {
        throw new RangeError("validarJogo10 espera exatamente 10 dezenas");
      }
      const PRIMOS = TimemaniaScoringSystem.PRIMOS_TIMEMANIA;
      const jogo = [...jogo10].sort((a, b) => a - b);
      const anterior = new Set(jogoAnterior7 || []);

      const soma = jogo.reduce((s, n) => s + n, 0);
      const pares = jogo.filter((n) => n % 2 === 0).length;
      const primos = jogo.filter((n) => PRIMOS.has(n)).length;
      const repAnterior = new Set(jogo.filter((n) => anterior.has(n))).size;
      const quadrantes = new Set(jogo.map((n) => this.mapearQuadrante(n))).size;
      let consecutivos = 0;
      for (let i = 0; i < 9; i++) if (jogo[i + 1] === jogo[i] + 1) consecutivos++;

      const freqDecis = new Map();
      for (const n of jogo) {
        const decil = Math.floor((n - 1) / 10);
        freqDecis.set(decil, (freqDecis.get(decil) || 0) + 1);
      }
      const contagens = [...freqDecis.values()];
      const maxLinha = contagens.length ? Math.max(...contagens) : 0;

      const primeiroNum = jogo[0];
      const ultimoNum = jogo[jogo.length - 1];
      const amplitude = ultimoNum - primeiroNum;

      const padraoFormatado = contagens.sort((a, b) => b - a).join("-");

      // --- HARD BLOCKS (Aposta Múltipla - 10 dezenas) ---
      if (repAnterior >= 2) return { all: false };
      if (primeiroNum >= 22 || ultimoNum < 60 || amplitude < 50) return { all: false };
      if (soma < 320 || soma > 490) return { all: false };
      if (maxLinha > 4) return { all: false };
      if (quadrantes < 3) return { all: false };
      if (consecutivos >= 3) return { all: false };

      let score = 0;
      if (soma >= 350 && soma <= 460) score += 20;
      else score += 10;

      if (pares >= 4 && pares <= 6) score += 20;
      else if (pares === 3 || pares === 7) score += 10;

      if (primos >= 2 && primos <= 4) score += 20;
      else if (primos === 1 || primos === 5) score += 10;

      if (maxLinha <= 2) score += 20;
      else score += 10;

      if (quadrantes === 4) score += 20;
      else score += 10;

      if (repAnterior === 0) score += 20;
      else score += 10;

      if (consecutivos === 0) score += 20;
      else if (consecutivos === 1) score += 10;
      else score += 5;

      const aprovado = score >= this.THRESHOLD_10;
      return {
        all: aprovado,
        score,
        soma,
        pares,
        primos,
        quadrantes,
        consecutivos,
        rep_anterior: repAnterior,
        amplitude: `[${primeiroNum}-${ultimoNum}]`,
        padrao_linhas: padraoFormatado,
      };
    }

    /**
     * Valida e pontua um sorteio/jogo de 7 dezenas (usado na lista de últimos concursos).
     * Devolve sempre { all, score, status_detalhado, padrao_linhas }; nos bloqueios, score = 0.
     */
    validarJogo7(jogo7, jogoAnterior7) {
      if (!Array.isArray(jogo7) || jogo7.length !== 7) {
        throw new RangeError("validarJogo7 espera exatamente 7 dezenas");
      }
      const PRIMOS = TimemaniaScoringSystem.PRIMOS_TIMEMANIA;
      const jogo = [...jogo7].sort((a, b) => a - b);
      const anterior = new Set(jogoAnterior7 || []);

      const soma = jogo.reduce((s, n) => s + n, 0);
      const pares = jogo.filter((n) => n % 2 === 0).length;
      const primos = jogo.filter((n) => PRIMOS.has(n)).length;
      const repAnterior = new Set(jogo.filter((n) => anterior.has(n))).size;
      const quadrantes = new Set(jogo.map((n) => this.mapearQuadrante(n))).size;
      let consecutivos = 0;
      for (let i = 0; i < 6; i++) if (jogo[i + 1] === jogo[i] + 1) consecutivos++;

      const freqDecis = new Map();
      for (const n of jogo) {
        const decil = Math.floor((n - 1) / 10);
        freqDecis.set(decil, (freqDecis.get(decil) || 0) + 1);
      }
      const contagens = [...freqDecis.values()];
      const maxLinha = contagens.length ? Math.max(...contagens) : 0;
      const linhasAtivas = freqDecis.size;

      const primeiroNum = jogo[0];
      const ultimoNum = jogo[jogo.length - 1];
      const amplitude = ultimoNum - primeiroNum;
      const padraoFormatado = contagens.sort((a, b) => b - a).join("-");

      const rej = (detalhe) => ({
        all: false,
        score: 0,
        status_detalhado: `REJ (0pts: ${detalhe})`,
        padrao_linhas: padraoFormatado,
      });
      if (repAnterior >= 2) return rej(`REP_ANT(${repAnterior})`);
      if (primeiroNum >= 22 || ultimoNum < 60 || amplitude < 50) return rej(`EXTREMOS[${primeiroNum}-${ultimoNum}]`);
      if (soma < 195 || soma > 375) return rej(`SOMA(${soma})`);
      if (maxLinha > 3) return rej(`ELIMINADO_LINHA(${maxLinha})`);
      if (linhasAtivas === 7 && maxLinha === 1) return rej("ELIMINADO_ESPALHAMENTO_TOTAL");
      if (quadrantes < 3) return rej(`QUADRANTES(${quadrantes})`);
      if (consecutivos >= 3) return rej(`CONSECUTIVOS(${consecutivos})`);

      let score = 0;
      const falhas = [];

      if (soma >= 230 && soma <= 340) score += 20;
      else score += 10;

      if (pares === 3 || pares === 4) score += 20;
      else if (pares === 2 || pares === 5) score += 10;
      else falhas.push(`PARES(${pares})`);

      if (primos === 2 || primos === 3) score += 20;
      else if (primos === 1 || primos === 4) score += 10;
      else falhas.push(`PRIMOS(${primos})`);

      if (maxLinha <= 2) score += 20;
      else score += 10;

      if (quadrantes === 4) score += 20;
      else score += 10;

      if (repAnterior === 0) score += 20;
      else score += 10;

      if (consecutivos === 0) score += 20;
      else if (consecutivos === 1) score += 10;
      else score += 5;

      const aprovado = score >= this.THRESHOLD_7;
      const motivo = aprovado ? `APROV (${score}pts)` : `REJ (${score}pts: ${falhas.join("/")})`;
      return { all: aprovado, score, status_detalhado: motivo, padrao_linhas: padraoFormatado };
    }
  }

  TimemaniaScoringSystem.PRIMOS_TIMEMANIA = new Set([
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41,
    43, 47, 53, 59, 61, 67, 71, 73, 79,
  ]);

  return TimemaniaScoringSystem;
});
