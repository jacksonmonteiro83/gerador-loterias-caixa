# Gerador de Jogos — Loterias Caixa

Gerador e analisador de jogos para as oito modalidades das Loterias Caixa, com
validação das regras oficiais, filtros matemáticos configuráveis e histórico
persistido em SQLite.

> **Aviso:** ferramenta estatística e educacional. Nenhum filtro aumenta a
> probabilidade matemática de acerto — todos os jogos válidos têm a mesma chance.
> Jogue com responsabilidade. Proibido para menores de 18 anos.

---

## Modalidades suportadas

| Modalidade | Universo | Dezenas sorteadas | Aposta (mín–máx) |
|---|---|---|---|
| Mega-Sena | 1–60 | 6 | 6–20 |
| Lotofácil | 1–25 | 15 | 15–20 |
| Quina | 1–80 | 5 | 5–15 |
| Lotomania | 1–100 | 20 | 50 (fixo) |
| Timemania | 1–80 | 10 | 10 (fixo) |
| Dupla Sena | 1–50 | 6 | 6–15 |
| Dia de Sorte | 1–31 | 7 | 7–15 |
| Super Sete | 7 colunas × 0–9 | 7 dígitos | 7 (fixo) |

---

## Arquitetura

```
.
├── main.py                  # CLI e teste de integração das 8 modalidades
├── requirements.txt
├── docs/
│   └── CONTRATO.md          # interface normativa entre os módulos
├── data/
│   └── loterias.db          # gerado em runtime (fora do Git)
├── src/
│   ├── core/                # motor genérico
│   │   ├── models.py        # LotterySpec, LotteryConfig, FiltroConfig
│   │   ├── filters.py       # pares, primos, moldura/miolo, soma, quadrantes
│   │   ├── stats.py         # frequência, atraso, repetição, contaminação
│   │   └── base_lottery.py  # LotteryBase (validação + geração)
│   ├── loterias/            # uma classe por modalidade
│   │   ├── mega_sena.py  lotofacil.py  quina.py  lotomania.py
│   │   ├── timemania.py  dupla_sena.py  dia_de_sorte.py  super_sete.py
│   │   └── registry.py      # LOTERIAS, get_loteria(), criar()
│   ├── etl/                 # coleta do histórico
│   │   ├── scraper.py       # cliente HTTP (Caixa + fallback)
│   │   └── loader.py        # download → validação → SQLite
│   └── utils/
│       └── db.py            # schema, upsert e leitura para DataFrame
└── tests/
```

Fluxo: `etl` baixa e grava em SQLite → `utils.db.carregar_df` devolve um
DataFrame → `core` calcula métricas e gera jogos → `loterias` aplica o spec de
cada modalidade.

---

## Instalação

```bash
git clone https://github.com/<seu-usuario>/gerador-loterias-caixa.git
cd gerador-loterias-caixa
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Requer Python 3.10+ (testado em 3.12).

---

## Uso

```bash
# demonstração de integração: valida, filtra e gera 3 jogos de cada modalidade
python main.py

# uma modalidade específica
python main.py --loteria mega-sena --jogos 5 --seed 42

# atualizar o histórico a partir da Caixa (incremental)
python main.py --atualizar

# usar histórico sintético (sem rede)
python main.py --offline --loteria lotofacil --jogos 10

# filtros e restrições
python main.py --loteria mega-sena --jogos 5 \
  --pares 3-3 --primos 2-4 --moldura 3-5 --soma 150-250 --quadrante-min 1 \
  --fixas 10,23 --excluidas 4,13 --repetidas 2 --contaminacao 4

# tabela de score dos últimos concursos
python main.py --loteria timemania --score --ultimos 12

# gerar exigindo score mínimo (ou desligar o filtro)
python main.py --loteria mega-sena --jogos 5 --score-min 125
python main.py --loteria mega-sena --jogos 5 --sem-score

# padrões de linha: top 3 automático, top 5 ou lista explícita
python main.py --loteria quina --jogos 5 --padroes top3
python main.py --loteria quina --jogos 5 --padroes 2-1-1-1,1-1-1-1-1
python main.py --loteria quina --jogos 5 --sem-padroes

# tabela de regras oficiais / saída JSON
python main.py --regras
python main.py --offline --json
```

Opções: `--loteria`, `--jogos`, `--dezenas`, `--seed`, `--offline`, `--db`,
`--atualizar`, `--regras`, `--json`, `--sem-restricoes`; filtros `--pares`,
`--impares`, `--primos`, `--moldura`, `--miolo`, `--soma`, `--quadrante-min`,
`--quadrante-max` (faixa `min-max`); histórico `--fixas`, `--excluidas`,
`--repetidas`, `--contaminacao`; score `--score`, `--ultimos`, `--score-min`,
`--sem-score`; padrões `--padroes`, `--sem-padroes`.

### Como biblioteca

```python
from src.core.models import LotteryConfig, FiltroConfig
from src.loterias.registry import criar
from src.utils.db import carregar_df

