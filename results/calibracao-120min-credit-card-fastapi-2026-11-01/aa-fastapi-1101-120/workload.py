"""Teste A/A (rodar UMA vez, pelo humano, antes da campanha).

Três cópias idênticas da baseline do artigo nos 3 slots de candidatos.
Como as cargas são iguais, toda diferença entre os 4 braços é RUÍDO.
Use o resultado para calibrar a margem de "keep" (hoje +10%).

Uso:  cp workload.py workload_campanha.py && cp workload_aa.py workload.py
      python prepare.py detect            # 60 min
      cp workload_campanha.py workload.py
"""


def _baseline_request(rng, i):
    if i % 2 == 0:
        return "/associate_card", {"credit_card": "4111111111111111", "phone": "+5511988887777"}
    return "/retrieve_cards", {"phone_numbers": ["+5511988887777"]}


CANDIDATES = [
    {"name": f"aa_copia_{k}", "hypothesis": "A/A: cópia idêntica da baseline; mede ruído.",
     "threads": 10, "think_time_s": 0.01, "request": _baseline_request}
    for k in (1, 2, 3)
]
