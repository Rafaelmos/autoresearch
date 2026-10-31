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

Rodada 2: teste de result sets massivos (~945 KB/req), JOIN/HAVING com 10 telefones
longos e escrita transacional intensa com 2 threads (abaixo do teto E2 de 5% 5xx).
"""


def _pad_card(idx, total_len=1960):
    base = "41111111%08d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


def _pad_phone(idx, total_len=180):
    base = "+55119888%05d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


# B1: 480 cartões de 1960 B associados a 1 telefone -> 480 + 1 + 480 = 961 linhas (<= 1000).
# Cada /retrieve_cards retorna 480 * 1960 B ≈ 940 KB do SQLite para o Node.js.
B1_CARDS = [_pad_card(k, 1960) for k in range(480)]
B1_PHONE = "+5511988800000"


def _resultset_largo_961(rng, i):
    tid = i % 10
    step = i // 10
    # Apenas tid == 0 escreve na fase inicial / manutenção leve (evita SQLITE_BUSY concorrente)
    if tid == 0 and (step < 480 or step % 50 == 0):
        idx = step % 480
        return "/associate_card", {"credit_card": B1_CARDS[idx], "phone": B1_PHONE}
    return "/retrieve_cards", {"phone_numbers": [B1_PHONE]}


# B2: 88 cartões de 1780 B associados a 10 telefones de 180 B -> 88 + 10 + 880 = 978 linhas (<= 1000).
# Cada /retrieve_cards passa os 10 telefones de 180 B (JSON ~1860 B <= 2048 B), forçando
# JOIN de 880 associações + GROUP BY cc.id + HAVING COUNT(DISTINCT p.id) = 10.
B2_CARDS = [_pad_card(k, 1780) for k in range(88)]
B2_PHONES = [_pad_phone(p, 180) for p in range(10)]


def _join_having_10_fones(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and (step < 880 or step % 40 == 0):
        pair_idx = step % 880
        c_idx = pair_idx // 10
        p_idx = pair_idx % 10
        return "/associate_card", {"credit_card": B2_CARDS[c_idx], "phone": B2_PHONES[p_idx]}
    return "/retrieve_cards", {"phone_numbers": B2_PHONES}


# B3: escrita transacional intensa (90% /associate_card, 10% /retrieve_cards) com 2 threads
# e strings de ~960 B, reciclando 300 cartões x 2 telefones = 300 + 2 + 600 = 902 linhas (<= 1000).
B3_CARDS = [_pad_card(k, 960) for k in range(300)]
B3_PHONES = [_pad_phone(p, 960) for p in range(2)]


def _escrita_2_threads_longa(rng, i):
    step = i // 2
    if step % 10 != 9:
        pair_idx = (i // 2) % 600
        return "/associate_card", {
            "credit_card": B3_CARDS[pair_idx % 300],
            "phone": B3_PHONES[pair_idx // 300],
        }
    return "/retrieve_cards", {"phone_numbers": [B3_PHONES[step % 2]]}


CANDIDATES = [
    {
        "name": "resultset_largo_961",
        "hypothesis": "B1: /retrieve_cards retornando 480 cartões de 1960 B (~940 KB/consulta, 961 linhas no banco) sob 10 threads causa retenção/fragmentação nativa em RowsBaton do sqlite3 (robust_slope >= 10 MB/h).",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _resultset_largo_961,
    },
    {
        "name": "join_having_10_fones",
        "hypothesis": "B2: /retrieve_cards com 10 telefones de 180 B sobre 880 associações (978 linhas) força B-tree temporária no JOIN + GROUP BY + HAVING COUNT(DISTINCT) = 10 por conexão efêmera (robust_slope >= 10 MB/h).",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _join_having_10_fones,
    },
    {
        "name": "escrita_2_threads_longa",
        "hypothesis": "B3: 90% /associate_card com strings de 960 B (902 linhas) em 2 threads maximiza transações BEGIN..COMMIT completas por segundo mantendo 5xx abaixo de 5% (E2) (robust_slope >= 10 MB/h).",
        "threads": 2,
        "think_time_s": 0.01,
        "request": _escrita_2_threads_longa,
    },
]
