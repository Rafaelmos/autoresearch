"""Carga experimental — ÚNICO arquivo que o agente edita na campanha de DETECÇÃO.

Contrato (imposto por harness/load.py): ver program_detect.md.
Rodada 2 (det-nov03): a baseline ficou plana (0,37 MB/h) na rodada 1, então
variamos valores, largura da consulta e concorrência de escrita.
"""

PHONES = ["+5511988887777", "+5511977776666", "+1(800)123-4567", "+44 2079460958", "+5581999990000"]


def _card(k):
    return "41111111" + str(10000000 + k % 100)  # 16 dígitos, 100 cartões distintos


def _diverso(rng, i):
    k = rng.randrange(100)
    if i % 2 == 0:
        return "/associate_card", {"credit_card": _card(k), "phone": PHONES[k % 5]}
    n = rng.randint(1, 5)
    return "/retrieve_cards", {"phone_numbers": rng.sample(PHONES, n)}


def _leitura_larga(rng, i):
    if i % 10 == 0:
        k = rng.randrange(20)
        return "/associate_card", {"credit_card": _card(k), "phone": PHONES[k % 5]}
    base = ["+5511%09d" % (900000000 + j) for j in range(5)]
    return "/retrieve_cards", {"phone_numbers": PHONES + base}


def _escrita_pesada(rng, i):
    if i % 10 == 0:
        return "/retrieve_cards", {"phone_numbers": [PHONES[0]]}
    k = rng.randrange(100)
    return "/associate_card", {"credit_card": _card(k), "phone": PHONES[k % 5]}


CANDIDATES = [
    {
        "name": "valores_diversos",
        "hypothesis": "B1: a retenção depende da diversidade de valores (100 cartões, 5 telefones, listas de 1-5); falsificada se a inclinação ficar < 10 MB/h como a baseline.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _diverso,
    },
    {
        "name": "leitura_10_telefones",
        "hypothesis": "B2: consultas com 10 telefones (IN largo, JOIN/GROUP BY maior) retêm memória nativa do sqlite3; falsificada se < 10 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _leitura_larga,
    },
    {
        "name": "escrita_4_threads",
        "hypothesis": "B3: escrita dominante (90%) com 4 threads, concorrência moderada, retém memória no caminho de transação; falsificada se < 10 MB/h ou se E2.",
        "threads": 4,
        "think_time_s": 0.01,
        "request": _escrita_pesada,
    },
]
