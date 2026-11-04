"""Carga experimental — ÚNICO arquivo que o agente edita na campanha de DETECÇÃO.

Contrato (imposto por harness/load.py): ver program_detect.md.
Rodada 5 (det-nov03): rodadas 1-4 planas. Testamos escrita concorrente pura
(10 threads, esperado E2/crash), erros intercalados com requisições válidas e
concorrência intermediária (6 threads).
"""

CARD = "4111111111111111"
PHONE = "+5511988887777"


def _so_associate_10(rng, i):
    return "/associate_card", {"credit_card": CARD, "phone": PHONE}


def _erros_intercalados(rng, i):
    m = i % 4
    if m == 0:
        return "/associate_card", {"credit_card": CARD, "phone": "123"}
    if m == 1:
        return "/retrieve_cards", {"phone_numbers": [PHONE, "x"]}
    if m == 2:
        return "/retrieve_cards", {"phone_numbers": [PHONE]}
    return "/associate_card", {"credit_card": "4000000000000%03d" % rng.randrange(20), "phone": PHONE}


def _meia_concorrencia(rng, i):
    k = rng.randrange(20)
    if i % 2 == 0:
        return "/associate_card", {"credit_card": "4000000000000%03d" % k, "phone": PHONE}
    return "/retrieve_cards", {"phone_numbers": [PHONE]}


CANDIDATES = [
    {
        "name": "associate_10_threads",
        "hypothesis": "E1: escrita pura com 10 threads causa muito SQLITE_BUSY (E2) e a retenção está nos caminhos de erro (conexão não fechada); falsificada se não houver E2 e a inclinação ficar < 10 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _so_associate_10,
    },
    {
        "name": "erros_intercalados",
        "hypothesis": "E2: 50% de requisições barradas na validação intercaladas com válidas retêm memória nos caminhos de erro 400; falsificada se < 10 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _erros_intercalados,
    },
    {
        "name": "meia_concorrencia",
        "hypothesis": "E3: com 6 threads (menos BUSY que 10) o mix 50/50 mostra a retenção; falsificada se < 10 MB/h.",
        "threads": 6,
        "think_time_s": 0.01,
        "request": _meia_concorrencia,
    },
]
