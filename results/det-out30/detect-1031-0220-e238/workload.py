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

Rodada 5: amplificação e ablação controlada do achado da Rodada 4
(erro_500_controlado_4pct teve h1_slope=4,79 e h2_slope=6,20 MB/h, crescimento
monótono nas duas metades com 0 escritas após 25s).
"""


def _pad_card(idx, total_len=1960):
    base = "41111111%08d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


def _unicode_card(idx, n_spaces=310):
    return ("41111111%08d" % idx) + ("\u3000" * n_spaces)


def _pad_phone(idx, total_len=185):
    base = "+55119888%05d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


# E1: Amplifica D2 de 300 cartões (601 linhas) e 4,0% de 500 para 485 cartões de 1960 B
# (485 + 1 + 485 = 971 linhas <= 1000, populadas nos primeiros ~35s, 0 escritas após 35s)
# e 1/22 (4,54% < 5% E2) de TypeError síncrono em validation.js -> errorHandler.js
# com payload de ~1,75 KB (9 telefones válidos longos + 1 inteiro).
E_CARDS_485 = [_pad_card(k, 1960) for k in range(485)]
E_PHONE_MAIN = "+5511988800001"
E_9_LONG_PHONES = [_pad_phone(p, 185) for p in range(1, 10)]


def _erro500_45pct_resultset_971(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and step < 485:
        return "/associate_card", {"credit_card": E_CARDS_485[step], "phone": E_PHONE_MAIN}
    if step % 22 == 11:
        return "/retrieve_cards", {"phone_numbers": E_9_LONG_PHONES + [123456789012]}
    return "/retrieve_cards", {"phone_numbers": [E_PHONE_MAIN]}


# E2: Ablação exata de E1 (mesmos 485 cartões de 1960 B = 971 linhas populadas nos primeiros ~35s,
# 0 escritas após 35s, mesma frequência 1/22 = 4,54%, mesmo tamanho de payload), mas trocando o
# inteiro (500 TypeError -> errorHandler.js) por string inválida (400 Bad Request sem exceção).
E_BAD_PHONE_STR = _pad_phone(99, 175) + "X"


def _ablation_400_resultset_971(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and step < 485:
        return "/associate_card", {"credit_card": E_CARDS_485[step], "phone": E_PHONE_MAIN}
    if step % 22 == 11:
        return "/retrieve_cards", {"phone_numbers": E_9_LONG_PHONES + [E_BAD_PHONE_STR]}
    return "/retrieve_cards", {"phone_numbers": [E_PHONE_MAIN]}


# E3: Combina os dois melhores sinais da Rodada 4: 475 cartões Unicode multi-byte (\u3000,
# TwoByteString V8 <-> UTF-8 N-API, 475 + 1 + 475 = 951 linhas <= 1000, 0 escritas após 35s)
# intercalados com 1/22 (4,54% < 5% E2) de TypeError síncrono em validation.js -> errorHandler.js.
E_UNICODE_475 = [_unicode_card(k, 310) for k in range(475)]


def _erro500_45pct_unicode_951(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and step < 475:
        return "/associate_card", {"credit_card": E_UNICODE_475[step], "phone": E_PHONE_MAIN}
    if step % 22 == 11:
        return "/retrieve_cards", {"phone_numbers": E_9_LONG_PHONES + [123456789012]}
    return "/retrieve_cards", {"phone_numbers": [E_PHONE_MAIN]}


CANDIDATES = [
    {
        "name": "erro500_45pct_resultset_971",
        "hypothesis": "E1: elevar D2 (robust_slope=4,79 MB/h) para 485 cartões de 1960 B (971 linhas, ~950 KB/leitura, 0 escritas após 35s) + 4,54% de TypeError 500 (E1 < 5% E2) amplifica a inclinação acima de 10 MB/h.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _erro500_45pct_resultset_971,
    },
    {
        "name": "ablation_400_resultset_971",
        "hypothesis": "E2: ablação exata de E1 trocando apenas o 500 (TypeError -> errorHandler.js) por 400 (string inválida); se cair para o ruído enquanto E1 sobe, isola errorHandler.js + stack trace sob carga como causa.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _ablation_400_resultset_971,
    },
    {
        "name": "erro500_45pct_unicode_951",
        "hypothesis": "E3: combinar 475 cartões Unicode multi-byte (TwoByteString V8 <-> UTF-8 N-API, 951 linhas, rss_slope=10,38 MB/h em D1) com 4,54% de TypeError 500 sustenta inclinação > 10 MB/h nas duas metades.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _erro500_45pct_unicode_951,
    },
]
