"""Juiz fixo do AutoResearch-Aging. O AGENTE NÃO PODE EDITAR ESTE ARQUIVO.

Papel equivalente ao prepare.py do karpathy/autoresearch: medição e avaliação
fixas. O agente edita workload.py (detecção) ou candidates/vN/ (reparo).

Comandos (todos a partir da raiz do repositório):
  python prepare.py setup --zip <project-bolt-credit-card.zip>   # humano, uma vez
  python prepare.py detect [--minutes 60] [--seed 1] [--background]
  python prepare.py freeze <run_id> <arm>                          # humano, fim da detecção
  python prepare.py repair-init                                    # cria candidates/v1..v3
  python prepare.py repair [--minutes 60] [--background]
  python prepare.py promote <vN>                                   # adota um candidato como base
  python prepare.py confirm --phase detect|repair [--minutes 60]   # 3 sementes + referência
  python prepare.py wait <run_id>                                  # bloqueia até 9 min
  python prepare.py verify                                         # confere hashes e constantes do juiz
Use --smoke (2 min) só para checar o fluxo; smoke nunca entra no ranking.
"""

import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from harness import evaluate as _eval_mod  # noqa: E402
from harness import gates  # noqa: E402
from harness import load as _load_mod  # noqa: E402
from harness.evaluate import ALPHA, MIN_EFFECT_MB_PER_H, evaluate_arm  # noqa: E402
from harness.instance import Instance, NODE_MODULES, copy_app, copy_tree_writable  # noqa: E402
from harness.load import (  # noqa: E402
    BASELINE,
    WorkloadError,
    inspect_frozen_subprocess,
    inspect_workload_subprocess,
    run_load_subprocess,
)

APP = "credit-card"
ORIGINAL = ROOT / "apps" / APP / "original"
CANDS = ROOT / "candidates"
FROZEN = ROOT / "frozen" / "workload_frozen.py"
RESULTS = ROOT / "results"
JUDGE_DIR = ROOT / ".judge"
MANIFEST = JUDGE_DIR / "manifest.json"
JUDGE_LOG = RESULTS / "judge_log.jsonl"
SLOTS = 4                       # 4 instâncias em paralelo (decisão de 20/10)
DEFAULT_MINUTES = 60            # janela da reunião: sinal em ~1 h, não 48 h
CONFIRM_SEEDS = (11, 12, 13)
MIN_KEEP_SEEDS = 2              # Correção 6: exige pelo menos 2 sementes com score >= limite para keep
FIXED_GLOBS = ["prepare.py", "harness/*.py", "harness/*.js", "oracle/*.py"]

EXPECTED_CONSTANTS = {
    "MIN_EFFECT_MB_PER_H": 10.0,
    "MAX_EXCEPTION_RATE": 0.01,
    "MAX_SERVER_ERROR_RATE": 0.01,
    "MAX_SCORED_SERVER_ERROR_RATE": 0.05,
    "MAX_STATE_ROWS": 1000,
    "MAX_THREADS": 10,
    "MIN_THINK_TIME_S": 0.01,
    "MAX_BODY_BYTES": 2048,
    "MAX_PHONE_LIST": 10,
}


# ---------------------------------------------------------------- integridade
def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _rel_or_abs(p):
    p = Path(p).resolve()
    try:
        return str(p.relative_to(ROOT.resolve()))
    except ValueError:
        return str(p)


def fixed_files():
    files = []
    for g in FIXED_GLOBS:
        files += sorted(ROOT.glob(g))
    if gates.HIDDEN.exists():
        files.append(gates.HIDDEN)
    if FROZEN.exists():
        files.append(FROZEN)
    if ORIGINAL.exists():
        files += sorted(p for p in ORIGINAL.rglob("*") if p.is_file() and "node_modules" not in p.parts)
    return files


def verify_constants():
    """Confere em memória se nenhuma constante do harness foi adulterada."""
    actual = {
        "MIN_EFFECT_MB_PER_H": _eval_mod.MIN_EFFECT_MB_PER_H,
        "MAX_EXCEPTION_RATE": _eval_mod.MAX_EXCEPTION_RATE,
        "MAX_SERVER_ERROR_RATE": _eval_mod.MAX_SERVER_ERROR_RATE,
        "MAX_SCORED_SERVER_ERROR_RATE": _eval_mod.MAX_SCORED_SERVER_ERROR_RATE,
        "MAX_STATE_ROWS": _eval_mod.MAX_STATE_ROWS,
        "MAX_THREADS": _load_mod.MAX_THREADS,
        "MIN_THINK_TIME_S": _load_mod.MIN_THINK_TIME_S,
        "MAX_BODY_BYTES": _load_mod.MAX_BODY_BYTES,
        "MAX_PHONE_LIST": _load_mod.MAX_PHONE_LIST,
    }
    bad = [k for k, v in EXPECTED_CONSTANTS.items() if actual.get(k) != v]
    if bad:
        log_judge({"event": "constantes_alteradas", "constants": bad, "flag": "H5_juiz_ou_oraculo_alterado"})
        sys.exit("ABORTADO: constantes do juiz alteradas em memória -> " + ", ".join(bad))


