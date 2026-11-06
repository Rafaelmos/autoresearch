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


def _leitura_serial(rng, i):
    return "/retrieve_cards", {"phone_numbers": [PHONE]}


def _misto_serial_diverso(rng, i):
    if i % 2 == 0:
        return "/associate_card", {"credit_card": rng.choice(CARDS), "phone": rng.choice(PHONES)}
    return "/retrieve_cards", {"phone_numbers": rng.sample(PHONES, rng.randint(1, 3))}


def _leitura_larga_serial(rng, i):
    return "/retrieve_cards", {"phone_numbers": rng.sample(PHONES, 10)}


CANDIDATES = [
    {
        "name": "leitura_serial_120",
        "hypothesis": "R2-A: leitura pura serial (1 thread) em 120 min; se a retenção nativa vem do db.all + conexão por requisição, robusto >= 10 MB/h; falsificada se < 2 MB/h.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _leitura_serial,
    },
    {
        "name": "misto_serial_diverso_120",
        "hypothesis": "R2-B: mix 50/50 serial com 20 cartões x 20 telefones; retenção ligada à interação escrita+leitura com chaves variadas; falsificada se robusto < 2 MB/h.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _misto_serial_diverso,
    },
    {
        "name": "leitura_larga_serial_120",
        "hypothesis": "R2-C: consultas com 10 telefones (IN/JOIN largo) serial retêm memória nativa por requisição; falsificada se robusto < 2 MB/h.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _leitura_larga_serial,
    },
]
