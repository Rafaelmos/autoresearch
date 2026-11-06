"""Carga experimental — ÚNICO arquivo que o agente edita na campanha de DETECÇÃO.

Equivale ao train.py do karpathy/autoresearch. A baseline do artigo roda sempre
no 4º slot (harness/load.py: BASELINE) e não é declarada aqui.

Contrato (imposto por harness/load.py; violar invalida o braço):
- CANDIDATES: 1 a 3 dicts com name, hypothesis, threads, think_time_s, request.
- threads em [1, 10]; think_time_s >= 0.01  (limites do artigo: 10 threads, 0,01 s).
- request(rng, i) -> (path, body_dict). path em {/associate_card, /retrieve_cards};
  body JSON <= 2048 bytes; phone_numbers com no máximo 10 itens.
  Use SOMENTE rng (random.Random semeado pelo juiz) e i (índice da requisição).
- Entradas inválidas são permitidas (testam caminhos de erro), mas 5xx/exceções
  acima de 1% invalidam o braço (saturação não é aging).
- Mais de 1000 linhas no banco ao fim marcam D2 (crescimento de estado legítimo):
  o braço é medido, mas não pontua.

Campanha det-nov04 (janelas de 120 min). Rodadas com 1 thread (harness estoura timeout com >1 thread em 120 min).
"""

PHONE = "+5511988887777"
CARDS = ["41111111%08d" % k for k in range(20)]
PHONES = ["+55119888%05d" % k for k in range(20)]
FMT = ["+55%s", "+55 (11) 9%s", "+55-11-9%s", "+5511%s"]


def _misto_2t(rng, i):
    if rng.random() < 0.5:
        return "/associate_card", {"credit_card": rng.choice(CARDS), "phone": rng.choice(PHONES)}
    return "/retrieve_cards", {"phone_numbers": rng.sample(PHONES, rng.randint(1, 3))}


def _formatos_variados(rng, i):
    # mesmos 20 telefones, mas escritos em formatos distintos (strings diferentes, validos)
    def ph():
        k = rng.randint(0, 19)
        return rng.choice(FMT) % ("%08d" % (88880000 + k))
    if i % 2 == 0:
        c = rng.choice(CARDS)
        if rng.random() < 0.5:
            c = " ".join(c[j:j + 4] for j in range(0, len(c), 4))
        return "/associate_card", {"credit_card": c, "phone": ph()}
    return "/retrieve_cards", {"phone_numbers": [ph() for _ in range(rng.randint(1, 4))]}


def _corpo_grande_misto(rng, i):
    pad = "x" * 1500
    if i % 2 == 0:
        return "/associate_card", {"credit_card": rng.choice(CARDS), "phone": rng.choice(PHONES), "extra": pad}
    return "/retrieve_cards", {"phone_numbers": rng.sample(PHONES, rng.randint(1, 3)), "extra": pad}


CANDIDATES = [
    {
        "name": "misto_diverso_2t",
        "hypothesis": "R4-A: mix diverso com 2 threads (sonda do limiar do timeout do harness e primeira concorrência); retenção só aparece com concorrência; falsificada se robusto < 2 MB/h.",
        "threads": 2,
        "think_time_s": 0.01,
        "request": _misto_2t,
    },
    {
        "name": "formatos_variados_serial",
        "hypothesis": "R4-B: strings de telefone/cartão em formatos válidos distintos (espaços, hífens, parênteses) retêm memória nativa por parâmetros ligados distintos; falsificada se robusto < 2 MB/h.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _formatos_variados,
    },
    {
        "name": "corpo_grande_misto_serial",
        "hypothesis": "R4-C: corpo de ~1,5 KB em mix 50/50 serial (body-parser + banco); replica em 120 min a pista F1/G3 de det-nov03, que não replicou em 60 min; falsificada se robusto < 2 MB/h.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _corpo_grande_misto,
    },
]