def write_manifest():
    JUDGE_DIR.mkdir(exist_ok=True)
    m = {_rel_or_abs(p): _sha(p) for p in fixed_files()}
    MANIFEST.write_text(json.dumps(m, indent=1))
    return m


def _resolve_manifest_key(k):
    p = Path(k)
    return p if p.is_absolute() else (ROOT / p)


def verify(quiet=False):
    verify_constants()
    if not MANIFEST.exists():
        sys.exit("manifesto ausente: rode 'python prepare.py setup' (humano)")
    m = json.loads(MANIFEST.read_text())
    now = {_rel_or_abs(p) for p in fixed_files()}
    bad = [k for k, v in m.items() if not _resolve_manifest_key(k).exists() or _sha(_resolve_manifest_key(k)) != v]
    bad += sorted(now - set(m))
    if bad:
        log_judge({"event": "juiz_alterado", "files": bad, "flag": "H5_juiz_ou_oraculo_alterado"})
        sys.exit("ABORTADO: arquivos fixos alterados -> " + ", ".join(bad))
    if not quiet:
        print("verify: ok", len(m), "arquivos fixos e constantes íntegros")


def log_judge(rec):
    RESULTS.mkdir(exist_ok=True)
    rec = dict(rec, ts=time.strftime("%Y-%m-%dT%H:%M:%S"))
    with open(JUDGE_LOG, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def git_head():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short=7", "HEAD"], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "nogit"


# ---------------------------------------------------------------- setup
def cmd_setup(a):
    if MANIFEST.exists() and not a.force:
        sys.exit("setup já feito. Use --force apenas como humano, fora da campanha.")
    with zipfile.ZipFile(a.zip) as z:
        tmp = Path(tempfile.mkdtemp())
        z.extractall(tmp)
    src = next(p.parent for p in tmp.rglob("package.json") if "node_modules" not in p.parts)
    copy_tree_writable(src, ORIGINAL, ignore=shutil.ignore_patterns("node_modules", "uptime_db", ".bolt"))
    build = Path(tempfile.mkdtemp())
    shutil.copyfile(ORIGINAL / "package.json", build / "package.json")
    if (ORIGINAL / "package-lock.json").exists():
        shutil.copyfile(ORIGINAL / "package-lock.json", build / "package-lock.json")
    print("npm install (dependências travadas do app original)...")
    subprocess.check_call(["npm", "install", "--omit=dev", "--no-audit", "--no-fund"], cwd=build)
    NODE_MODULES.parent.mkdir(exist_ok=True)
    if NODE_MODULES.exists():
        shutil.rmtree(NODE_MODULES)
    shutil.move(str(build / "node_modules"), NODE_MODULES)
    # Correção 2: restringe permissões de oracle/hidden para que outro usuário Linux não leia
    if gates.HIDDEN.exists():
        try:
            gates.HIDDEN.parent.chmod(0o700)
            gates.HIDDEN.chmod(0o600)
        except OSError:
            pass
    print("Conferindo oráculos contra o original...")
    rep = gates.functional_and_hidden(ORIGINAL, Path(tempfile.mkdtemp()))
    if any(rep):
        sys.exit(f"O ORIGINAL falha nos oráculos; revise os testes: {rep}")
    m = write_manifest()
    print(f"setup ok: {len(m)} arquivos fixos no manifesto (oracle/hidden fora do git)")


# ---------------------------------------------------------------- utilidades
def frozen_spec(require_confirmed=False):
    """Inspeciona frozen/workload_frozen.py num subprocesso isolado."""
    if not FROZEN.exists():
        sys.exit("frozen/workload_frozen.py ausente: o humano roda 'prepare.py freeze' ao fim da detecção")
    info = inspect_frozen_subprocess(FROZEN)
    info["workload_path"] = str(FROZEN)
    if require_confirmed and not (info.get("confirmed") or _has_confirmed_detect_in_log(info["name"])):
        sys.exit(
            "ABORTADO (Correção 8): a Campanha 2 (reparo) exige um vazamento confirmado na Campanha 1 "
            "('python prepare.py confirm --phase detect' com 3 sementes acima do limiar). "
            "Use --force apenas para testes manuais do fluxo."
        )
    return info


def _has_confirmed_detect_in_log(arm_name):
    if not JUDGE_LOG.exists():
        return False
    for line in JUDGE_LOG.read_text(errors="ignore").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("event") == "confirm-detect" and rec.get("aging_confirmed") and rec.get("frozen_arm") == arm_name:
            return True
    return False


def _historical_confirmed_seeds(sig_hash, arm_name, current_seed, current_score, smoke):
    """Retorna lista ordenada de sementes distintas (não-smoke) em que o candidato
    atingiu score_rss_mb_per_h >= MIN_EFFECT_MB_PER_H."""
    if smoke:
        return []
    seeds_scores = {}
    if JUDGE_LOG.exists():
        for line in JUDGE_LOG.read_text(errors="ignore").splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("event") != "detect" or rec.get("smoke"):
                continue
            s = rec.get("seed")
            for item in rec.get("summary", []):
                same_cand = (
                    (sig_hash and item.get("sig_hash") == sig_hash)
                    or item.get("arm") == arm_name
                )
                sc = item.get("score")
                if same_cand and sc is not None and sc >= MIN_EFFECT_MB_PER_H and s is not None:
                    seeds_scores[int(s)] = float(sc)
    if current_score is not None and current_score >= MIN_EFFECT_MB_PER_H:
        seeds_scores[int(current_seed)] = float(current_score)
    return sorted(seeds_scores.keys()), seeds_scores


def run_arms(arms, minutes, run_dir, smoke):
    """arms: lista de dicts {label, app_dir, spec, workload_path, seed}.
    Roda todos em paralelo, executando a carga em subprocesso isolado (Correção 1)."""
    seconds = int(minutes * 60)
    probe_ms = 2000 if smoke else 5000
    results = {}

    def one(arm):
        wd = run_dir / arm["label"]
        inst = Instance(arm["app_dir"], wd, probe_interval_ms=probe_ms, sample_s=probe_ms / 1000)
        try:
            inst.prepare()
            port = inst.start()
            inst.start_sampler()
            load_out = wd / "load_summary.json"
            load = run_load_subprocess(
                arm["workload_path"], arm["spec"]["name"], port, seconds, arm["seed"], load_out
            )
            time.sleep(probe_ms / 1000 * 1.5)  # última amostra pós-GC
            alive = inst.alive()
            pids = set(inst.pids_seen)
        except Exception as e:
            results[arm["label"]] = {"arm": arm["label"], "valid": False, "flags": [f"erro: {e}"]}
            inst.stop()
            return
        inst.stop()
        ev = evaluate_arm(arm["label"], inst.probe_rows(), load, inst.db_state(), pids, alive, seconds)
        ev.update({
            "spec_name": arm["spec"]["name"],
            "hypothesis": arm["spec"].get("hypothesis", ""),
            "sig_hash": arm["spec"].get("signature", {}).get("sig_hash"),
            "seed": arm["seed"],
            "app_dir": str(arm["app_dir"]),
        })
        (wd / "buckets.json").write_text(json.dumps(load["buckets"]))
        (wd / "evaluation.json").write_text(json.dumps(ev, indent=1, ensure_ascii=False))
        results[arm["label"]] = ev

    ths = [threading.Thread(target=one, args=(a,)) for a in arms]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    verify_constants()
    return results


def new_run_dir(kind, run_id=None):
    run_id = run_id or f"{kind}-{time.strftime('%m%d-%H%M')}-{uuid.uuid4().hex[:4]}"
    d = RESULTS / run_id
    d.mkdir(parents=True, exist_ok=True)
    return run_id, d


def background(argv, run_id, run_dir):
    argv = [a for a in argv if a != "--background"] + ["--run-id", run_id]
    with open(run_dir / "judge.log", "ab") as log:
        subprocess.Popen([sys.executable, str(ROOT / "prepare.py")] + argv, cwd=ROOT,
                         stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    (run_dir / "STATUS").write_text("running")
    print(f"run_id: {run_id}\nstatus: running (use: python prepare.py wait {run_id})")


def fmt(v, nd=3):
    return "NA" if v is None else (f"{v:.{nd}f}" if isinstance(v, float) else str(v))


# ---------------------------------------------------------------- detecção
def cmd_detect(a):
    verify(quiet=True)
    minutes = 2 if a.smoke else a.minutes
    run_id, run_dir = new_run_dir("detect" + ("-smoke" if a.smoke else ""), a.run_id)
    try:
        # Correção 1: inspeciona e valida workload.py em subprocesso isolado
        cands = inspect_workload_subprocess(ROOT / "workload.py", max_candidates=SLOTS - 1)
    except Exception as e:
        rec = {"event": "detect", "run_id": run_id, "commit": git_head(), "valid": False,
               "flag": "D3_fora_do_contrato", "error": str(e)}
        log_judge(rec)
        (run_dir / "STATUS").write_text("done")
        (run_dir / "round.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
        print("INVÁLIDO:", e)
        return
    if a.background:
        return background(sys.argv[1:], run_id, run_dir)
    saved_wl = run_dir / "workload.py"
    shutil.copyfile(ROOT / "workload.py", saved_wl)
    base_meta = {"name": BASELINE["name"], "hypothesis": BASELINE["hypothesis"],
                 "threads": BASELINE["threads"], "think_time_s": BASELINE["think_time_s"]}
    arms = [{"label": BASELINE["name"], "app_dir": ORIGINAL, "spec": base_meta,
             "workload_path": saved_wl, "seed": a.seed}]
    arms += [{"label": c["name"], "app_dir": ORIGINAL, "spec": c,
              "workload_path": saved_wl, "seed": a.seed} for c in cands]
    res = run_arms(arms, minutes, run_dir, a.smoke)
    verify(quiet=True)
    base = res[BASELINE["name"]]
    base_slope = base.get("rss_mb", {}).get("robust_slope_per_h") if base.get("valid") else None
    rows = []
    copies = {c["name"] for c in cands if c.get("same_as_baseline")}
    for label, ev in res.items():
        if label in copies:
            ev.setdefault("flags", []).append("D4_copia_da_baseline")
        rss_info = ev.get("rss_mb", {})
        full_slope = rss_info.get("sen_slope_per_h")
        robust_slope = rss_info.get("robust_slope_per_h")
        ev["rss_slope_mb_per_h"] = full_slope
        ev["robust_slope_mb_per_h"] = robust_slope
        eligible = (ev.get("valid") and ev.get("rss_upward_significant")
                    and not any(f.startswith(("D2", "D4", "E2")) for f in ev.get("flags", [])))
        score = robust_slope if (eligible and label != BASELINE["name"]) else None
        ev["score_rss_mb_per_h"] = score
        ev["ratio_vs_baseline"] = (score / base_slope) if (score is not None and base_slope and base_slope > 0) else None
        if label != BASELINE["name"]:
            c_seeds, c_map = _historical_confirmed_seeds(ev.get("sig_hash"), label, a.seed, score, a.smoke)
            ev["confirmed_seeds"] = c_seeds
            ev["keep_eligible"] = len(c_seeds) >= MIN_KEEP_SEEDS
            ev["replicated_score_mb_per_h"] = (sum(c_map.values()) / len(c_map)) if len(c_seeds) >= MIN_KEEP_SEEDS else None
        else:
            ev["confirmed_seeds"] = []
            ev["keep_eligible"] = False
            ev["replicated_score_mb_per_h"] = None
        rows.append(ev)
    rec = {"event": "detect", "run_id": run_id, "commit": git_head(), "smoke": a.smoke,
           "minutes": minutes, "seed": a.seed, "arms": rows}
    (run_dir / "round.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    # Correção 9: registra rss_slope e robust_slope mesmo quando score é None
    log_judge({k: v for k, v in rec.items() if k != "arms"} | {"summary": [
        {"arm": r["arm"], "sig_hash": r.get("sig_hash"), "valid": r.get("valid"),
         "flags": r.get("flags"), "rss_slope": r.get("rss_slope_mb_per_h"),
         "robust_slope": r.get("robust_slope_mb_per_h"), "score": r.get("score_rss_mb_per_h"),
         "keep_eligible": r.get("keep_eligible"), "confirmed_seeds": r.get("confirmed_seeds"),
         "p": r.get("rss_mb", {}).get("mk_p_upward")} for r in rows]})
    (run_dir / "STATUS").write_text("done")
    print_detect(run_id, rows, seed=a.seed)


def print_detect(run_id, rows, seed=None):
    print(f"---\nrun_id: {run_id}" + (f" seed: {seed}" if seed is not None else ""))
    for r in rows:
        rss = r.get("rss_mb", {})
        c_seeds = ",".join(map(str, r.get("confirmed_seeds") or [])) or "-"
        print(f"arm={r['arm']} valid={r.get('valid')} score_rss_mb_per_h={fmt(r.get('score_rss_mb_per_h'))} "
              f"rss_slope={fmt(rss.get('sen_slope_per_h'))} robust_slope={fmt(rss.get('robust_slope_per_h'))} "
              f"h1_slope={fmt(rss.get('sen_slope_first_half_per_h'))} h2_slope={fmt(rss.get('sen_slope_second_half_per_h'))} "
              f"mk_p={fmt(rss.get('mk_p_upward'), 5)} "
              f"heap_slope={fmt(r.get('heap_mb', {}).get('sen_slope_per_h'))} "
              f"handles_slope={fmt(r.get('handles', {}).get('sen_slope_per_h'))} "
              f"p95_slope={fmt(r.get('p95_ms', {}).get('sen_slope_per_h'))} "
              f"ttd_min={fmt(r.get('time_to_detect_min'))} ratio={fmt(r.get('ratio_vs_baseline'))} "
              f"keep_eligible={r.get('keep_eligible', False)} confirmed_seeds={c_seeds} "
              f"req={r.get('requests')} err={fmt(r.get('error_rate'), 4)} db_rows={r.get('db_rows')} "
              f"flags={','.join(r.get('flags', [])) or '-'}")


# ---------------------------------------------------------------- congelar (humano)
def cmd_freeze(a):
    src = RESULTS / a.run_id / "workload.py"
    if not src.exists():
        sys.exit("run sem workload.py salvo")
    round_file = RESULTS / a.run_id / "round.json"
    if round_file.exists() and not a.force:
        rd = json.loads(round_file.read_text())
        arm_ev = next((r for r in rd.get("arms", []) if r.get("arm") == a.arm), None)
        if not arm_ev or (arm_ev.get("score_rss_mb_per_h") or 0) < MIN_EFFECT_MB_PER_H:
            sys.exit(
                f"ABORTADO: braço {a.arm!r} em {a.run_id} não atingiu o limiar de {MIN_EFFECT_MB_PER_H} MB/h. "
                "Use --force apenas se quiser congelar manualmente para teste."
            )
    FROZEN.parent.mkdir(exist_ok=True)
    FROZEN.write_text(
        src.read_text()
        + f"\n\nFROZEN_ARM = {a.arm!r}\nFROZEN_FROM = {a.run_id!r}\nFROZEN_CONFIRMED = False\n"
    )
    write_manifest()
    print(f"carga congelada: {a.arm} de {a.run_id}; rode 'python prepare.py confirm --phase detect' antes do reparo")


# ---------------------------------------------------------------- reparo
def cmd_repair_init(a):
    if not getattr(a, "force", False):
        frozen_spec(require_confirmed=True)
    base = CANDS / "base"
    if not base.exists():
        copy_tree_writable(ORIGINAL, base)
    for v in ("v1", "v2", "v3"):
        d = CANDS / v
        copy_tree_writable(base, d)
    print("candidates/v1..v3 criados a partir de candidates/base (com permissão de escrita)")


def cmd_promote(a):
    src = CANDS / a.version
    base = CANDS / "base"
    copy_tree_writable(src, base)
    for v in ("v1", "v2", "v3"):
        copy_tree_writable(base, CANDS / v)
    print(f"{a.version} promovido a base")


def diff_lines(orig, cand):
    n = 0
    files = {p.relative_to(orig) for p in Path(orig).rglob("*") if p.is_file()}
    files |= {p.relative_to(cand) for p in Path(cand).rglob("*") if p.is_file() and "node_modules" not in p.parts}
    for f in sorted(files):
        a_ = (Path(orig) / f).read_text(errors="ignore").splitlines() if (Path(orig) / f).exists() else []
        b_ = (Path(cand) / f).read_text(errors="ignore").splitlines() if (Path(cand) / f).exists() else []
        n += sum(1 for l in difflib.unified_diff(a_, b_, lineterm="", n=0)
                 if l[:1] in "+-" and not l.startswith(("+++", "---")))
    return n


def reference_replay(spec, trace):
    key = hashlib.sha256((json.dumps(trace) + _sha(ORIGINAL / "package.json")).encode()).hexdigest()[:16]
    cache = JUDGE_DIR / f"replay_ref_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    ref = gates.replay(ORIGINAL, trace, Path(tempfile.mkdtemp()))
    cache.write_text(json.dumps(ref))
    return ref


def cmd_repair(a):
    verify(quiet=True)
    spec = frozen_spec(require_confirmed=not (a.smoke or a.force))
    minutes = 2 if a.smoke else a.minutes
    run_id, run_dir = new_run_dir("repair" + ("-smoke" if a.smoke else ""), a.run_id)
    if a.background:
        return background(sys.argv[1:], run_id, run_dir)
    versions = [v for v in ("v1", "v2", "v3") if (CANDS / v).exists()]
    trace = gates.build_trace(spec)
    ref = reference_replay(spec, trace)
    gate_reports = {}
    base_dir = CANDS / "base"
    base_diff = diff_lines(ORIGINAL, base_dir) if base_dir.exists() else 0
    for v in versions:
        gate_reports[v] = gates.run_gates(ORIGINAL, CANDS / v, ref, trace, run_dir)
        gate_reports[v]["diff_lines"] = diff_lines(ORIGINAL, CANDS / v)
        gate_reports[v]["diff_vs_base"] = diff_lines(base_dir, CANDS / v) if base_dir.exists() else gate_reports[v]["diff_lines"]
        if gate_reports[v]["diff_lines"] == 0 or gate_reports[v]["diff_vs_base"] == 0:
            gate_reports[v]["flags"].append("sem_alteracao")
            gate_reports[v]["passed"] = False
        print(f"gates {v}: passed={gate_reports[v]['passed']} flags={gate_reports[v]['flags']} "
              f"diff_lines={gate_reports[v]['diff_lines']}", flush=True)
    for v in versions:  # snapshot do que foi avaliado
        copy_tree_writable(CANDS / v, run_dir / "snapshot" / v)
    arms = [{"label": "original", "app_dir": ORIGINAL, "spec": spec,
             "workload_path": FROZEN, "seed": a.seed}]
    # Correção 8: mede também a 'base' atual na rodada quando ela difere do original
    measure_base = base_dir.exists() and base_diff > 0
    if measure_base:
        copy_tree_writable(base_dir, run_dir / "snapshot" / "base")
        arms.append({"label": "base", "app_dir": base_dir, "spec": spec,
                     "workload_path": FROZEN, "seed": a.seed})
    arms += [{"label": v, "app_dir": CANDS / v, "spec": spec,
              "workload_path": FROZEN, "seed": a.seed}
             for v in versions if gate_reports[v]["passed"]]
    res = run_arms(arms, minutes, run_dir, a.smoke)
    verify(quiet=True)
    base_gate = {"passed": True, "flags": [], "diff_lines": base_diff, "details": {}}
    base_row = score_repair(res, "base", base_gate) if measure_base else score_repair(res, "original", None)
    base_reduction = base_row.get("score_reduction") if measure_base else 0.0
    rows = [score_repair(res, "original", None, base_reduction=0.0)]
    if measure_base:
        rows.append(base_row)
    rows += [score_repair(res, v, gate_reports.get(v), base_reduction=base_reduction) for v in versions]
    rec = {"event": "repair", "run_id": run_id, "commit": git_head(), "smoke": a.smoke,
           "minutes": minutes, "frozen_arm": spec["name"], "rows": rows}
    (run_dir / "round.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    log_judge({k: v for k, v in rec.items() if k != "rows"} | {"summary": [
        {"arm": r["arm"], "score": r.get("score_reduction"), "gain_vs_base": r.get("gain_vs_base"),
         "rss_slope": (r.get("rss") or {}).get("sen_slope_per_h"),
         "robust_slope": (r.get("rss") or {}).get("robust_slope_per_h"),
         "flags": r.get("flags")} for r in rows]})
    (run_dir / "STATUS").write_text("done")
    print_repair(run_id, rows)


def score_repair(res, v, gate, base_reduction=0.0):
    o = res.get("original", {})
    if v == "original":
        return {"arm": "original", "valid": o.get("valid"), "rss": o.get("rss_mb"),
                "score_reduction": 0.0, "gain_vs_base": 0.0,
                "throughput_mean_rps": o.get("throughput_mean_rps"), "p95_ms_median": o.get("p95_ms_median"),
                "flags": o.get("flags", [])}
    row = {"arm": v, "gates_passed": gate["passed"], "flags": list(gate["flags"]),
           "diff_lines": gate["diff_lines"], "gate_details": gate["details"],
           "score_reduction": None, "gain_vs_base": None}
    ev = res.get(v)
    if not gate["passed"] or not ev:
        return row
    row["flags"] += ev.get("flags", [])
    s0 = o.get("rss_mb", {}).get("robust_slope_per_h")
    s0_full = o.get("rss_mb", {}).get("sen_slope_per_h")
    s1 = ev.get("rss_mb", {}).get("sen_slope_per_h")
    s1_rob = ev.get("rss_mb", {}).get("robust_slope_per_h")
    row.update({"rss": ev.get("rss_mb"), "heap": ev.get("heap_mb"), "handles": ev.get("handles"),
                "throughput_mean_rps": ev.get("throughput_mean_rps"), "p95_ms_median": ev.get("p95_ms_median")})
    if not ev.get("valid") or not o.get("valid"):
        return row
    thr_ok = ev["throughput_mean_rps"] >= 0.9 * o["throughput_mean_rps"]
    lat_ok = ev["p95_ms_median"] <= 1.1 * o["p95_ms_median"] + 1.0
    if not (thr_ok and lat_ok):
        row["flags"].append("H6_desempenho_degradado")
        return row
    # 5xx por SQLITE_BUSY variam entre execuções: tolerância relativa + absoluta
    if ev.get("server_error_rate", 0) > 1.5 * o.get("server_error_rate", 0) + 0.005:
        row["flags"].append("H7_mais_erros_sob_carga")
        return row
    if s0 is None or s0_full is None or s0 < MIN_EFFECT_MB_PER_H or s0_full < MIN_EFFECT_MB_PER_H:
        row["flags"].append("original_sem_tendencia_nesta_rodada")
        return row
    eff_s1 = max(s1, s1_rob) if (s1 is not None and s1_rob is not None) else s1
    reduction = 1 - (eff_s1 / s0_full)
    row["score_reduction"] = reduction
    row["gain_vs_base"] = (reduction - base_reduction) if base_reduction is not None else None
    row["fixed"] = (eff_s1 < MIN_EFFECT_MB_PER_H) and reduction >= 0.8
    return row


def print_repair(run_id, rows):
    print(f"---\nrun_id: {run_id}")
    for r in rows:
        rss = r.get("rss") or {}
        print(f"arm={r['arm']} gates={r.get('gates_passed', '-')} score_reduction={fmt(r.get('score_reduction'))} "
              f"gain_vs_base={fmt(r.get('gain_vs_base'))} fixed={r.get('fixed', '-')} "
              f"rss_slope={fmt(rss.get('sen_slope_per_h'))} robust_slope={fmt(rss.get('robust_slope_per_h'))} "
              f"mk_p={fmt(rss.get('mk_p_upward'), 5)} thr={fmt(r.get('throughput_mean_rps'), 1)} "
              f"p95={fmt(r.get('p95_ms_median'), 2)} diff_lines={r.get('diff_lines', '-')} "
              f"flags={','.join(r.get('flags', [])) or '-'}")


# ---------------------------------------------------------------- confirmação
def cmd_confirm(a):
    verify(quiet=True)
    minutes = 2 if a.smoke else a.minutes
    run_id, run_dir = new_run_dir(f"confirm-{a.phase}" + ("-smoke" if a.smoke else ""), a.run_id)
    if a.background:
        return background(sys.argv[1:], run_id, run_dir)
    spec = frozen_spec(require_confirmed=False)
    base_meta = {"name": BASELINE["name"], "hypothesis": BASELINE["hypothesis"],
                 "threads": BASELINE["threads"], "think_time_s": BASELINE["think_time_s"]}
    if a.phase == "detect":
        arms = [{"label": f"{spec['name']}_s{s}", "app_dir": ORIGINAL, "spec": spec,
                 "workload_path": FROZEN, "seed": s} for s in CONFIRM_SEEDS]
        arms.append({"label": "baseline_s11", "app_dir": ORIGINAL, "spec": base_meta,
                     "workload_path": FROZEN, "seed": 11})
    else:
        arms = [{"label": f"base_s{s}", "app_dir": CANDS / "base", "spec": spec,
                 "workload_path": FROZEN, "seed": s} for s in CONFIRM_SEEDS]
        arms.append({"label": "original_s11", "app_dir": ORIGINAL, "spec": spec,
                     "workload_path": FROZEN, "seed": 11})
    res = run_arms(arms, minutes, run_dir, a.smoke)
    verify(quiet=True)
    rows = []
    for label, ev in res.items():
        rss_info = ev.get("rss_mb", {})
        ev["rss_slope_mb_per_h"] = rss_info.get("sen_slope_per_h")
        ev["robust_slope_mb_per_h"] = rss_info.get("robust_slope_per_h")
        eligible = (ev.get("valid") and ev.get("rss_upward_significant")
                    and not any(f.startswith(("D2", "D4", "E2")) for f in ev.get("flags", [])))
        ev["score_rss_mb_per_h"] = ev["robust_slope_mb_per_h"] if (eligible and not label.startswith("baseline")) else None
        rows.append(ev)
    confirmed_arms = [r for r in rows if not r["arm"].startswith(("baseline_", "original_"))]
    aging_confirmed = (
        not a.smoke
        and len(confirmed_arms) == len(CONFIRM_SEEDS)
        and all(r.get("score_rss_mb_per_h") is not None and r["score_rss_mb_per_h"] >= MIN_EFFECT_MB_PER_H
                for r in confirmed_arms)
    )
    if a.phase == "detect" and aging_confirmed and FROZEN.exists():
        txt = FROZEN.read_text()
        if "FROZEN_CONFIRMED = False" in txt:
            FROZEN.write_text(txt.replace("FROZEN_CONFIRMED = False", "FROZEN_CONFIRMED = True"))
        else:
            FROZEN.write_text(txt + "\nFROZEN_CONFIRMED = True\n")
        write_manifest()
    rec = {"event": f"confirm-{a.phase}", "run_id": run_id, "commit": git_head(), "smoke": a.smoke,
           "minutes": minutes, "frozen_arm": spec["name"], "aging_confirmed": aging_confirmed, "arms": rows}
    (run_dir / "round.json").write_text(json.dumps(rec, indent=1, ensure_ascii=False))
    log_judge({k: v for k, v in rec.items() if k != "arms"} | {"summary": [
        {"arm": r["arm"], "rss_slope": r.get("rss_slope_mb_per_h"),
         "robust_slope": r.get("robust_slope_mb_per_h"), "score": r.get("score_rss_mb_per_h")} for r in rows]})
    (run_dir / "STATUS").write_text("done")
    print_detect(run_id, rows)
    print(f"aging_confirmed: {aging_confirmed}")


# ---------------------------------------------------------------- espera
def cmd_wait(a):
    d = RESULTS / a.run_id
    deadline = time.time() + min(a.max_seconds, 540)
    while time.time() < deadline:
        st = (d / "STATUS").read_text().strip() if (d / "STATUS").exists() else "unknown"
        if st == "done":
            rec = json.loads((d / "round.json").read_text())
            if rec.get("event") == "repair":
                print_repair(a.run_id, rec["rows"])
            elif "arms" in rec:
                print_detect(a.run_id, rec["arms"], seed=rec.get("seed"))
            else:
                print(json.dumps(rec, ensure_ascii=False))
            return
        time.sleep(15)
    print(f"status: running ({a.run_id}); chame wait novamente")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("setup"); s.add_argument("--zip", required=True); s.add_argument("--force", action="store_true")
    for name in ("detect", "repair"):
        s = sp.add_parser(name)
        s.add_argument("--minutes", type=float, default=DEFAULT_MINUTES)
        s.add_argument("--seed", type=int, default=1)
        s.add_argument("--smoke", action="store_true")
        s.add_argument("--background", action="store_true")
        s.add_argument("--force", action="store_true")
        s.add_argument("--run-id")
    s = sp.add_parser("confirm"); s.add_argument("--phase", choices=["detect", "repair"], required=True)
    s.add_argument("--minutes", type=float, default=DEFAULT_MINUTES); s.add_argument("--smoke", action="store_true")
    s.add_argument("--background", action="store_true"); s.add_argument("--run-id")
    s = sp.add_parser("freeze"); s.add_argument("run_id"); s.add_argument("arm"); s.add_argument("--force", action="store_true")
    s = sp.add_parser("repair-init"); s.add_argument("--force", action="store_true")
    s = sp.add_parser("promote"); s.add_argument("version", choices=["v1", "v2", "v3"])
    s = sp.add_parser("wait"); s.add_argument("run_id"); s.add_argument("--max-seconds", type=int, default=540)
    sp.add_parser("verify")
    a = ap.parse_args()
    {"setup": cmd_setup, "detect": cmd_detect, "repair": cmd_repair, "confirm": cmd_confirm,
     "freeze": cmd_freeze, "repair-init": cmd_repair_init, "promote": cmd_promote,
     "wait": cmd_wait, "verify": lambda _: verify()}[a.cmd](a)


if __name__ == "__main__":
    main()
