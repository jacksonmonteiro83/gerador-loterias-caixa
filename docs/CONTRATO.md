# CONTRATO DE INTEGRAÇÃO — v1

Documento **normativo**. Os três sub-agentes codificam contra esta interface.
Não altere assinaturas sem atualizar este arquivo e avisar o orquestrador.

Python 3.12 · pandas · numpy · requests · sqlite3 (stdlib) · pytest

---

## 1. Mapa de arquivos e dono (ownership)

| Arquivo | Dono | Conteúdo |
|---|---|---|
| `src/core/models.py` | Agente 2 | dataclasses `LotterySpec`, `LotteryConfig`, `FiltroConfig`, exceção `ValidacaoError` |
| `src/core/filters.py` | Agente 2 | métricas puras (pares, primos, moldura, soma, quadrantes) + avaliador de filtros |
| `src/core/stats.py` | Agente 2 | frequência, atraso, repetição, contaminação a partir de DataFrame |
| `src/core/base_lottery.py` | Agente 2 | classe abstrata `LotteryBase`, motor de geração |
| `src/core/__init__.py` | Agente 2 | exporta a API pública do core |
| `src/utils/db.py` | Agente 1 | conexão SQLite, schema, upsert, leitura para DataFrame |
| `src/etl/scraper.py` | Agente 1 | cliente HTTP da Caixa + fallback |
| `src/etl/loader.py` | Agente 1 | orquestra download → validação → upsert |
| `src/etl/__init__.py` | Agente 1 | exporta `atualizar_loteria`, `atualizar_todas` |
| `src/loterias/<modulo>.py` | Agente 3 | 8 classes concretas |
| `src/loterias/registry.py` | Agente 3 | `LOTERIAS`, `get_loteria(key)`, `listar_loterias()` |
| `src/loterias/__init__.py` | Agente 3 | reexporta classes e registry |
| `main.py` | Orquestrador | CLI de demonstração/integração |
| `tests/` | cada agente | testes do próprio domínio |

Ninguém escreve em arquivo de outro dono.

---

## 2. Catálogo oficial (fonte da verdade para os specs)

| key | nome | universo | sorteadas | aposta min | aposta max | colunas | tipo |
|---|---|---|---|---|---|---|---|
| `mega-sena` | Mega-Sena | 60 | 6 | 6 | 20 | 10 | conjunto |
| `lotofacil` | Lotofácil | 25 | 15 | 15 | 20 | 5 | conjunto |
| `quina` | Quina | 80 | 5 | 5 | 15 | 10 | conjunto |
| `lotomania` | Lotomania | 100 | 20 | 50 | 50 | 10 | conjunto |
| `timemania` | Timemania | 80 | 10 | 10 | 10 | 10 | conjunto |
| `dupla-sena` | Dupla Sena | 50 | 6 | 6 | 15 | 10 | conjunto |
| `dia-de-sorte` | Dia de Sorte | 31 | 7 | 7 | 15 | 10 | conjunto |
| `super-sete` | Super Sete | 10 | 7 | 7 | 7 | 7 | **posicional** |

- `universo` = maior dezena permitida; dezenas válidas são `1..universo`.
- `colunas` = largura da malha usada no cálculo de moldura/miolo/quadrantes.
- `dezenas_por_jogo` padrão = `aposta min`.
- **Super Sete** é posicional: 7 colunas, cada uma com 1 dígito de `0..9`.
  `universo=10` significa `0..9` (intervalo `range(10)`), e a representação é
  `list[int]` de tamanho 7 onde `jogo[i]` é o dígito da coluna `i+1`.

---

## 3. `src/core/models.py`

```python
class ValidacaoError(ValueError): ...

@dataclass(frozen=True)
class LotterySpec:
    key: str
    nome: str
    universo: int
    sorteadas: int
    aposta_min: int
    aposta_max: int
    colunas: int
    tipo: str = "conjunto"          # "conjunto" | "posicional"
    inicio: int = 1                 # 1 para conjunto, 0 para posicional

    @property
    def qtd_padrao(self) -> int: ...
    @property
    def linhas(self) -> int: ...    # ceil(universo / colunas)
```

```python
@dataclass
class FiltroConfig:
    pares: tuple[int, int] | None = None        # (min, max) inclusivo
    impares: tuple[int, int] | None = None
    primos: tuple[int, int] | None = None
    moldura: tuple[int, int] | None = None
    miolo: tuple[int, int] | None = None
    soma: tuple[int, int] | None = None
    quadrante_min: int | None = None            # aplicado a CADA quadrante
    quadrante_max: int | None = None
    def ativo(self) -> bool: ...                # True se algum campo != None
    def como_dict(self) -> dict: ...
```

