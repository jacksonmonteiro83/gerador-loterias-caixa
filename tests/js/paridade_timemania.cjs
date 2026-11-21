// Lê {casos: [{jogo, anterior}]} do stdin e imprime o resultado de validarJogo10 de cada um.
const TimemaniaScoringSystem = require("../../dashboard/timemania.js");
const t = new TimemaniaScoringSystem();
let entrada = "";
process.stdin.on("data", (c) => (entrada += c));
process.stdin.on("end", () => {
  const { casos } = JSON.parse(entrada);
  process.stdout.write(JSON.stringify(casos.map((c) => t.validarJogo10(c.jogo, c.anterior))));
});
