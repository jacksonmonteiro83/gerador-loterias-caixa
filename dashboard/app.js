/* Dashboard estático das Loterias Caixa.
 *
 * Todo o cálculo estatístico é pré-computado em Python (scripts/export_dashboard.py,
 * testado contra scipy). Aqui só se desenha e se geram jogos, então cada
 * modalidade é um JSON pequeno baixado sob demanda.
 */
(() => {
  "use strict";

  const G = window.Gerador;
  const NS = "http://www.w3.org/2000/svg";

  /* ---------- utilidades ---------- */

  const $ = (sel, raiz = document) => raiz.querySelector(sel);

  function el(tag, opts = {}, ...filhos) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(opts)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const f of filhos) if (f) node.append(f);
    return node;
  }

  function svg(tag, attrs = {}, ...filhos) {
    const node = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    for (const f of filhos) if (f) node.append(f);
    return node;
  }

  const dec = (x, casas = 1) =>
    Number(x).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });
  const fmt = (n) => Number(n).toLocaleString("pt-BR");
  const pct = (x, casas = 1) => `${dec(x, casas)}%`;
  const fmtP = (p) => (p < 0.001 ? "<0,001" : dec(p, 3));
  const fmtData = (iso) => {
    if (!iso) return "—";
    const [a, m, d] = iso.split("-");
    return `${d}/${m}/${a}`;
  };
  const rotuloBola = (v, posicional) => (posicional ? String(v) : String(v).padStart(2, "0"));
  const limpar = (no) => { no.replaceChildren(); return no; };

  const estado = { indice: null, cache: new Map(), atual: null, dados: null, metrica: "freq", token: 0, ultimosJogos: [] };

  /* ---------- carregamento ---------- */

  function mostrarEstado(texto, { erro = false, tentar = null } = {}) {
    const alvo = $("#estado");
    limpar(alvo);
    alvo.className = `estado${erro ? " erro" : ""}${texto ? "" : " vazio"}`;
    alvo.setAttribute("role", erro ? "alert" : "status");
    if (!texto) return;
    alvo.append(el("span", { text: texto }));
    if (tentar) {
      const b = el("button", { type: "button", class: "btn btn-sec", text: "Tentar de novo" });
      b.addEventListener("click", tentar);
      alvo.append(b);
    }
  }

  async function buscarJSON(url, opcoes) {
    const resposta = await fetch(url, opcoes);
    if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
    return resposta.json();
  }

  async function iniciar() {
    mostrarEstado("Carregando dados…");
    try {
      // revalida com o servidor (ETag) em vez de ignorar o cache por completo
      estado.indice = await buscarJSON("data/index.json", { cache: "no-cache" });
    } catch (erro) {
      $("#atualizado").textContent = "Falha ao carregar";
      mostrarEstado(`Não foi possível carregar os dados (${erro.message}).`, { erro: true, tentar: iniciar });
      return;
    }
    const indice = estado.indice;
    $("#atualizado").textContent = `Gerado em ${fmtData(indice.gerado_em)}`;
    $("#rodape-data").textContent = fmtData(indice.gerado_em);
    const total = Object.values(indice.loterias).reduce((s, l) => s + l.n, 0);
    $("#total-concursos").textContent = `${fmt(total)} concursos no histórico`;
    montarTabs();
    montarControles();
    const inicial = location.hash.slice(1);
    abrir(indice.loterias[inicial] ? inicial : Object.keys(indice.loterias)[0]);
  }

  async function abrir(chave) {
    const token = ++estado.token;
    estado.atual = chave;
    for (const b of $("#tabs").querySelectorAll("button")) {
      const ativo = b.dataset.chave === chave;
      b.setAttribute("aria-selected", ativo ? "true" : "false");
      b.tabIndex = ativo ? 0 : -1;
    }
    if (location.hash.slice(1) !== chave) history.replaceState(null, "", `#${chave}`);
    const meta = estado.indice.loterias[chave];
    $("#painel").setAttribute("aria-busy", "true");
    $("#painel").setAttribute("aria-labelledby", `tab-${chave}`);

    let dados = estado.cache.get(chave);
    if (!dados) {
      mostrarEstado(`Carregando ${meta.nome}…`);
      try {
        const versao = meta.ultimo && meta.ultimo.n ? `?v=${meta.ultimo.n}-${estado.indice.gerado_em}` : "";
        dados = await buscarJSON(`${meta.arquivo}${versao}`);
        estado.cache.set(chave, dados);
      } catch (erro) {
        if (token !== estado.token) return;
        mostrarEstado(`Não foi possível carregar ${meta.nome} (${erro.message}).`, { erro: true, tentar: () => abrir(chave) });
        return;
      }
    }
    if (token !== estado.token) return; // o usuário já trocou de modalidade
    estado.dados = dados;
    mostrarEstado("");
    renderizar(dados);
    $("#painel").setAttribute("aria-busy", "false");
  }

  function montarTabs() {
    const nav = limpar($("#tabs"));
    const chaves = Object.keys(estado.indice.loterias);
    for (const chave of chaves) {
      const botao = el("button", {
        type: "button", role: "tab", id: `tab-${chave}`, "data-chave": chave,
        "aria-controls": "painel", "aria-selected": "false", tabindex: "-1",
        text: estado.indice.loterias[chave].nome,
      });
      botao.addEventListener("click", () => abrir(chave));
      botao.addEventListener("keydown", (ev) => {
        const i = chaves.indexOf(chave);
        let alvo = null;
        if (ev.key === "ArrowRight") alvo = chaves[(i + 1) % chaves.length];
        else if (ev.key === "ArrowLeft") alvo = chaves[(i - 1 + chaves.length) % chaves.length];
        else if (ev.key === "Home") alvo = chaves[0];
        else if (ev.key === "End") alvo = chaves[chaves.length - 1];
        if (alvo) { ev.preventDefault(); abrir(alvo); $(`#tab-${alvo}`).focus(); }
      });
      nav.append(botao);
    }
    window.addEventListener("hashchange", () => {
      const h = location.hash.slice(1);
      if (estado.indice.loterias[h] && h !== estado.atual) abrir(h);
    });
  }

  function montarControles() {
    $(".toggle").addEventListener("click", (ev) => {
      const botao = ev.target.closest("button[data-metrica]");
      if (!botao) return;
      estado.metrica = botao.dataset.metrica;
      for (const b of $(".toggle").querySelectorAll("button")) {
        b.setAttribute("aria-pressed", b === botao ? "true" : "false");
      }
      desenharFrequencia(visaoUltimos(estado.dados));
    });
    $("#tabela-freq").addEventListener("toggle", (ev) => {
      if (ev.target.open) montarTabelaFrequencia(visaoUltimos(estado.dados));
    });
    $("#form-gerador").addEventListener("submit", (ev) => { ev.preventDefault(); gerarJogos(); });
    $("#copiar").addEventListener("click", copiarJogos);
  }

  /* ---------- gráficos SVG ---------- */

  const W = 720, H = 210, MARGEM = { e: 38, d: 8, t: 10, b: 24 };

  function eixoY(maximo, escala) {
    const passo = maximo / 2;
    return [0, passo, maximo].map((v) => ({ v, y: escala(v) }));
  }

  /**
   * Barras com referência: linha de esperado, faixa central opcional e limites.
   * cfg: { valores, rotulos, titulos, esperado, banda, limites:[{valor, rotulo, classe}], fora(i), descricao }
   */
  function graficoBarras(cfg) {
    const n = cfg.valores.length;
    const referencias = [cfg.esperado, cfg.maximoExtra, ...(cfg.banda || []), ...(cfg.limites || []).map((l) => l.valor)].filter((v) => v != null);
    const maximo = Math.max(1, ...cfg.valores, ...referencias) * 1.08;
    const larguraUtil = W - MARGEM.e - MARGEM.d;
    const alturaUtil = H - MARGEM.t - MARGEM.b;
    const y = (v) => MARGEM.t + alturaUtil * (1 - v / maximo);
    const passoX = larguraUtil / n;
    const larguraBarra = Math.max(2, passoX * 0.78);

    const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": cfg.descricao, class: "svg-grafico" });
    for (const t of eixoY(maximo, y)) {
      s.append(svg("line", { x1: MARGEM.e, x2: W - MARGEM.d, y1: t.y, y2: t.y, class: "grade" }));
      const rotulo = svg("text", { x: MARGEM.e - 5, y: t.y + 3, class: "eixo-txt", "text-anchor": "end" });
      rotulo.textContent = fmt(Math.round(t.v * 10) / 10);
      s.append(rotulo);
    }
    if (cfg.banda) {
      s.append(svg("rect", {
        x: MARGEM.e, width: larguraUtil, y: y(cfg.banda[1]), height: Math.max(0, y(cfg.banda[0]) - y(cfg.banda[1])), class: "banda",
      }));
    }
    cfg.valores.forEach((v, i) => {
      const x = MARGEM.e + i * passoX + (passoX - larguraBarra) / 2;
      const alto = Math.max(1, alturaUtil * (v / maximo));
      const barra = svg("rect", {
        x: x.toFixed(2), y: (MARGEM.t + alturaUtil - alto).toFixed(2), width: larguraBarra.toFixed(2), height: alto.toFixed(2),
        class: `barra${cfg.fora && cfg.fora(i) ? " fora" : ""}`,
      });
      const titulo = svg("title");
      titulo.textContent = cfg.titulos[i];
      barra.append(titulo);
      s.append(barra);
    });
    if (cfg.esperado != null) {
      s.append(svg("line", { x1: MARGEM.e, x2: W - MARGEM.d, y1: y(cfg.esperado), y2: y(cfg.esperado), class: "ref-esperado" }));
    }
    for (const l of cfg.limites || []) {
      s.append(svg("line", { x1: MARGEM.e, x2: W - MARGEM.d, y1: y(l.valor), y2: y(l.valor), class: l.classe }));
    }
    const passoRotulo = Math.max(1, Math.ceil(n / 20));
    cfg.rotulos.forEach((r, i) => {
      if (i % passoRotulo !== 0 && i !== n - 1) return;
      const t = svg("text", { x: MARGEM.e + i * passoX + passoX / 2, y: H - 8, class: "eixo-txt", "text-anchor": "middle" });
      t.textContent = r;
      s.append(t);
    });
    return s;
  }

  function graficoHistograma(bins, descricao) {
    const esperados = bins.map((b) => b.esp);
    const observados = bins.map((b) => b.obs);
    // a escala do eixo Y precisa cobrir também os pontos esperados
    const grafico = graficoBarras({
      valores: observados,
      rotulos: bins.map((b) => String(b.ini)),
      titulos: bins.map((b) => `${b.ini}–${b.fim}: ${b.obs} observados · ${dec(b.esp, 1)} esperados`),
      maximoExtra: Math.max(...esperados),
      descricao,
    });
    const n = bins.length;
    const maximo = Math.max(1, ...observados, ...esperados) * 1.08;
    const passoX = (W - MARGEM.e - MARGEM.d) / n;
    const alturaUtil = H - MARGEM.t - MARGEM.b;
    const pts = esperados.map((v, i) => [
      MARGEM.e + i * passoX + passoX / 2,
      MARGEM.t + alturaUtil * (1 - v / maximo),
    ]);
    grafico.append(svg("polyline", { points: pts.map((p) => p.join(",")).join(" "), class: "linha-esp" }));
    for (const [cx, cy] of pts) grafico.append(svg("circle", { cx, cy, r: 3, class: "ponto-esp" }));
    return grafico;
  }

  function heatmap(d) {
    const { colunas, freq_ref: ref, n } = d;
    const p = 1 / (d.max - d.min + 1);
    const dp = Math.sqrt(n * p * (1 - p));
    const grade = el("div", { class: "heat", role: "img", "aria-label": `Frequência de cada dígito por coluna em ${fmt(n)} concursos; esperado ${dec(ref.esperado, 1)} por célula` });
    grade.style.gridTemplateColumns = `34px repeat(${colunas.length}, 1fr)`;
    grade.append(el("div"));
    colunas.forEach((_, i) => grade.append(el("div", { class: "cab", text: `C${i + 1}` })));
    for (let dig = d.min; dig <= d.max; dig++) {
      grade.append(el("div", { class: "eixo", text: String(dig) }));
      colunas.forEach((col) => {
        const valor = col[dig - d.min];
        const z = dp > 0 ? (valor - ref.esperado) / dp : 0;
        const intensidade = Math.min(1, Math.abs(z) / 3);
        const cel = el("div", { class: `cel${Math.abs(z) > 1.96 ? " destaque-z" : ""}`, text: String(valor) });
        const cor = z >= 0 ? "74, 158, 255" : "255, 184, 77";
        cel.style.background = `rgba(${cor}, ${(0.06 + intensidade * 0.6).toFixed(2)})`;
        cel.title = `${valor} aparições · esperado ${dec(ref.esperado, 1)} · z = ${dec(z, 2)}`;
        grade.append(cel);
      });
    }
    return grade;
  }

  function linhaBarra({ rotulo, rotuloExtra, obs, esp, maximo, texto, titulo }) {
    const trilho = el("div", { class: "trilho" });
    trilho.append(el("div", { class: "preench" }));
    trilho.firstChild.style.width = `${Math.min(100, (obs / maximo) * 100)}%`;
    if (esp != null) {
      const marca = el("span", { class: "ref", "aria-hidden": "true" });
      marca.style.left = `${Math.min(100, (esp / maximo) * 100)}%`;
      trilho.append(marca);
    }
    const nome = el("span", { class: "rot" }, document.createTextNode(rotulo));
    if (rotuloExtra) nome.append(el("em", { class: "tag-top", text: rotuloExtra }));
    const linha = el("div", { class: "linha-barra", title: titulo }, nome, trilho, el("b", { text: texto }));
    return linha;
  }

  /* ---------- seções ---------- */

  function renderizar(d) {
    document.title = `${d.nome} — Loterias Caixa`;
    $("#nota-loteria").textContent = d.nota || "";
    renderAvisos(d);
    if (d.vazio) { renderVazio(d); return; }
    renderHero(d);
    renderStats(d);
    const v = visaoUltimos(d);
    desenharFrequencia(v);
    desenharSoma(v);
    desenharRepeticao(v);
    renderPadroes(v);
    renderScore(d);
    prepararGerador(d);
  }

  /**
   * Visão dos painéis de frequência, soma, repetição e padrões: só os últimos
   * concursos (d.ultimos). O atraso continua sendo o atual, medido no histórico completo.
   */
  function visaoUltimos(d) {
    const u = d.ultimos;
    if (!u) return d;
    return { ...d, ...u, n: u.n, janela: true };
  }

  function renderVazio(d) {
    for (const id of ["#ultimo-bolas", "#stats", "#grafico-freq", "#histograma-soma", "#barras-repeticao", "#barras-padroes", "#score-lista", "#jogos"]) {
      limpar($(id));
    }
    $("#ultimo-numero").textContent = "—";
    $("#ultimo-data").textContent = "sem dados";
    mostrarEstado(`Ainda não há histórico de ${d.nome}.`);
  }

  function renderAvisos(d) {
    const alvo = limpar($("#avisos"));
    const msgs = [];
    if (d.vazio) msgs.push("Sem concursos carregados para esta modalidade.");
    else {
      if (!d.completo) {
        msgs.push(
          `Histórico incompleto: ${fmt(d.n)} concursos carregados (do nº ${fmt(d.primeiro.n)} ao ${fmt(d.ultimo.n)}); ` +
          `faltam ${fmt(d.faltantes)}. As estatísticas valem para esta janela e os intervalos de confiança são mais largos.`
        );
      } else if (d.n < 500) {
        msgs.push(`Amostra pequena (${fmt(d.n)} concursos): desvios aparentes têm pouco valor estatístico.`);
      }
    }
    for (const m of msgs) alvo.append(el("p", { class: "banner", role: "note", text: m }));
  }

  function renderHero(d) {
    const u = d.ultimo;
    $("#ultimo-rotulo").textContent = d.posicional ? "Último concurso · dígito por coluna" : "Último concurso";
    $("#ultimo-numero").textContent = `#${fmt(u.n)}`;
    $("#ultimo-data").textContent = fmtData(u.d);
    const bolas = limpar($("#ultimo-bolas"));
    for (const v of u.z) bolas.append(el("span", { class: `bola${d.posicional ? " azul" : ""}`, text: rotuloBola(v, d.posicional) }));
  }

  function cartao(rotulo, valor, ref) {
    return el("div", { class: "stat" }, el("span", { text: rotulo }), el("b", { text: valor }), ref ? el("small", { text: ref }) : null);
  }

  function renderStats(d) {
    const alvo = limpar($("#stats"));
    alvo.append(
      cartao("Concursos", fmt(d.n)),
      cartao("Período", `${fmtData(d.primeiro.d)} – ${fmtData(d.ultimo.d)}`),
      cartao("Soma média", dec(d.soma.media_obs, 1), `esperada ${dec(d.soma.media_esp, 1)}`),
      cartao(d.posicional ? "Dígitos pares" : "Pares por jogo", dec(d.pares.media_obs, 2), `esperado ${dec(d.pares.media_esp, 2)}`),
      cartao("Dezenas", d.posicional ? `${d.sorteadas} colunas` : `${d.sorteadas} de ${d.min}–${d.max}`),
      cartao(d.posicional ? "Colunas repetidas" : "Repetição média",
        d.repeticao.media_obs == null ? "—" : dec(d.repeticao.media_obs, 2), `esperada ${dec(d.repeticao.media_esp, 2)}`),
    );
  }

  function desenharFrequencia(d) {
    if (!d || d.vazio) return;
    const alvo = limpar($("#grafico-freq"));
    const legenda = $("#legenda-freq");
    const toggle = $(".toggle");
    toggle.hidden = d.posicional;
    $("#tabela-freq").hidden = false;
    $("#tabela-freq").open = false;

    if (d.posicional) {
      alvo.append(heatmap(d));
      const r = d.freq_ref;
      legenda.textContent =
        `Últimos ${fmt(d.n)} concursos: contagem de cada dígito por coluna; esperado ${dec(r.esperado, 1)} por célula. ` +
        `Azul = acima, laranja = abaixo (intensidade ∝ |z|); borda = |z| > 1,96. ` +
        `${r.fora_banda} de ${d.sorteadas * (d.max - d.min + 1)} células fora da faixa de 95% (≈ ${dec(r.fora_banda_esperado, 0)} só por acaso).`;
      return;
    }

    const rotulos = Array.from({ length: d.max - d.min + 1 }, (_, i) => String(d.min + i).padStart(2, "0"));
    if (estado.metrica === "atraso") {
      const ref = d.atraso_ref;
      const grafico = graficoBarras({
        valores: d.atraso, rotulos,
        titulos: d.atraso.map((a, i) => `${rotulos[i]}: ${a} concursos sem sair · P(atraso ≥ ${a}) = ${fmtP(ref.cauda[i])}`),
        esperado: ref.media_esperada,
        limites: [{ valor: ref.p95, rotulo: "p95", classe: "ref-limite" }],
        fora: (i) => d.atraso[i] >= ref.p95,
        descricao: `Atraso de cada dezena (concursos desde a última aparição). Média esperada ${dec(ref.media_esperada, 1)}; percentil 95: ${ref.p95}.`,
      });
      alvo.append(grafico);
      legenda.textContent =
        `Atraso atual (concursos desde a última aparição, contado no histórico completo). Linha tracejada = média esperada (${dec(ref.media_esperada, 1)}); linha pontilhada = percentil 95 (${ref.p95}). ` +
        `${ref.acima_p95} de ${d.max - d.min + 1} dezenas estão acima do p95 (≈ ${dec(ref.acima_p95_esperado, 1)} só por acaso). ` +
        `Dezena "atrasada" não é mais provável: a chance de sair é sempre ${d.sorteadas}/${d.max - d.min + 1}.`;
      return;
    }
    const ref = d.freq_ref;
    alvo.append(graficoBarras({
      valores: d.freq, rotulos,
      titulos: d.freq.map((f, i) => `${rotulos[i]}: ${f} aparições (esperado ${dec(ref.esperado, 1)})`),
      esperado: ref.esperado, banda: ref.banda,
      fora: (i) => d.freq[i] < ref.banda[0] || d.freq[i] > ref.banda[1],
      descricao: `Frequência de cada dezena nos últimos ${d.n} concursos. Esperado ${dec(ref.esperado, 1)}; faixa de 95%: ${dec(ref.banda[0], 1)} a ${dec(ref.banda[1], 1)}.`,
    }));
    legenda.textContent =
      `Últimos ${fmt(d.n)} concursos · linha tracejada = esperado (${dec(ref.esperado, 1)}) · faixa sombreada = intervalo de 95% ao acaso (${dec(ref.banda[0], 1)}–${dec(ref.banda[1], 1)}). ` +
      `${ref.fora_banda} de ${d.max - d.min + 1} dezenas ficam fora (≈ ${dec(ref.fora_banda_esperado, 1)} só por acaso).`;
  }

  function montarTabelaFrequencia(d) {
    const alvo = limpar($("#tabela-freq-corpo"));
    if (!d || d.vazio) return;
    const tabela = el("table", { class: "tabela" });
    const cab = el("tr");
    if (d.posicional) {
      cab.append(el("th", { scope: "col", text: "Dígito" }));
      d.colunas.forEach((_, i) => cab.append(el("th", { scope: "col", text: `C${i + 1}` })));
      tabela.append(el("thead", {}, cab));
      const corpo = el("tbody");
      for (let dig = d.min; dig <= d.max; dig++) {
        const tr = el("tr", {}, el("th", { scope: "row", text: String(dig) }));
        d.colunas.forEach((c) => tr.append(el("td", { text: String(c[dig - d.min]) })));
        corpo.append(tr);
      }
      tabela.append(corpo);
    } else {
      for (const t of ["Dezena", "Frequência", "Atraso", "P(atraso ≥ observado)"]) cab.append(el("th", { scope: "col", text: t }));
      tabela.append(el("thead", {}, cab));
      const corpo = el("tbody");
      d.freq.forEach((f, i) => corpo.append(el("tr", {},
        el("th", { scope: "row", text: String(d.min + i).padStart(2, "0") }),
        el("td", { text: String(f) }), el("td", { text: String(d.atraso[i]) }), el("td", { text: fmtP(d.atraso_ref.cauda[i]) }))));
      tabela.append(corpo);
    }
    alvo.append(tabela);
  }

  function desenharSoma(d) {
    const s = d.soma;
    limpar($("#histograma-soma")).append(graficoHistograma(s.bins,
      `Distribuição da soma das dezenas: barras observadas, pontos esperados. Média observada ${s.media_obs}, esperada ${s.media_esp}.`));
    $("#legenda-soma").textContent =
      `Últimos ${fmt(d.n)} concursos. Barras = observado; pontos = esperado exato (n × P). Média ${dec(s.media_obs, 1)} (esperada ${dec(s.media_esp, 1)}); ` +
      `desvio-padrão ${dec(s.dp_obs, 1)} (esperado ${dec(s.dp_esp, 1)}). Faixas de ${s.bins[0].fim - s.bins[0].ini + 1} unidades.`;
  }

  function desenharRepeticao(d) {
    const r = d.repeticao;
    const alvo = limpar($("#barras-repeticao"));
    const total = Math.max(1, r.pares);
    const obsPct = r.obs.map((v) => (100 * v) / total);
    const espPct = r.esp.map((v) => (100 * v) / total);
    const maximo = Math.max(1, ...obsPct, ...espPct) * 1.05;
    r.obs.forEach((_, i) => {
      if (obsPct[i] === 0 && espPct[i] < 0.05) return; // oculta caudas vazias
      const rotulo = d.posicional ? `${i} coluna${i === 1 ? "" : "s"}` : `${i} dezena${i === 1 ? "" : "s"}`;
      alvo.append(linhaBarra({
        rotulo, obs: obsPct[i], esp: espPct[i], maximo,
        texto: `${pct(obsPct[i])} (esp. ${pct(espPct[i])})`,
        titulo: `${r.obs[i]} de ${r.pares} pares de concursos · esperado ${dec(r.esp[i], 1)}`,
      }));
    });
    $("#legenda-rep").textContent = d.posicional
      ? `Últimos ${fmt(r.pares)} concursos comparados ao anterior. Colunas cujo dígito repete o do concurso anterior. Barra = observado; traço = esperado (binomial, p = 0,1). Média ${dec(r.media_obs, 2)} (esperada ${dec(r.media_esp, 2)}).`
      : `Últimos ${fmt(r.pares)} concursos comparados ao anterior. Dezenas que repetem do concurso anterior. Barra = observado; traço = esperado (hipergeométrica). Média ${dec(r.media_obs, 2)} (esperada ${dec(r.media_esp, 2)}).`;
  }

  function renderPadroes(d) {
    const alvo = limpar($("#barras-padroes"));
    const kpi = limpar($("#padrao-kpi"));
    const legenda = $("#legenda-padroes");
    if (d.posicional || !d.padroes || !d.padroes.length) {
      legenda.textContent = "Na Super Sete cada coluna sorteia um dígito: padrão de linha não se aplica.";
      return;
    }
    kpi.append(el("span", { text: `${fmt(d.padroes_distintos)} padrões possíveis` }));
    const maximo = Math.max(1, ...d.padroes.map((p) => Math.max(p.percentual, p.esperado_pct))) * 1.05;
    d.padroes.forEach((p, i) => {
      alvo.append(linhaBarra({
        rotulo: p.padrao, rotuloExtra: i < 3 ? "top 3" : "", obs: p.percentual, esp: p.esperado_pct, maximo,
        texto: `${pct(p.percentual)} (esp. ${pct(p.esperado_pct)})`,
        titulo: `${p.quantidade} concursos · z = ${dec(p.z, 2)}`,
      }));
    });
    legenda.textContent =
      `Últimos ${fmt(d.n)} concursos. Distribuição das ${d.sorteadas} dezenas pelas ${d.linhas} linhas de ${d.colunas_malha} colunas. Barra = observado; traço = esperado ao acaso. ` +
      `Um padrão é frequente porque ocupa mais combinações do espaço, não porque o sorteio o prefira: o top 3 cobre ${pct(d.padroes_top3_observado_pct)} dos concursos ` +
      `contra ${pct(d.padroes_top3_esperado_pct)} esperados.`;
  }

  function renderScore(d) {
    const perfil = d.perfil;
    const kpi = limpar($("#score-kpi"));
    const lista = limpar($("#score-lista"));
    if (!perfil) return;
    kpi.append(
      el("span", {}, document.createTextNode("limiar "), el("b", { text: String(perfil.limiar) }), document.createTextNode(`/${perfil.maximo}`)),
    );
    if (perfil.fonte !== "nulo") {
      kpi.append(el("span", {}, document.createTextNode("aprovam "), el("b", { text: pct(perfil.aderencia) })));
    } else {
      kpi.append(el("span", {}, document.createTextNode("ao acaso "), el("b", { text: pct(perfil.taxa_nominal) })));
    }
    listarScores(d, lista);
  }

  function textoRepetidas(d, c, forma) {
    if (c.r == null) return "—";
    const unidade = d.posicional ? ["coluna", "colunas"] : ["dezena", "dezenas"];
    const plural = c.r === 1 ? 0 : 1;
    return forma === "curto"
      ? `${c.r} repetida${plural ? "s" : ""}`
      : `${c.r} ${unidade[plural]} repetida${plural ? "s" : ""} em relação ao concurso anterior`;
  }

  function listarScores(d, lista) {
    for (const c of [...d.recentes].reverse()) {
      const tipico = Boolean(c.a);
      const bolas = el("div", { class: "bolas" });
      for (const v of c.z) bolas.append(el("span", { class: `bola peq${d.posicional ? " azul" : ""}`, text: rotuloBola(v, d.posicional) }));
      lista.append(el("div", { class: "score-linha" },
        el("span", { class: "score-concurso", text: `#${fmt(c.n)}` }),
        bolas,
        el("div", { class: "score-meta" },
          el("span", { class: "score-badge", title: textoRepetidas(d, c, "longo"), text: textoRepetidas(d, c, "curto") }),
          el("span", { class: `score-badge ${tipico ? "ok" : "neutro"}`, text: `${c.s} pts` }),
          el("span", { class: "score-detalhe", text: c.p ? `padrão ${c.p}` : `soma ${c.z.reduce((s, v) => s + v, 0)}` }),
          el("span", { class: "score-status", text: tipico ? "típico" : "atípico" }),
        ),
      ));
    }
  }

  /* ---------- gerador ---------- */

  function perfilDoJogo(d) { return d.perfil_aposta || d.perfil; }

  function prepararGerador(d) {
    const tamanho = d.aposta_min;
    const select = $("#estrategia");
    const opPadroes = select.querySelector('option[value="padroes"]');
    const padroesOk = !d.posicional && d.padroes_top3 && d.padroes_top3.length > 0 && tamanho === d.sorteadas;
    opPadroes.disabled = !padroesOk;
    if (!padroesOk && select.value === "padroes") select.value = "aleatorio";
    if (padroesOk && !estado.escolheuMetodo) select.value = "padroes";
    select.onchange = () => { estado.escolheuMetodo = true; };
    const repOk = G.elegivelRepetidas(d);
    $("#rotulo-repetidas").hidden = !repOk;
    $("#repetidas").hidden = !repOk;
    if (!repOk) $("#repetidas").value = "aleatorio";
    const elegivel = G.elegivelEvitarDatas(d);
    $("#rotulo-evitar-datas").hidden = !elegivel;
    if (!elegivel) $("#evitar-datas").checked = false;
    limpar($("#jogos"));
    $("#copiar").hidden = true;
    estado.ultimosJogos = [];
    const chance = G.umEm(d, tamanho);
    $("#legenda-gerador").textContent =
      `Jogo de ${tamanho} dezenas. Chance de acertar todas as dezenas sorteadas: 1 em ${chance.toLocaleString("pt-BR")} — igual para qualquer combinação. ` +
      `Os filtros usam amostragem com rejeição (uniforme dentro das combinações aceitas); "evitar datas" é só uma heurística de rateio.` +
      (repOk ? ` "Repetidas do anterior" fixa quantas dezenas do jogo também saíram no concurso #${fmt(d.ultimo.n)} (que teve ${d.sorteadas} dezenas); em "Aleatório" não há restrição.` : "");
  }

  function gerarJogos() {
    const d = estado.dados;
    if (!d || d.vazio) return;
    const quantidade = Math.min(20, Math.max(1, Number($("#qtd").value) || 1));
    $("#qtd").value = String(quantidade);
    const perfil = perfilDoJogo(d);
    const opcoes = {
      estrategia: $("#estrategia").value,
      evitarDatas: $("#evitar-datas").checked,
      repetidas: $("#repetidas").value,
      anterior: d.ultimo.z,
      perfil,
      tamanho: d.aposta_min,
    };
    const { jogos, esgotou } = G.gerarJogos(d, quantidade, opcoes);
    const alvo = limpar($("#jogos"));
    const top3 = new Set(d.padroes_top3 || []);
    estado.ultimosJogos = jogos.map((j) => j.dezenas);

    for (const { dezenas } of jogos) {
      const soma = dezenas.reduce((s, v) => s + v, 0);
      const pares = dezenas.filter((v) => v % 2 === 0).length;
      const linha = el("div", { class: "jogo" });
      const bolas = el("div", { class: "bolas" });
      for (const v of dezenas) bolas.append(el("span", { class: `bola${d.posicional ? " azul" : ""}`, text: rotuloBola(v, d.posicional) }));
      const rep = G.elegivelRepetidas(d) ? ` · ${G.repetidasDoAnterior(dezenas, d.ultimo.z)} rep.` : "";
      linha.append(bolas, el("span", { class: "tag", text: `soma ${soma} · ${pares} par(es)${rep}` }));
      if (!d.posicional) {
        const padrao = G.padraoLinhas(perfil, dezenas);
        const nota = d.aposta_min === d.sorteadas ? (top3.has(padrao) ? " · top 3" : " · fora do top 3") : "";
        linha.append(el("span", { class: "score-badge neutro", text: `padrão ${padrao}${nota}` }));
      }
      const r = G.pontuarJogo(perfil, dezenas, d.ultimo.z);
      linha.append(el("span", { class: `score-badge ${r.aprovado ? "ok" : "neutro"}`, title: r.status, text: `${r.score} pts · ${r.aprovado ? "típico" : "atípico"}` }));
      alvo.append(linha);
    }
    $("#copiar").hidden = false;
    if (esgotou) {
      alvo.append(el("p", { class: "banner", role: "note", text: "Os filtros escolhidos são restritivos demais: alguns jogos foram gerados sem satisfazê-los." }));
    }
  }

  async function copiarJogos() {
    const d = estado.dados;
    const texto = estado.ultimosJogos.map((j) => j.map((v) => rotuloBola(v, d.posicional)).join(d.posicional ? " " : " ")).join("\n");
    try {
      await navigator.clipboard.writeText(texto);
      mostrarEstado("Jogos copiados.");
      setTimeout(() => { if ($("#estado").textContent === "Jogos copiados.") mostrarEstado(""); }, 2500);
    } catch (_) {
      mostrarEstado("Não foi possível copiar automaticamente; selecione os jogos manualmente.", { erro: true });
    }
  }

  iniciar();
})();