historico = carregar_df("mega-sena")

cfg = LotteryConfig(
    qtd_jogos=5,
    dezenas_por_jogo=6,
    filtros=FiltroConfig(
        pares=(3, 3),          # exatamente 3 pares
        primos=(2, 4),
        moldura=(3, 5),
        soma=(150, 250),
        quadrante_min=1,       # cada quadrante com pelo menos 1 dezena
    ),
    dezenas_fixas=[10, 23],
    dezenas_excluidas=[4, 13],
    repetidas_concurso_anterior=2,
    contaminacao_maxima=4,
    seed=42,
)

loteria = criar("mega-sena", config=cfg, historico=historico)
for jogo in loteria.gerar():
    print(sorted(jogo), loteria.analisar(jogo)["soma"])
```

### Score adaptativo

O port do modelo da Timemania virou um motor genérico: cada modalidade calibra
suas faixas e cortes sobre o próprio histórico (percentis), em vez de usar os
valores fixos pensados para 1–80 com 7 dezenas.

- **Jogos de conjunto**: 7 critérios × 20 pts = **140 pts** — soma, pares,
  primos, concentração por linha, cobertura de quadrantes, repetição do concurso
  anterior e consecutivos.
- **Super Sete (posicional)**: 5 critérios × 20 pts = **100 pts** — soma, pares,
  primos, repetição por coluna e concentração de dígitos.
- Antes da pontuação há **blocos rígidos** (soma fora da faixa histórica,
  extremos, amplitude, linha concentrada, quadrantes vazios, consecutivos e
  repetição acima do corte). Um jogo que cai em qualquer bloco recebe 0 pts.
- A nota de corte é o **percentil 65 dos scores históricos** (aprox. 35% dos
  concursos passam), limitada a 70–125 (conjunto) ou 45–90 (posicional).
- Lotomania (aposta de 50 dezenas, sorteio de 20) e Timemania (aposta de 10,
  sorteio de 7) usam um perfil por tamanho de jogo.
- Na CLI o filtro de score é automático **apenas** quando não há restrições de
  histórico (fixas, excluídas, repetidas ou contaminação); `--score-min` força
  um valor e `--sem-score` desliga.

O score mede aderência ao padrão histórico; **não** aumenta a probabilidade
matemática de acerto.

```python
resultado = loteria.pontuar(jogo)
print(resultado["score"], resultado["status"], resultado["metricas"])
perfil = loteria.perfil_score
print(perfil.limiar, perfil.aderencia, perfil.ideal)
```

### Padrões de linha

A assinatura de **padrão de linha** é como as dezenas se distribuem pelas linhas
da malha: na Quina, `2-1-1-1` significa 2 dezenas na 1ª linha (1–10) e 1 em cada
outra. No histórico recente da Quina esse padrão cai em **55% dos concursos** —
os concentrados (`3-1-1`, `4-1`, tudo numa linha) somam pouco:

- Na CLI, `--padroes top3` (ou `top5`, ou uma lista `2-1-1-1,1-1-1-1-1`) filtra a
  geração para jogos cuja distribuição está entre os padrões mais frequentes.
  Sem a flag, o **top 3 automático** entra quando não há restrições de histórico
  e cobre ao menos 50% dos concursos; `--sem-padroes` desliga.
- O resumo da CLI mostra os padrões permitidos com a frequência histórica e a
  cobertura (`padrões permitidos: 2-1-1-1 (55.0%) · ... · cobertura 91.0%`), e
  cada jogo sai com `padrao=2-1-1-1`.
- O filtro vale apenas para jogos do **tamanho do sorteio** e modalidades de
  conjunto: Lotomania (aposta 50 × sorteio 20) e Timemania (aposta 10 × sorteio
  7 real) ficam sem filtro de padrão; Super Sete é posicional e não se aplica.
- No **dashboard**, o card em destaque "Padrões que mais caem" mostra o padrão
  líder, as barras de frequência e os padrões excluídos; o gerador tem a
  opção "só padrões top 3" (amostragem ponderada pela frequência histórica) e
  cada jogo recebe o selo `padrão` — verde no top 3, âmbar fora.

```python
tabela = loteria.padroes_frequentes     # [{padrao, quantidade, percentual}, ...]
assinatura = loteria.padrao_linhas(jogo)  # "2-1-1-1"
cobertura = loteria.padroes_cobertura     # % de concursos cobertos pelo filtro
```

### Filtros

| Filtro | Campo | Descrição |
|---|---|---|
| Pares / Ímpares | `pares`, `impares` | faixa `(min, max)` de quantidade |
| Primos | `primos` | primos no jogo |
| Moldura / Miolo | `moldura`, `miolo` | borda e interior da malha de `spec.colunas` colunas |
| Soma | `soma` | soma total das dezenas |
| Quadrantes | `quadrante_min`, `quadrante_max` | mínimo/máximo por quadrante da malha |

### Parâmetros de histórico

| Parâmetro | Efeito |
|---|---|
| `dezenas_fixas` | dezenas obrigatórias em todo jogo |
| `dezenas_excluidas` | dezenas proibidas |
| `repetidas_concurso_anterior` | quantidade exata de dezenas repetidas do último concurso |
| `max_repetidas` | teto de repetição em relação ao último concurso |
| `contaminacao_maxima` | sobreposição máxima permitida com **qualquer** concurso do histórico |

---

## Banco de dados

Arquivo `data/loterias.db` com as tabelas:

- `concursos(loteria, concurso, data, dezenas, premiacoes, acumulado)` — chave primária `(loteria, concurso)`; `dezenas` em JSON.
- `meta(loteria, ultimo_concurso, atualizado_em)` — controle incremental do ETL.

O ETL é incremental: baixa apenas concursos posteriores ao `ultimo_concurso`.
Se a rede falhar, cai no modo `offline-sintetico`, que gera histórico de teste —
esse modo **não** representa resultados reais.

Fontes: o endpoint oficial da Caixa
(`servicebus2.caixa.gov.br/portaldeloterias/api`) para sete modalidades e a API
espelho `loteriascaixa-api.herokuapp.com/api` para a **Super Sete**, cujo caminho
no serviço oficial responde 500 (não publicado). A API espelho devolve a lista
do concurso mais novo para o mais antigo; por isso o ETL escolhe o maior número
de concurso ao descobrir o último publicado.

---

## Dashboard público

**https://jacksonmonteiro83.github.io/gerador-loterias-caixa/**

Página estática com o último concurso de cada modalidade, frequência e atraso,
distribuição da soma, repetição do concurso anterior, heatmap por coluna da Super
Sete, **score dos últimos resultados** (limiar e aderência calibrados por
modalidade), card em destaque dos **padrões de linha que mais caem** e um gerador
rápido que mostra score e padrão de cada jogo (com filtro opcional "só padrões
top 3"). Fica em `dashboard/` e é publicada pelo GitHub Actions a cada push.

Para atualizar os dados da página:

```bash
python main.py --atualizar
python scripts/export_dashboard.py
git add dashboard/data.json && git commit -m "Atualiza dados do dashboard" && git push
```

### Atualização diária automática

O workflow `.github/workflows/atualizar.yml` roda **todo dia às 3h da manhã
(horário de Brasília)** no GitHub Actions: baixa os concursos novos da Caixa,
reexporta `dashboard/data.json`, dá push no `main` e publica o GitHub Pages —
sem intervenção manual. Também pode ser disparado à mão (aba **Actions** →
"Atualizar resultados diarios" → **Run workflow**).

Se a Caixa não responder e alguma modalidade não vier com dados reais, o
`--atualizar` falha com código 2 e nada é publicado: o site continua com o
último histórico real (e o Actions envia um e-mail de falha ao dono do repo).
O Super Sete usa um espelho de terceiros (endpoint oficial devolve 500 há
tempo); se o espelho cair, só ele fica desatualizado nesse dia.

---

## Testes

```bash
python -m pytest -q
```

A suíte cobre validação oficial, filtros, moldura/miolo/quadrantes, geração
determinística, histórico (repetição e contaminação), SQLite, ETL (com rede
mockada), o motor de score adaptativo e uma integração de ponta a ponta da CLI —
tudo sem depender de rede.

---

## Git e GitHub

```bash
git init
git add .
git commit -m "feat: estrutura inicial do gerador de jogos"

