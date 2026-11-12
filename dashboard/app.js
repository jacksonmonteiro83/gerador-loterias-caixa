/* Dashboard estático das Loterias Caixa — sem dependências. */
(() => {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const el = (tag, cls, html) => {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (html !== undefined) node.innerHTML = html;
    return node;
  };
  const fmt = (n) => n.toLocaleString("pt-BR");
  const fmtData = (iso) => {
    if (!iso) return "—";
    const [a, m, d] = iso.split("-");
    return `${d}/${m}/${a}`;
  };
  const media = (arr) => (arr.length ? arr.reduce((s, v) => s + v, 0) / arr.length : 0);

  const estado = { dados: null, atual: "mega-sena", metrica: "freq" };

  /* ---------- carregamento ---------- */

  async function iniciar() {
    try {
      const resposta = await fetch("data.json", { cache: "no-store" });
      if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
      estado.dados = await resposta.json();
    } catch (erro) {
      $("#hero").innerHTML = `<p class="legenda">Não foi possível carregar <code>data.json</code> (${erro.message}). Rode <code>python scripts/export_dashboard.py</code>.</p>`;
      return;
    }
    montarTabs();
    $("#atualizado").textContent = `Gerado em ${fmtData(estado.dados.gerado_em)}`;
    const total = Object.values(estado.dados.loterias).reduce((s, l) => s + l.concursos.length, 0);
    $("#total-concursos").textContent = `${fmt(total)} concursos no histórico`;
    $("#rodape-data").textContent = fmtData(estado.dados.gerado_em);
    renderizar();
  }

  function montarTabs() {
    const nav = $("#tabs");
    nav.innerHTML = "";
    for (const [chave, info] of Object.entries(estado.dados.loterias)) {
      const botao = el("button", "", info.nome);
      botao.type = "button";
      botao.setAttribute("role", "tab");
      botao.setAttribute("aria-selected", chave === estado.atual ? "true" : "false");
      botao.addEventListener("click", () => {
        estado.atual = chave;
        for (const b of nav.querySelectorAll("button")) b.setAttribute("aria-selected", "false");
        botao.setAttribute("aria-selected", "true");
        renderizar();
      });
      nav.appendChild(botao);
    }
    document.querySelector(".toggle").addEventListener("click", (evento) => {
      const botao = evento.target.closest("button[data-metrica]");
      if (!botao) return;
      estado.metrica = botao.dataset.metrica;
      for (const b of document.querySelectorAll(".toggle button")) b.classList.toggle("ativo", b === botao);
      desenharFrequencia();
    });
    $("#gerar").addEventListener("click", gerarJogos);
  }

  /* ---------- dados derivados ---------- */

  function derivar(info) {
    const concursos = info.concursos;
    const universo = info.max - info.min + 1;
    const ultimo = concursos[concursos.length - 1] || null;

    const somas = concursos.map((c) => c.z.reduce((s, v) => s + v, 0));
    const pares = concursos.map((c) => c.z.filter((v) => v % 2 === 0).length);
    const repeticoes = [];
    for (let i = 1; i < concursos.length; i++) {
      const anterior = new Set(concursos[i - 1].z);
      repeticoes.push(concursos[i].z.filter((v) => anterior.has(v)).length);
    }

    let freq = null;
    let atrasos = null;
    let colunas = null;

    if (info.posicional) {
      colunas = Array.from({ length: info.sorteadas }, () => new Array(10).fill(0));
      for (const c of concursos) c.z.forEach((v, i) => { if (colunas[i]) colunas[i][v]++; });
    } else {
      freq = new Map();
      for (let d = info.min; d <= info.max; d++) freq.set(d, 0);
      for (const c of concursos) for (const d of c.z) freq.set(d, (freq.get(d) || 0) + 1);
      atrasos = new Map();
      for (let d = info.min; d <= info.max; d++) {
        let atraso = concursos.length;
        for (let i = concursos.length - 1; i >= 0; i--) {
          if (concursos[i].z.includes(d)) { atraso = concursos.length - 1 - i; break; }
        }
        atrasos.set(d, atraso);
      }
    }

    return { universo, ultimo, somas, pares, repeticoes, freq, atrasos, colunas };
  }

  /* ---------- render ---------- */

  function renderizar() {
    const info = estado.dados.loterias[estado.atual];
    const d = derivar(info);
    $("#nota-loteria").textContent = info.nota || "";
    renderHero(info, d);
    renderStats(info, d);
    desenharFrequencia(info, d);
    desenharSoma(info, d);
    desenharRepeticao(info, d);
    $("#jogos").innerHTML = "";
  }

  function bolas(dezenas, posicional) {
    const wrap = el("div", "bolas");
    dezenas.forEach((v) => {
      const b = el("span", `bola${posicional ? " azul" : ""}`, String(v).padStart(2, "0"));
      if (posicional) b.textContent = String(v);
      wrap.appendChild(b);
    });
    return wrap;
  }

  function renderHero(info, d) {
    const u = d.ultimo;
    $("#ultimo-rotulo").textContent = info.posicional ? "Último concurso · dígitos por coluna" : "Último concurso";
    $("#ultimo-numero").textContent = u ? `#${fmt(u.n)}` : "—";
    $("#ultimo-data").textContent = u ? fmtData(u.d) : "sem dados";
    const alvo = $("#ultimo-bolas");
    alvo.innerHTML = "";
    if (u) alvo.appendChild(bolas(u.z, info.posicional));
  }

  function renderStats(info, d) {
    const n = info.concursos.length;
    const primeiro = info.concursos[0];
    const ultimo = d.ultimo;
    const cartoes = [
      ["Concursos", fmt(n)],
      ["Período", `${fmtData(primeiro?.d)} – ${fmtData(ultimo?.d)}`],
      ["Soma média", n ? Math.round(media(d.somas)) : "—"],
      ["Pares por jogo", n ? media(d.pares).toFixed(1) : "—"],
      ["Dezenas", info.posicional ? `${info.sorteadas} colunas` : `${info.sorteadas} de ${info.min}–${info.max}`],
      ["Repetição média", info.posicional ? "—" : d.repeticoes.length ? media(d.repeticoes).toFixed(1) : "—"],
    ];
    const alvo = $("#stats");
    alvo.innerHTML = "";
    for (const [rotulo, valor] of cartoes) {
      const cartao = el("div", "stat", `<span>${rotulo}</span><b>${valor}</b>`);
      alvo.appendChild(cartao);
    }
  }

  function desenharFrequencia(info, d) {
    const alvo = $("#grafico-freq");
    alvo.innerHTML = "";
    alvo.className = "grafico-freq";
    alvo.style.display = info.posicional ? "block" : "flex";

    if (info.posicional) {
      desenharHeat(info, d, alvo);
      $("#legenda-freq").textContent = "Acertos de cada dígito por coluna nos últimos concursos.";
      return;
    }

    const n = info.concursos.length;
    const esperado = n ? (n * info.sorteadas) / d.universo : 0;
    const usarAtraso = estado.metrica === "atraso";
    const valores = usarAtraso
      ? [...d.atrasos.entries()]
      : [...d.freq.entries()];
    const maximo = Math.max(1, ...valores.map(([, v]) => v));
    const passo = Math.ceil(valores.length / 22);

    for (const [dezena, valor] of valores) {
      const col = el("div", "col");
      if (!usarAtraso && valor >= esperado * 1.15) col.classList.add("quente");
      const barra = el("div", "barra");
      barra.style.height = `${Math.max(2, (valor / maximo) * 100)}%`;
      barra.title = `${dezena}: ${usarAtraso ? `${valor} concursos sem sair` : `${valor} aparições`}`;
      col.appendChild(barra);
      const rotulo = el("small", "", String(dezena).padStart(2, "0"));
      if (dezena % passo !== 0 && dezena !== info.max) rotulo.style.visibility = "hidden";
      col.appendChild(rotulo);
      alvo.appendChild(col);
    }

    $("#legenda-freq").textContent = usarAtraso
      ? "Concursos desde a última aparição de cada dezena (maior = mais atrasada)."
      : `${n} concursos · frequência média esperada ${esperado.toFixed(1)} por dezena · barras verdes acima de 15% da média.`;
  }

  function desenharHeat(info, d, alvo) {
    const maximo = Math.max(1, ...d.colunas.flat());
    const grade = el("div", "heat");
    grade.appendChild(el("div"));
    for (let c = 1; c <= info.sorteadas; c++) grade.appendChild(el("div", "cab", `C${c}`));
    for (let digito = 0; digito <= 9; digito++) {
      grade.appendChild(el("div", "eixo", String(digito)));
      d.colunas.forEach((contagem) => {
        const valor = contagem[digito];
        const intensidade = 0.08 + (valor / maximo) * 0.6;
        const cel = el("div", "cel", String(valor));
        cel.style.background = `rgba(74, 158, 255, ${intensidade.toFixed(2)})`;
        cel.title = `${valor} aparições`;
        grade.appendChild(cel);
      });
    }
    alvo.classList.remove("grafico-freq");
    alvo.classList.add("grafico-heat");
    alvo.appendChild(grade);
    alvo.style.display = "block";
  }

  function desenharSoma(info, d) {
    const alvo = $("#histograma-soma");
    alvo.innerHTML = "";
    const somas = d.somas;
    if (!somas.length) return;
    const min = Math.min(...somas);
    const max = Math.max(...somas);
    const faixas = 12;
    const largura = Math.max(1, Math.ceil((max - min + 1) / faixas));
    const baldes = new Array(faixas).fill(0);
    somas.forEach((s) => {
      const indice = Math.min(faixas - 1, Math.floor((s - min) / largura));
      baldes[indice]++;
    });
    const pico = Math.max(1, ...baldes);
    baldes.forEach((qtd, i) => {
      const col = el("div", "col");
      const barra = el("div", "barra");
      barra.style.height = `${Math.max(2, (qtd / pico) * 100)}%`;
      const inicio = min + i * largura;
      barra.title = `${inicio}–${inicio + largura - 1}: ${qtd} sorteios`;
      col.appendChild(barra);
      if (i % 2 === 0) col.appendChild(el("small", "", String(inicio)));
      alvo.appendChild(col);
    });
    $("#legenda-soma").textContent = `Soma típica entre ${min} e ${max}; média ${Math.round(media(somas))}.`;
  }

  function desenharRepeticao(info, d) {
    const alvo = $("#barras-repeticao");
    alvo.innerHTML = "";
    if (info.posicional) {
      alvo.innerHTML = "<p class='legenda'>Na Super Sete o conceito de repetição é por coluna, não por conjunto de dezenas.</p>";
      return;
    }
    const contagem = new Map();
    d.repeticoes.forEach((r) => contagem.set(r, (contagem.get(r) || 0) + 1));
    const maximo = Math.max(1, ...contagem.values());
    const total = d.repeticoes.length || 1;
    [...contagem.entries()].sort((a, b) => a[0] - b[0]).forEach(([qtd, vezes]) => {
      const linha = el("div", "linha-barra");
      linha.appendChild(el("span", "", `${qtd} dezena${qtd === 1 ? "" : "s"}`));
      const trilho = el("div", "trilho");
      const preench = el("div", "preench");
      preench.style.width = `${(vezes / maximo) * 100}%`;
      trilho.appendChild(preench);
      linha.appendChild(trilho);
      linha.appendChild(el("b", "", `${Math.round((vezes / total) * 100)}%`));
      alvo.appendChild(linha);
    });
  }

  /* ---------- gerador ---------- */

  function sorteio(info) {
    if (info.posicional) return Array.from({ length: info.sorteadas }, () => Math.floor(Math.random() * 10));
    const universo = [];
    for (let d = info.min; d <= info.max; d++) universo.push(d);
    for (let i = universo.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [universo[i], universo[j]] = [universo[j], universo[i]];
    }
    return universo.slice(0, info.sorteadas).sort((a, b) => a - b);
  }

  function gerarJogos() {
    const info = estado.dados.loterias[estado.atual];
    const quantidade = Math.min(20, Math.max(1, Number($("#qtd").value) || 1));
    const alvo = $("#jogos");
    alvo.innerHTML = "";
    for (let i = 0; i < quantidade; i++) {
      const dezenas = sorteio(info);
      const soma = dezenas.reduce((s, v) => s + v, 0);
      const pares = dezenas.filter((v) => v % 2 === 0).length;
      const linha = el("div", "jogo");
      linha.appendChild(bolas(dezenas, info.posicional));
      linha.appendChild(el("span", "tag", `soma ${soma} · ${pares} par(es)`));
      alvo.appendChild(linha);
    }
  }

  iniciar();
})();
