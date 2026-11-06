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


def _escrita_diversa(rng, i):
    return "/associate_card", {"credit_card": rng.choice(CARDS), "phone": rng.choice(PHONES)}


def _leitura_inexistente(rng, i):
    return "/retrieve_cards", {"phone_numbers": ["+5521977%06d" % rng.randint(0, 999999) for _ in range(3)]}


def _misto_com_5xx(rng, i):
    # ~3% de requisições com credit_card numérico: o validador chama .replace e lança TypeError -> errorHandler (5xx)
    if rng.random() < 0.03:
        return "/associate_card", {"credit_card": 4111111111111111, "phone": PHONE}
    if i % 2 == 0:
        return "/associate_card", {"credit_card": rng.choice(CARDS), "phone": rng.choice(PHONES)}
    return "/retrieve_cards", {"phone_numbers": [rng.choice(PHONES)]}


CANDIDATES = [
    {
        "name": "escrita_diversa_serial",
        "hypothesis": "R3-A: escrita serial com 20x20 chaves (INSERT OR IGNORE em linhas existentes e novas) retém memória nativa; falsificada se robusto < 2 MB/h.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _escrita_diversa,
    },
    {
        "name": "leitura_inexistente_serial",
        "hypothesis": "R3-B: consultas com telefones aleatórios inexistentes (caminho notFound, sem linhas) retêm memória nativa (statement/JOIN vazio); falsificada se robusto < 2 MB/h.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _leitura_inexistente,
    },
    {
        "name": "misto_com_5xx_serial",
        "hypothesis": "R3-C: ~3% de erros 500 via errorHandler (TypeError no validador, stack logada) acumulam memória; falsificada se robusto < 2 MB/h. Gera E1 por construção.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _misto_com_5xx,
    },
]
