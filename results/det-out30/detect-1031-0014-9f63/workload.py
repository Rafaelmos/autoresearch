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

Rodada 3: contenção controlada escrita/leitura (3 writers / 7 readers com strings longas),
fragmentação de alocador por alternância de result sets (0 B, 2 KB, 58 KB e 880 KB),
e estresse de strings/regex de 2 KB no caminho de validação (400).
"""


def _pad_card(idx, total_len=1950):
    base = "41111111%08d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


def _pad_phone(idx, total_len=180):
    base = "+55119888%05d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


# C1: 3 threads escritoras + 7 threads leitoras sobre 200 cartões x 3 telefones (200 + 3 + 600 = 803 linhas <= 1000).
# Isola se a contenção moderada de escrita (SQLITE_BUSY + ROLLBACK + trace.js com argumentos longos, mantendo 5xx < 5%)
# retém memória nativa ao longo de 60 min.
C1_CARDS = [_pad_card(k, 1750) for k in range(200)]
C1_PHONES = [_pad_phone(p, 180) for p in range(3)]


def _contencao_3w_7r(rng, i):
    tid = i % 10
    step = i // 10
    if tid in (0, 1, 2):
        pair_idx = (step * 3 + tid) % 600
        return "/associate_card", {
            "credit_card": C1_CARDS[pair_idx % 200],
            "phone": C1_PHONES[pair_idx // 200],
        }
    return "/retrieve_cards", {"phone_numbers": C1_PHONES[: rng.randint(1, 3)]}


# C2: Fragmentação do alocador nativo (glibc ptmalloc2 / sqlite3 RowsBaton) alternando
# consultas que retornam 450 cartões (~880 KB), 30 cartões (~58 KB), 1 cartão (~2 KB) e 0 cartões (404),
# com estado estacionário (450 cartões + 3 telefones + 481 associações = 934 linhas <= 1000) populado nos primeiros 15s.
C2_CARDS = [_pad_card(k, 1950) for k in range(450)]
C2_PHONES = ["+5511988800000", "+5511988800001", "+5511988800002"]
C2_PAIRS = (
    [(k, 0) for k in range(450)]
    + [(k, 1) for k in range(30)]
    + [(0, 2)]
)  # 481 associações


def _fragmentacao_resultset_misto(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and (step < len(C2_PAIRS) or step % 25 == 0):
        c_idx, p_idx = C2_PAIRS[step % len(C2_PAIRS)]
        return "/associate_card", {"credit_card": C2_CARDS[c_idx], "phone": C2_PHONES[p_idx]}
    mode = rng.randrange(4)
    if mode == 0:
        return "/retrieve_cards", {"phone_numbers": [C2_PHONES[0]]}  # ~880 KB (450 cartões)
    if mode == 1:
        return "/retrieve_cards", {"phone_numbers": [C2_PHONES[0], C2_PHONES[1]]}  # ~58 KB (30 cartões)
    if mode == 2:
        return "/retrieve_cards", {"phone_numbers": C2_PHONES}  # ~2 KB (1 cartão)
    return "/retrieve_cards", {"phone_numbers": [C2_PHONES[2], "+5511999999999"]}  # 404 (0 cartões)


# C3: Estresse de validação e parser Express/V8 (0 linhas no banco, sem D4):
# 80% /retrieve_cards com 10 telefones de 190 B (o 10º inválido após replace de regex) e
# 20% /associate_card com cartão de 1900 B inválido no último caractere.
C3_VALID_PHONES = [_pad_phone(p, 185) for p in range(9)]
C3_BAD_PHONE = _pad_phone(9, 180) + "X"
C3_BAD_CARDS = [_pad_card(k, 1780) + "X" for k in range(20)]


def _regex_validacao_2kb(rng, i):
    if i % 5 == 0:
        return "/associate_card", {
            "credit_card": C3_BAD_CARDS[rng.randrange(20)],
            "phone": C3_VALID_PHONES[0],
        }
    return "/retrieve_cards", {"phone_numbers": C3_VALID_PHONES + [C3_BAD_PHONE]}


CANDIDATES = [
    {
        "name": "contencao_3w_7r",
        "hypothesis": "C1: 3 threads em /associate_card e 7 em /retrieve_cards (803 linhas, strings de 1750 B) geram SQLITE_BUSY/ROLLBACK com trace.js (< 5% 5xx) e testam se o caminho de rollback retém memória nativa.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _contencao_3w_7r,
    },
    {
        "name": "fragmentacao_resultset_misto",
        "hypothesis": "C2: alternar result sets de 880 KB (450 cartões), 58 KB (30 cartões), 2 KB (1 cartão) e 404 (0 cartões) com escritas intercaladas (934 linhas) fragmenta arenas nativas do glibc/sqlite3.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _fragmentacao_resultset_misto,
    },
    {
        "name": "regex_validacao_2kb",
        "hypothesis": "C3: payloads de ~2 KB barrados na validação regex após percorrer 9 itens válidos (80% retrieve / 20% associate, 0 linhas no banco) testam retenção em V8/Express sem abrir SQLite.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _regex_validacao_2kb,
    },
]
