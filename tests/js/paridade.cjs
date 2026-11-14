"use strict";
// Lê {perfil, jogos:[{dezenas, anterior}]} do stdin e imprime os scores do JS.
const G = require("../../dashboard/gerador.js");
let entrada = "";
process.stdin.on("data", (c) => (entrada += c));
process.stdin.on("end", () => {
  const { perfil, jogos } = JSON.parse(entrada);
  const saida = jogos.map(({ dezenas, anterior }) => {
    const r = G.pontuarJogo(perfil, dezenas, anterior);
    return { score: r.score, aprovado: r.aprovado, status: r.status };
  });
  process.stdout.write(JSON.stringify(saida));
});