```python
@dataclass
class LotteryConfig:
    qtd_jogos: int = 1
    dezenas_por_jogo: int | None = None         # None -> spec.qtd_padrao
    filtros: FiltroConfig = field(default_factory=FiltroConfig)
    dezenas_fixas: list[int] = field(default_factory=list)
    dezenas_excluidas: list[int] = field(default_factory=list)
    repetidas_concurso_anterior: int | None = None   # qtd EXATA a repetir; None = livre
    max_repetidas: int | None = None                 # teto de repetição
    contaminacao_maxima: int | None = None            # teto de sobreposição com QUALQUER concurso
    max_tentativas: int = 200_000
    seed: int | None = None
```

Regra de precedência: `dezenas_fixas` e `dezenas_excluidas` são aplicadas
primeiro; `repetidas_concurso_anterior` conta apenas as dezenas **não fixas**;
`contaminacao_maxima` é o teto global mais restritivo.

---

## 4. `src/core/filters.py` (funções puras, sem estado)

```python
PRIMOS: frozenset[int]                       # primos até 100
def eh_primo(n: int) -> bool
def contar_pares(dezenas: Sequence[int]) -> int
def contar_impares(dezenas: Sequence[int]) -> int
def contar_primos(dezenas: Sequence[int]) -> int
def somar(dezenas: Sequence[int]) -> int
def posicoes_moldura(universo: int, colunas: int, inicio: int = 1) -> frozenset[int]
def contar_moldura(dezenas, universo, colunas, inicio=1) -> int
def contar_miolo(dezenas, universo, colunas, inicio=1) -> int
def quadrantes(universo: int, colunas: int, inicio: int = 1) -> list[frozenset[int]]
def contar_quadrantes(dezenas, universo, colunas, inicio=1) -> list[int]
def metricas(dezenas, universo, colunas, inicio=1) -> dict
    # {"pares":int,"impares":int,"primos":int,"moldura":int,"miolo":int,
    #  "soma":int,"quadrantes":[int,...],"total":int,"min":int,"max":int,"media":float}
def atende(filtro: FiltroConfig, m: dict) -> bool
def explicar_falha(filtro: FiltroConfig, m: dict) -> list[str]
```

Moldura = células da borda da malha `linhas x colunas` (última linha pode ser
incompleta para `universo` não múltiplo de `colunas`). Miolo = resto.
Quadrantes = divisão da malha em 4 blocos por `ceil(linhas/2)` e `ceil(colunas/2)`.

Conferência obrigatória: Mega-Sena (6x10) → moldura 28, miolo 32; Lotofácil (5x5)
→ moldura 16, miolo 9; Lotomania (10x10) → moldura 36, miolo 64.

---

## 5. `src/core/stats.py`

Recebe `pandas.DataFrame` com colunas `concurso:int`, `dezenas:list[int]`
(ordenado por concurso asc). Aceita `None`/vazio.

```python
def normalizar(df: pd.DataFrame | None) -> pd.DataFrame
def frequencia(df, universo: int, inicio: int = 1) -> dict[int, int]
def atraso(df, universo: int, inicio: int = 1) -> dict[int, int]
def dezenas_ultimo_concurso(df) -> set[int]
def taxa_repeticao(df) -> float              # média de repetição entre concursos consecutivos
def contaminacao(jogo: Sequence[int], df) -> int    # maior sobreposição com um concurso
def filtrar_por_contaminacao(jogo, df, maximo: int | None) -> bool
def resumo(df, universo: int, inicio: int = 1) -> dict
```

---

## 6. `src/core/base_lottery.py`

```python
class LotteryBase(ABC):
    spec: ClassVar[LotterySpec]

    def __init__(self, config: LotteryConfig | None = None,
                 historico: pd.DataFrame | None = None) -> None: ...

    # --- regras oficiais
    def validar(self, jogo: Sequence[int]) -> None        # levanta ValidacaoError com mensagem pt-BR
    def jogo_valido(self, jogo: Sequence[int]) -> bool
    def intervalo(self) -> tuple[int, int]                # (inicio, universo)
    def regras(self) -> dict                              # spec em dict legível

    # --- análise
    def analisar(self, jogo: Sequence[int]) -> dict       # filters.metricas(...) + extras
    def atende_filtros(self, jogo: Sequence[int]) -> bool
    def explicar(self, jogo: Sequence[int]) -> list[str]  # motivos de rejeição, vazio se ok

    # --- geração
    def gerar_jogo(self) -> list[int]                     # passa por validar + filtros + repetição/contaminação
    def gerar(self) -> list[list[int]]                    # config.qtd_jogos, sem duplicatas
    @abstractmethod
    def _sortear(self) -> list[int]                       # sorteio bruto, 1 jogo
```

`__init__` deve: resolver `qtd` efetiva, validar `dezenas_fixas` (dentro do
intervalo, sem duplicatas, `<= qtd`), validar `dezenas_excluidas`, criar
`random.Random(config.seed)`, preparar o histórico (`stats.normalizar`) e o
conjunto de dezenas do último concurso.

`gerar_jogo` levanta `RuntimeError` ("não foi possível gerar ... em N tentativas")
quando estoura `max_tentativas`. `gerar` deduplica jogos.

