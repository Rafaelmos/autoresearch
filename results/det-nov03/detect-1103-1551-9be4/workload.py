"""Carga experimental — ÚNICO arquivo que o agente edita na campanha de DETECÇÃO.

Contrato (imposto por harness/load.py): ver program_detect.md.
Rodada 3 (det-nov03): rodadas 1-2 não passaram de ~1 MB/h robusto. Testamos
(C1) caminho de validação com payloads grandes, (C2) caminho serial sem
concorrência e (C3) leitura serial com listas longas.
"""

PHONES = ["+5511988887777", "+5511977776666", "+1(800)123-4567", "+44 2079460958", "+5581999990000"]


def _card(k):
    return "41111111" + str(10000000 + k % 100)


def _payload_grande(rng, i):
    # 1500 dígitos: falha na regex/validação (400) sem tocar no banco, mas o body é grande.
    big = "".join(rng.choice("0123456789") for _ in range(1500))
    if i % 2 == 0:
        return "/associate_card", {"credit_card": big, "phone": PHONES[0]}
    return "/retrieve_cards", {"phone_numbers": [big]}


def _serial_misto(rng, i):
    k = rng.randrange(100)
    if i % 2 == 0:
        return "/associate_card", {"credit_card": _card(k), "phone": PHONES[k % 5]}
    return "/retrieve_cards", {"phone_numbers": rng.sample(PHONES, rng.randint(1, 5))}


def _leitura_serial_larga(rng, i):
    k = rng.randrange(100)
    if i % 20 == 0:
        return "/associate_card", {"credit_card": _card(k), "phone": PHONES[k % 5]}
    extra = ["+5511%09d" % rng.randrange(900000000, 900001000) for _ in range(5)]
    return "/retrieve_cards", {"phone_numbers": PHONES + extra}


CANDIDATES = [
    {
        "name": "payload_grande_invalido",
        "hypothesis": "C1: bodies de ~1,5 KB rejeitados na validação (sem banco) retêm memória no parser/regex; falsificada se < 10 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _payload_grande,
    },
    {
        "name": "serial_misto",
        "hypothesis": "C2: sem concorrência (1 thread, sem BUSY) o caminho normal de associate+retrieve retém memória; falsificada se < 10 MB/h.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _serial_misto,
    },
    {
        "name": "leitura_serial_larga",
        "hypothesis": "C3: leitura larga (10 telefones) serial, com 5% de escrita, retém memória nativa do sqlite3 por conexão; falsificada se < 10 MB/h.",
        "threads": 2,
        "think_time_s": 0.01,
        "request": _leitura_serial_larga,
    },
]
