"""Carga experimental — ÚNICO arquivo que o agente edita na campanha de DETECÇÃO.

Contrato (imposto por harness/load.py): ver program_detect.md.
Rodada 8 (det-nov03), semente 2: réplica de F1 (corpo_extra_grande, 2,4 MB/h
robusto na rodada 6) e de G3 (escrita_serial_corpo_grande, 12,1 global / 1,99
robusto na rodada 7), mais uma variante de F1 com 2 threads.
"""

CARD = "4111111111111111"
PHONE = "+5511988887777"
PAD = "x" * 1700


def _corpo_extra(rng, i):
    if i % 2 == 0:
        return "/associate_card", {"credit_card": CARD, "phone": PHONE, "pad": PAD}
    return "/retrieve_cards", {"phone_numbers": [PHONE], "pad": PAD}


def _escrita_serial_corpo_grande(rng, i):
    return "/associate_card", {"credit_card": CARD, "phone": PHONE, "pad": "x" * 1850}


CANDIDATES = [
    {
        "name": "corpo_extra_grande",
        "hypothesis": "F1 (réplica, semente 2): corpos de ~1,7 KB com campo extra válidos retêm memória no body-parser; falsificada se < 10 MB/h ou se a inclinação robusta divergir muito da semente 1 (2,4).",
        "threads": 3,
        "think_time_s": 0.01,
        "request": _corpo_extra,
    },
    {
        "name": "escrita_serial_corpo_grande",
        "hypothesis": "G3 (réplica, semente 2): corpo grande em escrita serial retém memória; o global 12,1 da semente 1 era degrau (robusto 1,99), esperado < 10 MB/h robusto; falsificada se robusto >= 10.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _escrita_serial_corpo_grande,
    },
    {
        "name": "corpo_extra_2t",
        "hypothesis": "H1: F1 com 2 threads em vez de 3 indica se o efeito do corpo grande escala com a concorrência; falsificada se < 10 MB/h.",
        "threads": 2,
        "think_time_s": 0.01,
        "request": _corpo_extra,
    },
]
