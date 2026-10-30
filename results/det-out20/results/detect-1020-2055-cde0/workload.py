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


PHONES = ["+55119888%05d" % k for k in range(5)]


def _leitura_densa(n_cards):
    # 1 escrita para cada 9 leituras de 1 a 3 telefones; n_cards x 5 telefones pares
    def f(rng, i):
        if i % 10 == 0:
            k = i // 10
            return "/associate_card", {"credit_card": "41111111%08d" % (k % n_cards), "phone": PHONES[(k // n_cards) % 5]}
        return "/retrieve_cards", {"phone_numbers": [PHONES[rng.randrange(5)] for _ in range(rng.randint(1, 3))]}
    return f


CANDIDATES = [
    {
        "name": "leitura_densa_replica",
        "hypothesis": "H1: réplica de leitura_densa (100 cartões, 605 linhas, 8,46 MB/h). Se voltar a >= 5 MB/h com a baseline plana, o efeito é real; abaixo de 2, foi ruído.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _leitura_densa(100),
    },
    {
        "name": "leitura_rala",
        "hypothesis": "H2: mesma carga com 5 cartões (35 linhas, leituras devolvem até 5 cartões). Se a retenção vem do tamanho do result set, a inclinação cai para o ruído (< 2 MB/h).",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _leitura_densa(5),
    },
    {
        "name": "leitura_densissima",
        "hypothesis": "H3: 150 cartões (905 linhas, abaixo de D2; leituras devolvem até 150 cartões). Se o efeito escala com o result set, a inclinação supera a de 100 cartões.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _leitura_densa(150),
    },
]
