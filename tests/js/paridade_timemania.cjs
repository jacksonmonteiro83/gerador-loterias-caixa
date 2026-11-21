// Lê {casos: [{jogo, anterior}]} do stdin e imprime validarJogo10 (10 dezenas) ou validarJogo7 (7 dezenas) de cada um.
const TimemaniaScoringSystem = require("../../dashboard/timemania.js");
const t = new TimemaniaScoringSystem();
let entrada = "";
process.stdin.on("data", (c) => (entrada += c));
process.stdin.on("end", () => {
  const { casos } = JSON.parse(entrada);
  process.stdout.write(JSON.stringify(casos.map((c) => (c.jogo.length === 7 ? t.validarJogo7(c.jogo, c.anterior) : t.validarJogo10(c.jogo, c.anterior)))));
});
