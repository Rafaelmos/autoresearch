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


LONG_CARD = _pad("4111111111111111", 300)


def _long_phone(rng):
    return _pad("+55119888%05d" % rng.randrange(10), 150)


def _mix_longo(rng, i):
    if i % 2 == 0:
        return "/associate_card", {"credit_card": LONG_CARD, "phone": _long_phone(rng)}
    return "/retrieve_cards", {"phone_numbers": [_long_phone(rng)]}


def _retrieve_longo(rng, i):
    return "/retrieve_cards", {"phone_numbers": [_long_phone(rng) for _ in range(10)]}


def _tipo_invalido(rng, i):
    # phone_numbers com número (não string): isValidPhone lança TypeError -> 500 da app
    return "/retrieve_cards", {"phone_numbers": [12345678901]}


def _mix_invertido(rng, i):
    # mesmos valores da baseline, ordem trocada (começa por leitura)
    if i % 2 == 1:
        return "/associate_card", {"credit_card": "4111111111111111", "phone": "+5511988887777"}
    return "/retrieve_cards", {"phone_numbers": ["+5511988887777"]}


def _associate_fixo(rng, i):
    return "/associate_card", {"credit_card": "4111111111111111", "phone": "+5511988887777"}


def _retrieve_fixo(rng, i):
    return "/retrieve_cards", {"phone_numbers": ["+5511988887777"]}


CANDIDATES = [
    {
        "name": "mix_1_thread_replica",
        "hypothesis": "F1: réplica de mix_1_thread (6,13 MB/h na rodada 5). Se voltar a >= 5 MB/h com MK p<0,01, o efeito de baixa concorrência é real; se ficar perto de 1, foi ruído.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _mix_invertido,
    },
    {
        "name": "associate_1_thread",
        "hypothesis": "F2: com 1 thread não há SQLITE_BUSY, então escrita pura é válida; se a retenção vier de associate_card (transação, 4 statements), a inclinação passa de 5 MB/h e retrieve_1_thread não.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _associate_fixo,
    },
    {
        "name": "retrieve_1_thread",
        "hypothesis": "F3: leitura pura com 1 thread; se a retenção vier de retrieve_cards, a inclinação passa de 5 MB/h e associate_1_thread não.",
        "threads": 1,
        "think_time_s": 0.01,
        "request": _retrieve_fixo,
    },
]
