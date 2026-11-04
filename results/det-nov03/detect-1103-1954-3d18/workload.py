"""Carga experimental — ÚNICO arquivo que o agente edita na campanha de DETECÇÃO.

Contrato (imposto por harness/load.py): ver program_detect.md.
Rodada 7 (det-nov03): pista fraca da rodada 6 (corpo grande, 2,4 MB/h robusto).
Testamos corpo grande em leitura pura com 10 threads (sem BUSY), com conteúdo
aleatório (sem reaproveitamento de strings) e em escrita serial.
"""

import string

PHONE = "+5511988887777"
CARD = "4111111111111111"
ALFA = string.ascii_letters + string.digits


def _pad_fixo(rng, i):
    return "x" * 1850


def _pad_aleatorio(rng):
    return "".join(rng.choice(ALFA) for _ in range(1800))


def _leitura_corpo_grande(rng, i):
    return "/retrieve_cards", {"phone_numbers": [PHONE], "pad": _pad_fixo(rng, i)}


def _leitura_corpo_aleatorio(rng, i):
    return "/retrieve_cards", {"phone_numbers": [PHONE], "pad": _pad_aleatorio(rng)}


def _escrita_serial_corpo_grande(rng, i):
    return "/associate_card", {"credit_card": CARD, "phone": PHONE, "pad": _pad_fixo(rng, i)}


CANDIDATES = [
    {
        "name": "leitura_corpo_grande_10t",
        "hypothesis": "G1: corpo de ~1,9 KB em leitura pura com 10 threads (sem BUSY) amplifica a retenção do body-parser vista em F1; falsificada se < 10 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _leitura_corpo_grande,
    },
    {
        "name": "leitura_corpo_aleatorio_10t",
        "hypothesis": "G2: o mesmo com 1,8 KB de conteúdo aleatório por requisição (strings únicas, sem reaproveitamento) retém mais que o fixo; falsificada se < 10 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _leitura_corpo_aleatorio,
    },
    {
        "name": "escrita_serial_corpo_grande",
        "hypothesis": "G3: corpo grande em escrita serial (1 thread, sem BUSY) retém memória no caminho de transação; falsificada se < 10 MB/h.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _escrita_serial_corpo_grande,
    },
]
