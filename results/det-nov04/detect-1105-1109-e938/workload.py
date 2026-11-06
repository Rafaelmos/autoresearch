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

Campanha det-nov04 (janelas de 120 min). Rodada 1: ablações por operação.
"""

CARD = "4111111111111111"
PHONE = "+5511988887777"
CARDS = ["41111111%08d" % k for k in range(20)]
PHONES = ["+55119888%05d" % k for k in range(20)]


def _associate_serial(rng, i):
    return "/associate_card", {"credit_card": CARD, "phone": PHONE}


def _retrieve_only(rng, i):
    return "/retrieve_cards", {"phone_numbers": [PHONE]}


def _misto_diverso(rng, i):
    if rng.random() < 0.5:
        return "/associate_card", {"credit_card": rng.choice(CARDS), "phone": rng.choice(PHONES)}
    k = rng.randint(1, 3)
    return "/retrieve_cards", {"phone_numbers": rng.sample(PHONES, k)}


CANDIDATES = [
    {
        "name": "escrita_serial_120",
        "hypothesis": "R1-A: com 1 thread (sem SQLITE_BUSY), escrita pura em 120 min mostra inclinação robusta >= 10 MB/h; se ficar < 2 MB/h, o caminho de escrita (transação + conexão nova) não envelhece sozinho.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _associate_serial,
    },
    {
        "name": "leitura_10t_120",
        "hypothesis": "R1-B: leitura pura com 10 threads (sem escrita, sem BUSY) retém memória nativa do sqlite3 (db.all + conexão por requisição); falsificada se robusto < 2 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _retrieve_only,
    },
    {
        "name": "misto_diverso_4t",
        "hypothesis": "R1-C: mix 50/50 com 20 cartões x 20 telefones e consultas de 1-3 telefones, 4 threads (pouco BUSY), expõe retenção ligada à diversidade de chaves; falsificada se robusto < 2 MB/h.",
        "threads": 4,
        "think_time_s": 0.01,
        "request": _misto_diverso,
    },
]