# crie o repositório vazio no GitHub e então:
git branch -M main
git remote add origin https://github.com/<seu-usuario>/gerador-loterias-caixa.git
git push -u origin main
```

Primeiro push via SSH (recomendado):

```bash
ssh-keygen -t ed25519 -C "seu@email.com"
# adicione o conteúdo de ~/.ssh/id_ed25519.pub em GitHub > Settings > SSH keys
git remote add origin git@github.com:<seu-usuario>/gerador-loterias-caixa.git
git push -u origin main
```

Boas práticas já aplicadas: `.gitignore` exclui `data/*.db`, `.venv`, caches e
`.env`. Nunca versione o banco nem credenciais.

---

## Estado do projeto

| Etapa | Status |
|---|---|
| Estrutura de pastas, `requirements.txt`, `.gitignore`, README | concluída |
| ETL/scraper Caixa → SQLite (incremental + fallback offline) | concluído |
| Core Engine (regras, filtros, histórico, geração) | concluído |
| 8 módulos de modalidade + registry | concluído |
| CLI `main.py` e validação de integração | concluído |
| Score adaptativo por modalidade (calibrado no histórico) | concluído |
| Filtro por padrões de linha (top 3 do histórico) | concluído |
| Dashboard público com score e gerador | concluído |
| Suíte de testes | 234 testes verdes |

Próximos passos sugeridos: backtest de filtros sobre o histórico, exportação
CSV/PDF de volantes e uma interface web simples.

---

## Licença

MIT.
