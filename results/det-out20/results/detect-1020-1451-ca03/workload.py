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

Rodada inicial: ablações para localizar QUAL operação causa a tendência.
"""

CARD = "4111111111111111"
PHONE = "+5511988887777"


def _pool_cards(rng):
    return "41111111111%05d" % rng.randrange(10)


def _pool_phone(rng):
    return "+55119888%05d" % rng.randrange(10)


def _mix_varied(rng, i):
    if i % 2 == 0:
        return "/associate_card", {"credit_card": _pool_cards(rng), "phone": _pool_phone(rng)}
    return "/retrieve_cards", {"phone_numbers": [_pool_phone(rng) for _ in range(rng.randint(1, 10))]}


def _retrieve_10(rng, i):
    return "/retrieve_cards", {"phone_numbers": [_pool_phone(rng) for _ in range(10)]}


def _read_heavy(rng, i):
    if i % 10 == 0:
        return "/associate_card", {"credit_card": _pool_cards(rng), "phone": _pool_phone(rng)}
    return "/retrieve_cards", {"phone_numbers": [_pool_phone(rng) for _ in range(rng.randint(1, 3))]}


CANDIDATES = [
    {
        "name": "mix_variado",
        "hypothesis": "B1: valores variados (10 cartões x 10 telefones, listas de 1-10) em mix 1:1 retêm mais memória nativa que a baseline de valores fixos (RSS > 5 MB/h); falsificada se ficar no ruído.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _mix_varied,
    },
    {
        "name": "retrieve_10",
        "hypothesis": "B2: SQL com 10 placeholders compilado em conexão nova a cada requisição retém mais memória nativa que 1 placeholder (so_retrieve=0,61 MB/h); falsificada se < 5 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _retrieve_10,
    },
    {
        "name": "leitura_pesada",
        "hypothesis": "B3: 90% leitura / 10% escrita gera SQLITE_BUSY em leituras (caminho de erro com db.close) sem saturar; falsificada se RSS < 5 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _read_heavy,
    },
]
