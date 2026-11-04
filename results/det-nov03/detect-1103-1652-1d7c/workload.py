"""Carga experimental — ÚNICO arquivo que o agente edita na campanha de DETECÇÃO.

Contrato (imposto por harness/load.py): ver program_detect.md.
Rodada 4 (det-nov03): strings distintas em formatos válidos, um cartão com
muitos telefones e respostas grandes (estado do banco abaixo de 1000 linhas).
"""


def _telefone(k):
    s = k % 4
    if s == 0:
        return "+55119%08d" % (10000000 + k)
    if s == 1:
        return "+1(800)%03d-%04d" % (k % 1000, k % 10000)
    if s == 2:
        return "+44 20%08d" % (10000000 + k)
    return "+55 81 9%04d-%04d" % (k % 10000, (k * 7) % 10000)


def _strings_distintas(rng, i):
    k = rng.randrange(300)
    if i % 2 == 0:
        return "/associate_card", {"credit_card": "4111-1111-1111-%04d" % (k % 100), "phone": _telefone(k)}
    return "/retrieve_cards", {"phone_numbers": [_telefone(rng.randrange(300))]}


def _um_cartao_muitos_telefones(rng, i):
    k = rng.randrange(150)
    if i % 2 == 0:
        return "/associate_card", {"credit_card": "4222222222222222", "phone": _telefone(k)}
    return "/retrieve_cards", {"phone_numbers": [_telefone(rng.randrange(150)) for _ in range(rng.randint(1, 3))]}


def _resultado_grande(rng, i):
    if i % 10 == 0:
        return "/associate_card", {"credit_card": "43333333%08d" % rng.randrange(60), "phone": _telefone(rng.randrange(10))}
    return "/retrieve_cards", {"phone_numbers": [_telefone(j) for j in range(10)]}


CANDIDATES = [
    {
        "name": "strings_distintas",
        "hypothesis": "D1: 300 telefones em 4 formatos e 100 cartões com separadores (muitas strings distintas) fazem o sqlite3 reter memória nativa; falsificada se < 10 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _strings_distintas,
    },
    {
        "name": "um_cartao_muitos_telefones",
        "hypothesis": "D2: um único cartão ligado a ~150 telefones torna o JOIN/GROUP BY pesado e retém memória por consulta; falsificada se < 10 MB/h.",
        "threads": 3,
        "think_time_s": 0.01,
        "request": _um_cartao_muitos_telefones,
    },
    {
        "name": "resultado_grande",
        "hypothesis": "D3: respostas com ~60 cartões por consulta de 10 telefones retêm buffers nativos de resultado; falsificada se < 10 MB/h.",
        "threads": 3,
        "think_time_s": 0.01,
        "request": _resultado_grande,
    },
]
