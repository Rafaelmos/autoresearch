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

Rodada 6 (seed 2): réplica direta do melhor braço da campanha até aqui
(erro_500_controlado_4pct, que teve robust_slope=4,794 e rss_slope=6,255 MB/h na Rodada 4),
combinação de fragmentação de result sets variados com TypeError em validateAssociateCard,
e contenção simétrica 3 writers / 3 readers em 6 threads.
"""


def _pad_card(idx, total_len=1800):
    base = "41111111%08d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


def _pad_phone(idx, total_len=180):
    base = "+55119888%05d" % idx
    pad_len = max(0, total_len - len(base))
    return base + (" -" * (pad_len // 2))


# F1: Réplica exata de erro_500_controlado_4pct (D2 da Rodada 4: robust_slope=4,794 MB/h,
# h1_slope=4,794, h2_slope=6,202, rss_slope=6,255 MB/h) na semente 2 para verificar se o
# crescimento monótono nas duas metades se sustenta em outra execução.
D2_CARDS = [_pad_card(k, 1800) for k in range(300)]
D2_PHONE = "+5511988800001"


def _erro_500_controlado_4pct(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and step < 300:
        return "/associate_card", {"credit_card": D2_CARDS[step], "phone": D2_PHONE}
    if step % 25 == 12:
        return "/retrieve_cards", {"phone_numbers": [123456789012]}
    return "/retrieve_cards", {"phone_numbers": [D2_PHONE]}


# F2: Combina a fragmentação de result sets de tamanhos múltiplos (450 cartões ~880 KB,
# 30 cartões ~58 KB, 1 cartão ~2 KB e 404, 934 linhas <= 1000, C2 da Rodada 3 com robust_slope=1,936 MB/h)
# com 4,0% de TypeError em validateAssociateCard (após limpar credit_card de 1950 B, phone numérico
# lança TypeError -> errorHandler.js).
F2_CARDS = [_pad_card(k, 1950) for k in range(450)]
F2_PHONES = ["+5511988800000", "+5511988800001", "+5511988800002"]
F2_PAIRS = [(k, 0) for k in range(450)] + [(k, 1) for k in range(30)] + [(0, 2)]


def _frag_misto_erro500_associate(rng, i):
    tid = i % 10
    step = i // 10
    if tid == 0 and step < len(F2_PAIRS):
        c_idx, p_idx = F2_PAIRS[step]
        return "/associate_card", {"credit_card": F2_CARDS[c_idx], "phone": F2_PHONES[p_idx]}
    if step % 25 == 12:
        return "/associate_card", {"credit_card": F2_CARDS[step % 450], "phone": 123456789012}
    mode = rng.randrange(4)
    if mode == 0:
        return "/retrieve_cards", {"phone_numbers": [F2_PHONES[0]]}
    if mode == 1:
        return "/retrieve_cards", {"phone_numbers": [F2_PHONES[0], F2_PHONES[1]]}
    if mode == 2:
        return "/retrieve_cards", {"phone_numbers": F2_PHONES}
    return "/retrieve_cards", {"phone_numbers": [F2_PHONES[2], "+5511999999999"]}


# F3: Contenção simétrica em 6 threads (3 escritoras em /associate_card + 3 leitoras em /retrieve_cards)
# sobre 250 cartões x 2 telefones (250 + 2 + 500 = 752 linhas <= 1000).
F3_CARDS = [_pad_card(k, 1800) for k in range(250)]
F3_PHONES = [_pad_phone(p, 180) for p in range(2)]


def _contencao_3w_3r_6threads(rng, i):
    tid = i % 6
    step = i // 6
    if tid in (0, 1, 2):
        pair_idx = (step * 3 + tid) % 500
        return "/associate_card", {
            "credit_card": F3_CARDS[pair_idx % 250],
            "phone": F3_PHONES[pair_idx // 250],
        }
    return "/retrieve_cards", {"phone_numbers": F3_PHONES[: rng.randint(1, 2)]}


CANDIDATES = [
    {
        "name": "erro_500_controlado_4pct",
        "hypothesis": "F1: réplica na semente 2 do melhor braço da Rodada 4 (robust_slope=4,794 MB/h, h1=4,794, h2=6,202 MB/h); verifica se a tendência monótona em 601 linhas + 4% TypeError é reprodutível.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _erro_500_controlado_4pct,
    },
    {
        "name": "frag_misto_erro500_associate",
        "hypothesis": "F2: combinar result sets de tamanhos múltiplos (880 KB, 58 KB, 2 KB e 404; 934 linhas) com 4% de TypeError em validateAssociateCard após alocar string limpa de 1950 B amplifica a fragmentação.",
        "threads": 10,
        "think_time_s": 0.01,
        "request": _frag_misto_erro500_associate,
    },
    {
        "name": "contencao_3w_3r_6threads",
        "hypothesis": "F3: 6 threads (3 writers / 3 readers, 752 linhas de 1800 B) elevam a fração de transações /associate_card e ROLLBACK por SQLITE_BUSY (~1-4% 5xx, abaixo de E2) sem saturar a CPU.",
        "threads": 6,
        "think_time_s": 0.01,
        "request": _contencao_3w_3r_6threads,
    },
]
