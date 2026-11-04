"""Carga experimental — ÚNICO arquivo que o agente edita na campanha de DETECÇÃO.

Contrato (imposto por harness/load.py): ver program_detect.md.
Rodada 6 (det-nov03): corpo com campo extra grande (parser JSON), consulta
com telefones duplicados (HAVING nunca casa) e taxa baixa (think time 1 s).
"""

CARD = "4111111111111111"
PHONE = "+5511988887777"
PAD = "x" * 1700


def _corpo_extra(rng, i):
    if i % 2 == 0:
        return "/associate_card", {"credit_card": CARD, "phone": PHONE, "pad": PAD}
    return "/retrieve_cards", {"phone_numbers": [PHONE], "pad": PAD}


def _telefones_duplicados(rng, i):
    if i % 20 == 0:
        return "/associate_card", {"credit_card": CARD, "phone": PHONE}
    return "/retrieve_cards", {"phone_numbers": [PHONE] * 10}


def _taxa_baixa(rng, i):
    k = rng.randrange(20)
    if i % 2 == 0:
        return "/associate_card", {"credit_card": "4000000000000%03d" % k, "phone": PHONE}
    return "/retrieve_cards", {"phone_numbers": [PHONE]}


CANDIDATES = [
    {
        "name": "corpo_extra_grande",
        "hypothesis": "F1: corpos de ~1,7 KB com campo extra válidos retêm memória no body-parser; falsificada se < 10 MB/h.",
        "threads": 3,
        "think_time_s": 0.01,
        "request": _corpo_extra,
    },
    {
        "name": "telefones_duplicados",
        "hypothesis": "F2: 10 telefones iguais (COUNT DISTINCT nunca bate com 10) retornam vazio e retêm memória no plano da consulta; falsificada se < 10 MB/h.",
        "threads": 3,
        "think_time_s": 0.01,
        "request": _telefones_duplicados,
    },
    {
        "name": "taxa_baixa",
        "hypothesis": "F3: com think time de 1 s (~10 rps) o crescimento depende de tempo e não de volume; falsificada se < 10 MB/h.",
        "threads": 10,
        "think_time_s": 1.0,
        "request": _taxa_baixa,
    },
]
