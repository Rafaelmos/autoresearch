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


def _pad(value, width):
    # espaços e hífens são removidos pela validação; o valor segue válido
    return value + " -" * ((width - len(value)) // 2)


N_CARDS = 100
PHONES = ["+55119888%05d" % k for k in range(5)]


def _card(k):
    return "41111111%08d" % (k % N_CARDS)


def _base_densa(rng, i):
    # associações em sequência (100 cartões x 5 telefones = 500 pares, 605 linhas, abaixo de D2);
    # leituras devolvem até 100 cartões por telefone
    if i % 2 == 0:
        k = i // 2
        return "/associate_card", {"credit_card": _card(k), "phone": PHONES[(k // N_CARDS) % 5]}
    return "/retrieve_cards", {"phone_numbers": [PHONES[rng.randrange(5)]]}


def _leitura_densa(rng, i):
    # 1 escrita para cada 9 leituras de 1 a 3 telefones
    if i % 10 == 0:
        k = i // 10
        return "/associate_card", {"credit_card": _card(k), "phone": PHONES[(k // N_CARDS) % 5]}
    return "/retrieve_cards", {"phone_numbers": [PHONES[rng.randrange(5)] for _ in range(rng.randint(1, 3))]}


CANDIDATES = [
    {
        "name": "densa_10_threads",
        "hypothesis": "G1: banco com 600 linhas, em que cada leitura devolve até 100 cartões, retém memória nativa de result set (RSS > 5 MB/h, heap plano); falsificada se ficar no ruído de 0,5-1,5.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _base_densa,
    },
    {
        "name": "densa_1_thread",
        "hypothesis": "G2: mesma carga com 1 thread, sem SQLITE_BUSY; separa o efeito do volume de resultado do efeito da contenção.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _base_densa,
    },
    {
        "name": "leitura_densa",
        "hypothesis": "G3: 90% leituras de 1 a 3 telefones sobre o banco denso (cada leitura devolve até 100 cartões ou faz o JOIN com HAVING): se o custo está no result set, deve passar de 5 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _leitura_densa,
    },
]
