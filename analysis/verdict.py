"""Veredito pós-hoc por braço, lendo results/<run>/<braço>/evaluation.json (somente leitura).

Não altera o juiz nem a pontuação oficial. Critérios (de program_detect.md, 'critério robusto'):
  MK de alta p < 0,01; min(Sen primeira metade, segunda metade) >= 5 MB/h;
  candidato - baseline >= max(2 MB/h, 25% de |baseline|); sem flags que invalidam.
Vereditos (vocabulário do llm-aging-detection-agents, adaptado: aqui não há instrumentação de
caminho executado, então 'ativado' = MK de alta significativo no RSS):
  ACTIVATED_WITH_AGING  todos os critérios passam (ainda exige réplica em 3 sementes: confirm)
  ACTIVATED_NO_SYMPTOM  MK significativo, mas efeito pequeno, degrau ou indistinto da baseline
  NOT_ACTIVATED         sem tendência de alta significativa
  INCONCLUSIVE          braço inválido, saturado (D1/E2) ou sem baseline na rodada

Uso: python analysis/verdict.py results/<grupo>/<run_id> [...]
"""
import json
import sys
from pathlib import Path

ALPHA, MIN_HALVES, MIN_DELTA, REL_DELTA = 0.01, 5.0, 2.0, 0.25
BLOCKING = {"D1_saturacao", "E2_erro_dominante_revisao_humana"}


def load_arms(run: Path) -> dict:
    return {p.parent.name: json.loads(p.read_text()) for p in sorted(run.glob("*/evaluation.json"))}


def judge(ev: dict, base: dict | None) -> tuple[str, str]:
    flags = set(ev.get("flags", []))
    if not ev.get("valid", True) or flags & BLOCKING:
        return "INCONCLUSIVE", f"inválido/saturado ({', '.join(sorted(flags & BLOCKING)) or 'valid=false'})"
    if base is None:
        return "INCONCLUSIVE", "sem baseline na rodada"
    rss = ev["rss_mb"]
    if rss["mk_p_upward"] >= ALPHA:
        return "NOT_ACTIVATED", f"MK p={rss['mk_p_upward']:.2g}"
    halves = min(rss["sen_slope_first_half_per_h"], rss["sen_slope_second_half_per_h"])
    b = base["rss_mb"]["sen_slope_per_h"]
    delta = rss["sen_slope_per_h"] - b
    need = max(MIN_DELTA, REL_DELTA * abs(b))
    why = f"min das metades {halves:.1f} MB/h (exige {MIN_HALVES}); delta vs baseline {delta:.1f} (exige {need:.1f})"
    if halves >= MIN_HALVES and delta >= need:
        kind = "nativo (heap plano)" if ev["heap_mb"]["sen_slope_per_h"] < 0.1 * rss["sen_slope_per_h"] else "heap"
        return "ACTIVATED_WITH_AGING", f"{why}; retenção {kind}"
    return "ACTIVATED_NO_SYMPTOM", why


def main() -> None:
    for arg in sys.argv[1:]:
        run = Path(arg)
        arms = load_arms(run)
        base = next((v for k, v in arms.items() if k.startswith("baseline")), None)
        print(f"== {run.name}")
        for name, ev in arms.items():
            verdict, why = judge(ev, None if name.startswith("baseline") else base)
            if name.startswith("baseline"):
                verdict, why = "BASELINE", f"Sen {ev['rss_mb']['sen_slope_per_h']:.1f} MB/h"
            print(f"{name:40s} {verdict:22s} {why}")


if __name__ == "__main__":
    main()
