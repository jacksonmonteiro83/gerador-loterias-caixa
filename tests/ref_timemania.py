"""Implementação de referência (Python) do motor heurístico da Timemania.

Cópia fiel da classe fornecida pelo autor; é a verdade contra a qual a versão
JavaScript (dashboard/timemania.js) é testada (tests/test_timemania_js.py).
Só o `api_url`, que veio com a formatação de link quebrada, foi normalizado.
"""

import random  # noqa: F401
from collections import Counter


class TimemaniaScoringSystem:
    PRIMOS_TIMEMANIA = {
        2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41,
        43, 47, 53, 59, 61, 67, 71, 73, 79
    }

    def __init__(self):
        self.api_url = "https://loteriascaixa-api.herokuapp.com/api/timemania"
        self.THRESHOLD_10 = 120
        self.THRESHOLD_7 = 85
        self.params = {}

    def mapear_quadrante(self, n):
        linha = (n - 1) // 10
        coluna = (n - 1) % 10
        if linha < 4 and coluna < 5: return 1
        if linha < 4 and coluna >= 5: return 2
        if linha >= 4 and coluna < 5: return 3
        return 4

    def validar_jogo_10(self, jogo_10, jogo_anterior_7):
        jogo = sorted(jogo_10)
        soma = sum(jogo)
        pares = sum(1 for n in jogo if n % 2 == 0)
        primos = sum(1 for n in jogo if n in self.PRIMOS_TIMEMANIA)
        rep_anterior = len(set(jogo).intersection(set(jogo_anterior_7)))
        quadrantes = len(set(self.mapear_quadrante(n) for n in jogo))
        consecutivos = sum(1 for i in range(9) if jogo[i + 1] == jogo[i] + 1)

        decis = [(n - 1) // 10 for n in jogo]
        freq_decis = Counter(decis)
        max_linha = max(freq_decis.values()) if freq_decis else 0
        linhas_ativas = len(freq_decis)

        primeiro_num = jogo[0]
        ultimo_num = jogo[-1]
        amplitude = ultimo_num - primeiro_num

        padrao_lista = sorted(freq_decis.values(), reverse=True)
        padrao_formatado = "-".join(map(str, padrao_lista))

        # --- HARD BLOCKS (Aposta Múltipla - 10 dezenas) ---
        if rep_anterior >= 2: return {"all": False}
        if primeiro_num > 16 or ultimo_num < 64 or amplitude < 55: return {"all": False}
        if soma < 320 or soma > 490: return {"all": False}
        if max_linha > 3: return {"all": False}
        if quadrantes < 3: return {"all": False}
        if consecutivos >= 2: return {"all": False}

        score = 0
        if 350 <= soma <= 460: score += 20
        else: score += 10

        if pares in [4, 5, 6]: score += 20
        elif pares in [3, 7]: score += 10

        if primos in [2, 3, 4]: score += 20
        elif primos in [1, 5]: score += 10

        if max_linha <= 2: score += 20
        else: score += 10

        if quadrantes == 4: score += 20
        else: score += 10

        if rep_anterior == 0: score += 20
        else: score += 10

        if consecutivos == 0: score += 20
        elif consecutivos == 1: score += 10
        else: score += 5

        aprovado = score >= self.THRESHOLD_10
        return {
            "all": aprovado,
            "score": score,
            "soma": soma,
            "pares": pares,
            "primos": primos,
            "quadrantes": quadrantes,
            "consecutivos": consecutivos,
            "rep_anterior": rep_anterior,
            "amplitude": f"[{primeiro_num}-{ultimo_num}]",
            "padrao_linhas": padrao_formatado
        }

    def validar_jogo_7(self, jogo_7, jogo_anterior_7):
        jogo = sorted(jogo_7)
        soma = sum(jogo)
        pares = sum(1 for n in jogo if n % 2 == 0)
        primos = sum(1 for n in jogo if n in self.PRIMOS_TIMEMANIA)
        rep_anterior = len(set(jogo).intersection(set(jogo_anterior_7)))
        quadrantes = len(set(self.mapear_quadrante(n) for n in jogo))
        consecutivos = sum(1 for i in range(6) if jogo[i + 1] == jogo[i] + 1)

        decis = [(n - 1) // 10 for n in jogo]
        freq_decis = Counter(decis)
        max_linha = max(freq_decis.values()) if freq_decis else 0
        linhas_ativas = len(freq_decis)

        primeiro_num = jogo[0]
        ultimo_num = jogo[-1]
        amplitude = ultimo_num - primeiro_num

        padrao_lista = sorted(freq_decis.values(), reverse=True)
        padrao_formatado = "-".join(map(str, padrao_lista))

        if rep_anterior >= 2:
            return {"all": False, "score": 0, "status_detalhado": f"REJ (0pts: REP_ANT({rep_anterior}))", "padrao_linhas": padrao_formatado}
        if primeiro_num >= 22 or ultimo_num < 60 or amplitude < 50:
            return {"all": False, "score": 0, "status_detalhado": f"REJ (0pts: EXTREMOS[{primeiro_num}-{ultimo_num}])", "padrao_linhas": padrao_formatado}
        if soma < 195 or soma > 375:
            return {"all": False, "score": 0, "status_detalhado": f"REJ (0pts: SOMA({soma}))", "padrao_linhas": padrao_formatado}
        if max_linha > 3:
            return {"all": False, "score": 0, "status_detalhado": f"REJ (0pts: ELIMINADO_LINHA({max_linha}))", "padrao_linhas": padrao_formatado}
        if linhas_ativas == 7 and max_linha == 1:
            return {"all": False, "score": 0, "status_detalhado": "REJ (0pts: ELIMINADO_ESPALHAMENTO_TOTAL)", "padrao_linhas": padrao_formatado}
        if quadrantes < 3:
            return {"all": False, "score": 0, "status_detalhado": f"REJ (0pts: QUADRANTES({quadrantes}))", "padrao_linhas": padrao_formatado}
        if consecutivos >= 3:
            return {"all": False, "score": 0, "status_detalhado": f"REJ (0pts: CONSECUTIVOS({consecutivos}))", "padrao_linhas": padrao_formatado}

        score = 0
        falhas = []

        if 230 <= soma <= 340: score += 20
        else: score += 10

        if pares in [3, 4]: score += 20
        elif pares in [2, 5]: score += 10
        else: falhas.append(f"PARES({pares})")

        if primos in [2, 3]: score += 20
        elif primos in [1, 4]: score += 10
        else: falhas.append(f"PRIMOS({primos})")

        if max_linha <= 2: score += 20
        else: score += 10

        if quadrantes == 4: score += 20
        else: score += 10

        if rep_anterior == 0: score += 20
        else: score += 10

        if consecutivos == 0: score += 20
        elif consecutivos == 1: score += 10
        else: score += 5

        aprovado = score >= self.THRESHOLD_7
        motivo = f"APROV ({score}pts)" if aprovado else f"REJ ({score}pts: {'/'.join(falhas)})"

        return {"all": aprovado, "score": score, "status_detalhado": motivo, "padrao_linhas": padrao_formatado}