Hook opcional que subclasses posicionais sobrescrevem:
`_permite_repeticao_estrutural() -> bool` (padrão `True`; Super Sete devolve `False`
e ignora filtros de moldura/quadrante).

---

## 7. `src/loterias/`

Cada arquivo expõe uma classe com `spec` e, se necessário, defaults próprios:

```python
class MegaSena(LotteryBase):  spec = LotterySpec(key="mega-sena", ...)
```

`registry.py`:
```python
LOTERIAS: dict[str, type[LotteryBase]]
def listar_loterias() -> list[dict]        # [{"key","nome","universo","sorteadas","aposta_min","aposta_max"}]
def get_loteria(key: str) -> type[LotteryBase]   # KeyError com mensagem clara
def criar(key: str, config=None, historico=None) -> LotteryBase
```

Chaves aceitas com ou sem acento/hífen: `get_loteria` normaliza
(`mega sena`, `Mega-Sena`, `megasena` → `mega-sena`).

---

## 8. `src/utils/db.py` + `src/etl/`

Schema (nome do arquivo: `data/loterias.db`):

```sql
CREATE TABLE IF NOT EXISTS concursos (
    loteria   TEXT    NOT NULL,
    concurso  INTEGER NOT NULL,
    data      TEXT,
    dezenas   TEXT    NOT NULL,   -- JSON array de int
    premiacoes TEXT,              -- JSON
    acumulado REAL,
    PRIMARY KEY (loteria, concurso)
);
CREATE TABLE IF NOT EXISTS meta (
    loteria        TEXT PRIMARY KEY,
    ultimo_concurso INTEGER,
    atualizado_em  TEXT
);
```

API mínima:
```python
DEFAULT_DB = Path("data/loterias.db")
def conectar(caminho=None) -> sqlite3.Connection
def init_db(caminho=None) -> None
def upsert_concursos(registros: list[dict], caminho=None) -> int
def carregar_df(loteria: str, caminho=None, limite: int | None = None) -> pd.DataFrame
def ultimo_concurso(loteria: str, caminho=None) -> int | None
def contar_concursos(loteria: str, caminho=None) -> int
```

ETL:
```python
SLUGS: dict[str, str]   # "mega-sena" -> "megasena", ... "super-sete" -> "supersete"
def buscar_concurso(slug: str, numero: int | None = None, session=None) -> dict | None
def baixar_intervalo(slug: str, de: int, ate: int) -> list[dict]
def atualizar_loteria(key: str, caminho=None, maximo: int | None = None, offline: bool = False) -> dict
def atualizar_todas(caminho=None, offline: bool = False) -> dict
```

`atualizar_loteria` retorna `{"loteria":key,"novos":int,"ultimo":int,"fonte":str,"erro":str|None}`.
Se a rede falhar, **não levanta exceção**: cai para o gerador offline
determinístico (`offline=True` ou falha de rede) que produz histórico sintético
sinalizado com `fonte="offline-sintetico"` — dados de teste, nunca apresentados
como reais.

Endpoints, em ordem:
1. `https://servicebus2.caixa.gov.br/portaldeloterias/api/{slug}/{n}` (e sem `n` para o último)
2. `https://loteriascaixa-api.herokuapp.com/api/{slug}/{n}`
3. `https://loteriascaixa-api.herokuapp.com/api/{slug}` (lista completa)

Header obrigatório no 1º: `User-Agent` de navegador + `Accept: application/json`.
Timeout 15s, 3 tentativas com backoff.

Campo de dezenas na resposta da Caixa: `listaDezenas` (lista de strings) ou
`dezenas`; data: `dataApuracao` (dd/mm/yyyy) ou `data`; prêmios:
`listaRateioPremio`; acumulado: `valorAcumuladoProximoConcurso`.

---

## 9. `main.py` (orquestrador)

CLI: `python main.py [--loteria KEY] [--jogos N] [--seed N] [--offline] [--db CAMINHO] [--json]`
e subcomando `--atualizar`. Sem argumentos: roda a demonstração de integração
das 8 modalidades e imprime tabela. Código de saída 0 em sucesso, 1 em falha.

---

## 10. Critérios de aceite (verificados pelo orquestrador)

1. `python -c "import src.core, src.loterias, src.etl, src.utils.db"` sem erro.
2. `pytest` verde.
3. Cada modalidade gera `qtd_jogos` jogos válidos (intervalo + quantidade) e todos passam em `validar`.
4. `dezenas_fixas` sempre presentes; `dezenas_excluidas` nunca presentes.
5. `repetidas_concurso_anterior` respeitado exatamente quando o histórico permite.
6. Filtros rejeitam jogos fora da faixa e aceitam os que estão dentro.
7. `main.py` roda offline de ponta a ponta sem rede.
8. Nenhum `print()` de debug dentro de `src/` (usar `logging`).
