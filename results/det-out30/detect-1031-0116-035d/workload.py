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

Rodada 4: strings Unicode multi-byte (TwoByteString V8 <-> UTF-8 N-API/SQLite),
caminho de erro 500 controlado em 4% (E1 permitido, abaixo de E2=5%) misturado a
leitura densa, e JOIN/GROUP BY/HAVING de 811 associações com interseção vazia (404).
"""


def _unicode_card(idx, n_spaces=310):
    # \u3000 (ideographic space) é aceito por \s em isValidCreditCard e gera TwoByteString no V8
    # e 3 bytes UTF-8 por caractere no SQLite/N-API (em JSON wire: 6 bytes "\\u3000" * 310 = 1860 B <= 2048 B).
    return ("41111111%08d" % idx) + ("\u3000" * n_spaces)


def _pad_card(idx, total_len=1800):
    base = "41111111%08d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


def _pad_phone(idx, total_len=180):
    base = "+55119888%05d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


# D1: 450 cartões Unicode multi-byte (\u3000) associados a 1 telefone (450 + 1 + 450 = 901 linhas <= 1000).
# Força transcodificação UTF-8 <-> UTF-16 (TwoByteString) em Napi::String e sqlite3_step.
D1_CARDS = [_unicode_card(k, 310) for k in range(450)]
D1_PHONE = "+5511988800000"


def _unicode_twobyte_resultset(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and (step < 450 or step % 40 == 0):
        idx = step % 450
        return "/associate_card", {"credit_card": D1_CARDS[idx], "phone": D1_PHONE}
    return "/retrieve_cards", {"phone_numbers": [D1_PHONE]}


# D2: 4% de requisições (1 em 25 -> 4,0% de 500, E1 pontuável e abaixo do limite E2 de 5%)
# acionam TypeError síncrono em validation.js -> errorHandler.js (formatação de stack trace V8),
# combinadas com 96% de operações em banco populado (300 cartões + 1 telefone + 300 assoc = 601 linhas).
D2_CARDS = [_pad_card(k, 1800) for k in range(300)]
D2_PHONE = "+5511988800001"


def _erro_500_controlado_4pct(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and step < 300:
        return "/associate_card", {"credit_card": D2_CARDS[step], "phone": D2_PHONE}
    if step % 25 == 12:
        # Envia inteiro em phone_numbers: Array.isArray passa, mas phoneNumber.replace lança TypeError (500)
        return "/retrieve_cards", {"phone_numbers": [123456789012]}
    return "/retrieve_cards", {"phone_numbers": [D2_PHONE]}


# D3: 90 cartões associados a 9 telefones (p0..p8) + 1 cartão associado a p9 (91 + 10 + 811 = 912 linhas <= 1000).
# A consulta com os 10 telefones [p0..p9] obriga o SQLite a varrer e agrupar as 811 associações na B-tree
# temporária de GROUP BY/COUNT(DISTINCT), mas resulta em interseção vazia no HAVING (= 10) -> resposta curta 404,
# maximizando a taxa de criação/destruição de B-trees temporárias por segundo.
D3_CARDS = [_pad_card(k, 1750) for k in range(91)]
D3_PHONES = [_pad_phone(p, 180) for p in range(10)]
D3_PAIRS = [(c, p) for c in range(90) for p in range(9)] + [(90, 9)]  # 811 associações


def _join_912_having_vazio_404(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and (step < len(D3_PAIRS) or step % 40 == 0):
        c_idx, p_idx = D3_PAIRS[step % len(D3_PAIRS)]
        return "/associate_card", {"credit_card": D3_CARDS[c_idx], "phone": D3_PHONES[p_idx]}
    return "/retrieve_cards", {"phone_numbers": D3_PHONES}


CANDIDATES = [
    {
        "name": "unicode_twobyte_resultset",
        "hypothesis": "D1: strings Unicode multi-byte (\\u3000, válidas em \\s) em 450 cartões (901 linhas) forçam alocação de TwoByteString no V8 e transcodificação UTF-8 no N-API/sqlite3 a cada /retrieve_cards.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _unicode_twobyte_resultset,
    },
    {
        "name": "erro_500_controlado_4pct",
        "hypothesis": "D2: 4,0% de erros 500 (TypeError em validation.js -> errorHandler.js, flag E1 pontuável < 5% E2) combinados com 96% de /retrieve_cards (601 linhas) testam retenção no caminho de exceção Express/V8.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _erro_500_controlado_4pct,
    },
    {
        "name": "join_912_having_vazio_404",
        "hypothesis": "D3: /retrieve_cards com 10 telefones sobre 811 associações (912 linhas) cuja interseção falha no HAVING COUNT(DISTINCT)=10 (404 curto) maximiza a taxa de B-trees temporárias no SQLite.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _join_912_having_vazio_404,
    },
]
