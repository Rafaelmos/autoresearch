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


def _retrieve_n(n, width):
    def f(rng, i):
        return "/retrieve_cards", {"phone_numbers": [_pad("+55119888%05d" % rng.randrange(10), width) for _ in range(n)]}
    return f


CANDIDATES = [
    {
        "name": "retrieve_meio",
        "hypothesis": "D1: dose-resposta. 10 telefones de 75 caracteres (cerca de 0,8 KB) devem render cerca de metade dos 6,6 MB/h de retrieve_longo; se render o mesmo ou nada, o efeito não escala com bytes.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _retrieve_n(10, 75),
    },
    {
        "name": "retrieve_max",
        "hypothesis": "D2: 10 telefones de 195 caracteres (cerca de 2,0 KB, máximo do contrato) devem render mais que retrieve_longo; se ficar abaixo de 5 MB/h, o resultado da rodada 3 era ruído.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _retrieve_n(10, 195),
    },
    {
        "name": "retrieve_1_longo",
        "hypothesis": "D3: 1 telefone de 1900 caracteres (mesmos bytes, 1 placeholder) separa tamanho do valor de quantidade de binds; se render como retrieve_max, o fator é o tamanho da string, não o número de placeholders.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _retrieve_n(1, 1900),
    },
]
