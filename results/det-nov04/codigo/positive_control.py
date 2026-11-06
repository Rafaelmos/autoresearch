"""Controle positivo/negativo do juiz (humano roda, fora do laço do agente).

Roda 4 instâncias em paralelo com a carga da BASELINE do artigo, em cópias da app
com vazamento nativo INJETADO de taxa conhecida (MB/h): 0 (controle negativo), 10, 20, 40.
Usa o mesmo run_arms/evaluate_arm do juiz. Pergunta respondida: o detector, nesta duração e
com 4 instâncias disputando a máquina, recupera um vazamento de 10 MB/h (o piso)?

Uso: python calibration/positive_control.py --minutes 120 [--smoke]
Não escreve em results/judge_log.jsonl; saída em results/calibration-<id>/ e calibration_summary.json.
Fica fora de FIXED_GLOBS e de apps/credit-card/original (o manifesto não muda).
"""
import argparse, json, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import prepare as P  # noqa: E402
from harness.load import BASELINE  # noqa: E402

RATES = [0, 10, 20, 40]  # MB/h injetados
HOOK = """
// --- vazamento injetado (calibração): {rate} MB/h = {bps} bytes/s, retidos e tocados (RSS real) ---
const __leak = [];
setInterval(() => {{ __leak.push(Buffer.alloc({bps}, 1)); }}, 1000).unref();
// ---------------------------------------------------------------------------------------------
"""


def build(rate, dst):
    P.copy_tree_writable(P.ORIGINAL, dst)
    if rate:
        idx = dst / "index.js"
        bps = round(rate * 1e6 / 3600)
        idx.write_text(HOOK.format(rate=rate, bps=bps) + idx.read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=120)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    P.verify(quiet=True)
    minutes = 2 if a.smoke else a.minutes
    rid = f"calibration-{time.strftime('%m%d-%H%M')}" + ("-smoke" if a.smoke else "")
    rd = ROOT / "results" / rid
    rd.mkdir(parents=True, exist_ok=True)
    wl = rd / "workload.py"
    shutil.copyfile(ROOT / "workload.py", wl)
    meta = {"name": BASELINE["name"], "hypothesis": "controle positivo", "threads": BASELINE["threads"],
            "think_time_s": BASELINE["think_time_s"]}
    arms = []
    for r in RATES:
        d = rd / f"_app_leak_{r}"
        build(r, d)
        arms.append({"label": f"leak_{r}_mbh", "app_dir": d, "spec": meta, "workload_path": wl, "seed": a.seed})
    res = P.run_arms(arms, minutes, rd, a.smoke)
    P.verify(quiet=True)  # a calibração não pode ter alterado o juiz
    out = []
    for r in RATES:
        ev = res[f"leak_{r}_mbh"]
        s = ev.get("rss_mb", {})
        g, rb = s.get("sen_slope_per_h"), s.get("robust_slope_per_h")
        det = bool(ev.get("valid") and g is not None and rb is not None and g >= 10 and rb >= 10
                   and ev.get("rss_upward_significant"))
        out.append({"injetado_mb_h": r, "rss_slope": g, "robust_slope": rb, "valid": ev.get("valid"),
                    "flags": ev.get("flags"), "detectado_pela_regra_do_juiz": det,
                    "recuperacao_robusta_pct": (100 * rb / r) if (r and rb is not None) else None})
    (rd / "calibration_summary.json").write_text(json.dumps(
        {"minutes": minutes, "seed": a.seed, "smoke": a.smoke, "arms": out}, indent=1, ensure_ascii=False))
    print(f"{rid} · {minutes:g} min")
    for o in out:
        f = lambda v: "NA" if v is None else f"{v:+.2f}"
        print(f"  injetado {o['injetado_mb_h']:>3} MB/h → global {f(o['rss_slope'])} robusto {f(o['robust_slope'])}"
              f" · detectado={o['detectado_pela_regra_do_juiz']} · flags={o['flags']}")


if __name__ == "__main__":
    main()
