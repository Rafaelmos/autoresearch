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


def _only_associate(rng, i):
    return "/associate_card", {"credit_card": CARD, "phone": PHONE}


def _only_retrieve(rng, i):
    return "/retrieve_cards", {"phone_numbers": [PHONE]}


def _invalid_inputs(rng, i):
    if i % 2 == 0:
        return "/associate_card", {"credit_card": "abc", "phone": PHONE}
    return "/retrieve_cards", {"phone_numbers": []}


CANDIDATES = [
    {
        "name": "so_associate",
        "hypothesis": "A1: a retenção vem do caminho de escrita (transação + conexão nova por requisição).",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _only_associate,
    },
    {
        "name": "so_retrieve",
        "hypothesis": "A2: a retenção vem do caminho de leitura (db.all + conexão nova por requisição).",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _only_retrieve,
    },
    {
        "name": "so_invalidas",
        "hypothesis": "A3: controle sem banco. Requisições barradas na validação não abrem conexão; espera-se tendência nula.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _invalid_inputs,
    },
]
