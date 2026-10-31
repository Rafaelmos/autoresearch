"""Carga experimental - ÚNICO arquivo que o agente edita na campanha de DETECÇÃO.

Equivale ao train.py do karpathy/autoresearch. A baseline do artigo roda sempre
no 4º slot (harness/load.py: BASELINE) e não é declarada aqui.

Contrato (imposto por harness/load.py; violar invalida o braço):
- CANDIDATES: 1 a 3 dicts com name, hypothesis, threads, think_time_s, request.
- threads em [1, 10]; think_time_s >= 0.01  (limites do artigo: 10 threads, 0,01 s).
- request(rng, i) -> (path, body_dict). path em {/associate_card, /retrieve_cards};
  body JSON <= 2048 bytes; phone_numbers com no máximo 10 itens.
- Mais de 1000 linhas no banco ao fim marcam D2: o braço é medido, mas não pontua.

Rodada de RÉPLICA (31/10, juiz v2 @ fix/juiz-v2): repete, sem alterar nada, os três
candidatos da campanha det-out30 que mais subiram, para testar se o efeito se repete.

| Candidato                   | Origem (det-out30)          | Slope original | Linhas |
|-----------------------------|-----------------------------|----------------|--------|
| unicode_twobyte_resultset   | detect-1031-0116-035d (D1)  | 10,38 MB/h     | 901    |
| join_912_having_vazio_404   | detect-1031-0116-035d (D3)  |  6,25 MB/h     | 912    |
| erro500_45pct_resultset_971 | detect-1031-0220-e238 (E1)  |  7,66 MB/h     | 971    |

O banco é populado pela thread 0 nos primeiros ~35-70 s (dentro dos 300 s de aquecimento)
e fica com no máximo 971 linhas (< 1000, sem D2). Nenhum candidato usa o rng: a carga é
idêntica à original; a réplica mede só a variabilidade de execução.
"""


def _pad_card(idx, total_len):
    base = "41111111%08d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


def _pad_phone(idx, total_len):
    base = "+55119888%05d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


def _unicode_card(idx, n_spaces):
    # \u3000 (espaço ideográfico) passa no \s de isValidCreditCard e vira TwoByteString no V8
    return ("41111111%08d" % idx) + ("\u3000" * n_spaces)


# --- R1 = D1 da det-out30: 450 cartões Unicode + 1 telefone + 450 associações = 901 linhas
R1_CARDS = [_unicode_card(k, 310) for k in range(450)]
R1_PHONE = "+5511988800000"


def _unicode_twobyte_resultset(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and (step < 450 or step % 40 == 0):
        idx = step % 450
        return "/associate_card", {"credit_card": R1_CARDS[idx], "phone": R1_PHONE}
    return "/retrieve_cards", {"phone_numbers": [R1_PHONE]}


# --- R2 = D3 da det-out30: 91 cartões + 10 telefones + 811 associações = 912 linhas
R2_CARDS = [_pad_card(k, 1750) for k in range(91)]
R2_PHONES = [_pad_phone(p, 180) for p in range(10)]
R2_PAIRS = [(c, p) for c in range(90) for p in range(9)] + [(90, 9)]


def _join_912_having_vazio_404(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and (step < len(R2_PAIRS) or step % 40 == 0):
        c_idx, p_idx = R2_PAIRS[step % len(R2_PAIRS)]
        return "/associate_card", {"credit_card": R2_CARDS[c_idx], "phone": R2_PHONES[p_idx]}
    return "/retrieve_cards", {"phone_numbers": R2_PHONES}


# --- R3 = E1 da det-out30: 485 cartões de 1960 B + 1 telefone + 485 associações = 971 linhas,
#     sem escritas depois do preenchimento, e 1/22 (4,54%) de TypeError 500 (E1, abaixo de E2)
R3_CARDS = [_pad_card(k, 1960) for k in range(485)]
R3_PHONE = "+5511988800001"
R3_LONG_PHONES = [_pad_phone(p, 185) for p in range(1, 10)]


def _erro500_45pct_resultset_971(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and step < 485:
        return "/associate_card", {"credit_card": R3_CARDS[step], "phone": R3_PHONE}
    if step % 22 == 11:
        return "/retrieve_cards", {"phone_numbers": R3_LONG_PHONES + [123456789012]}
    return "/retrieve_cards", {"phone_numbers": [R3_PHONE]}


CANDIDATES = [
    {
        "name": "rep_unicode_twobyte_resultset",
        "hypothesis": "Réplica de D1 (det-out30, 10,38 MB/h): 450 cartões Unicode \\u3000 (901 linhas) forçam "
                      "TwoByteString no V8 e transcodificação UTF-8 no N-API/sqlite3 a cada /retrieve_cards. "
                      "Se o efeito for real, slope e menor metade >= 5 MB/h de novo.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _unicode_twobyte_resultset,
    },
    {
        "name": "rep_join_912_having_vazio_404",
        "hypothesis": "Réplica de D3 (det-out30, 6,25 MB/h): /retrieve_cards com 10 telefones sobre 811 associações "
                      "(912 linhas) e interseção vazia no HAVING (404) maximiza B-trees temporárias no SQLite.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _join_912_having_vazio_404,
    },
    {
        "name": "rep_erro500_45pct_resultset_971",
        "hypothesis": "Réplica de E1 (det-out30, 7,66 MB/h): result sets de ~950 KB (971 linhas, sem escritas "
                      "após o preenchimento) + 4,54% de TypeError 500 em validation.js -> errorHandler.js.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _erro500_45pct_resultset_971,
    },
]
