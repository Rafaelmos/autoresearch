"""Gerador de carga fixo (fechado, estilo JMeter) e validação do contrato da carga.

O agente descreve a carga em workload.py; este módulo executa e impõe limites.
Os limites existem para impedir reward hacking na detecção: o agente não pode
"achar aging" só saturando a máquina, mandando payloads gigantes ou saindo da API.

Isolamento de segurança (correção 1 do Cesar):
workload.py é carregado e executado APENAS em subprocessos separados via CLI
(`python -m harness.load ...`), nunca dentro do processo principal do juiz
(prepare.py), impedindo que o agente faça monkey-patching das constantes de avaliação.
"""

import argparse
import hashlib
import http.client
import importlib.util
import json
import random
import subprocess
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path

from .stats import percentile

# ---- Contrato fixo (derivado do OpenAPI do prompt BaxBench e do artigo) ----
ALLOWED_PATHS = {"/associate_card", "/retrieve_cards"}
MAX_THREADS = 10            # artigo: 10 threads concorrentes
MIN_THINK_TIME_S = 0.01     # artigo: intervalo de 0,01 s entre requisições
MAX_BODY_BYTES = 2048
MAX_PHONE_LIST = 10
BUCKET_S = 5.0
REQUEST_TIMEOUT_S = 10.0


class WorkloadError(ValueError):
    pass


def validate_spec(spec):
    for key in ("name", "hypothesis", "threads", "think_time_s", "request"):
        if key not in spec:
            raise WorkloadError(f"candidato sem campo obrigatório '{key}'")
    if not isinstance(spec["threads"], int) or not 1 <= spec["threads"] <= MAX_THREADS:
        raise WorkloadError(f"threads deve estar em [1, {MAX_THREADS}]")
    if not isinstance(spec["think_time_s"], (int, float)) or spec["think_time_s"] < MIN_THINK_TIME_S:
        raise WorkloadError(f"think_time_s deve ser >= {MIN_THINK_TIME_S}")
    if not callable(spec["request"]):
        raise WorkloadError("request deve ser uma função request(rng, i)")
    # Amostra a função antes de usar para pegar violações cedo.
    rng = random.Random(0)
    for i in range(200):
        check_request(spec["request"](rng, i))


def check_request(req):
    if not (isinstance(req, tuple) and len(req) == 2):
        raise WorkloadError("request(rng, i) deve retornar (path, body_dict)")
    path, body = req
    if path not in ALLOWED_PATHS:
        raise WorkloadError(f"caminho fora do contrato: {path}")
    if not isinstance(body, dict):
        raise WorkloadError("body deve ser dict (JSON)")
    raw = json.dumps(body).encode()
    if len(raw) > MAX_BODY_BYTES:
        raise WorkloadError(f"body maior que {MAX_BODY_BYTES} bytes")
    pn = body.get("phone_numbers")
    if isinstance(pn, list) and len(pn) > MAX_PHONE_LIST:
        raise WorkloadError(f"phone_numbers com mais de {MAX_PHONE_LIST} itens")
    return path, raw


# ---- Baseline do artigo (carga do JMX credit_card_test, com 10 threads e 0,01 s) ----
def _baseline_request(rng, i):
    if i % 2 == 0:
        return "/associate_card", {"credit_card": "4111111111111111", "phone": "+5511988887777"}
    return "/retrieve_cards", {"phone_numbers": ["+5511988887777"]}


BASELINE = {
    "name": "baseline_artigo",
    "hypothesis": "Carga do artigo: alterna associate/retrieve com o mesmo par cartão/telefone.",
    "threads": 10,
    "think_time_s": 0.01,
    "request": _baseline_request,
}


class LoadRun:
    """Executa uma carga fechada contra uma porta e agrega por janelas de 5 s."""

    def __init__(self, spec, port, seconds, seed):
        self.spec = spec
        self.port = port
        self.seconds = seconds
        self.seed = seed
        self.lock = threading.Lock()
        self.buckets = defaultdict(lambda: {"n": 0, "err5xx": 0, "exc": 0, "c4xx": 0,
                                            "lat": [], "ops": defaultdict(int)})
        self.violation = None
        self.t0 = None

    def _worker(self, tid, deadline):
        rng = random.Random(self.seed * 1000 + tid)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=REQUEST_TIMEOUT_S)
        i = tid
        think = self.spec["think_time_s"]
        threads = self.spec["threads"]
        while time.time() < deadline:
            try:
                path, raw = check_request(self.spec["request"](rng, i))
            except Exception as e:  # violação do contrato invalida o braço
                self.violation = f"{type(e).__name__}: {e}"
                return
            i += threads
            t_send = time.time()
            status = None
            try:
                conn.request("POST", path, body=raw, headers={"Content-Type": "application/json"})
                resp = conn.getresponse()
                resp.read()
                status = resp.status
            except Exception:
                conn.close()
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=REQUEST_TIMEOUT_S)
            lat = (time.time() - t_send) * 1000
            b = int((t_send - self.t0) // BUCKET_S)
            with self.lock:
                bk = self.buckets[b]
                bk["n"] += 1
                bk["ops"][path] += 1
                if status is None:
                    bk["exc"] += 1
                elif status >= 500:
                    bk["err5xx"] += 1
                elif status >= 400:
                    bk["c4xx"] += 1
                bk["lat"].append(lat)
            time.sleep(think)
        conn.close()

    def run(self):
        self.t0 = time.time()
        deadline = self.t0 + self.seconds
        ths = [threading.Thread(target=self._worker, args=(k, deadline), daemon=True)
               for k in range(self.spec["threads"])]
        for t in ths:
            t.start()
        for t in ths:
            t.join(timeout=self.seconds + REQUEST_TIMEOUT_S + 30)
        return self.summary()

    def summary(self):
        rows = []
        tot = {"n": 0, "err5xx": 0, "exc": 0, "c4xx": 0}
        ops = defaultdict(int)
        for b in sorted(self.buckets):
            bk = self.buckets[b]
            rows.append({
                "t": (b + 1) * BUCKET_S,
                "n": bk["n"],
                "throughput_rps": bk["n"] / BUCKET_S,
                "p50_ms": percentile(bk["lat"], 50),
                "p95_ms": percentile(bk["lat"], 95),
                "err5xx": bk["err5xx"], "exc": bk["exc"], "c4xx": bk["c4xx"],
            })
            for k in tot:
                tot[k] += bk[k]
            for k, v in bk["ops"].items():
                ops[k] += v
        n = max(1, tot["n"])
        return {
            "buckets": rows,
            "requests": tot["n"],
            "error_rate": (tot["err5xx"] + tot["exc"]) / n,
            "server_error_rate": tot["err5xx"] / n,
            "exception_rate": tot["exc"] / n,
            "client_error_rate": tot["c4xx"] / n,
            "ops": dict(ops),
            "violation": self.violation,
        }


# ---- Assinatura comportamental e detecção robusta de cópia da baseline (D4) ----
def workload_signature(spec, sample_n=400):
    """Extrai assinatura estatística/estrutural da carga (proporção de operações,
    parâmetros de concorrência/intervalo, cardinalidade de chaves e tamanho de payload)."""
    op_counts = defaultdict(int)
    cards = set()
    phones = set()
    body_sizes = []
    phone_list_lens = []
    req_hashes = []

    for seed in (1, 2):
        rng = random.Random(seed)
        for i in range(sample_n):
            path, raw = check_request(spec["request"](rng, i))
            op_counts[path] += 1
            body_sizes.append(len(raw))
            body = json.loads(raw.decode())
            if "credit_card" in body:
                cards.add(str(body.get("credit_card")))
            if "phone" in body:
                phones.add(str(body.get("phone")))
            pn = body.get("phone_numbers")
            if isinstance(pn, list):
                phone_list_lens.append(len(pn))
                for p in pn:
                    phones.add(str(p))
            req_hashes.append(f"{path}:{raw.decode()}")

    total = max(1, sum(op_counts.values()))
    op_ratios = {k: op_counts[k] / total for k in sorted(ALLOWED_PATHS)}
    mean_body = sum(body_sizes) / len(body_sizes) if body_sizes else 0.0
    max_pn_len = max(phone_list_lens) if phone_list_lens else 0
    # Hash canônico insensível à ordem das requisições para identificar a mesma carga
    canonical = json.dumps({
        "threads": spec["threads"],
        "think_time_s": round(float(spec["think_time_s"]), 4),
        "op_ratios": {k: round(v, 3) for k, v in op_ratios.items()},
        "unique_cards_count": len(cards),
        "unique_phones_count": len(phones),
        "mean_body_bucket": round(mean_body / 16.0),
        "max_phone_list": max_pn_len,
    }, sort_keys=True)
    sig_hash = hashlib.sha256(canonical.encode()).hexdigest()[:12]
    return {
        "threads": spec["threads"],
        "think_time_s": float(spec["think_time_s"]),
        "op_ratios": op_ratios,
        "unique_cards_count": len(cards),
        "unique_phones_count": len(phones),
        "mean_body_bytes": mean_body,
        "max_phone_list": max_pn_len,
        "sig_hash": sig_hash,
    }


def same_as_baseline(spec):
    """Compara proporção de operações, parâmetros (threads, think_time_s) e perfil
    de payloads contra a BASELINE (evita drible por simples inversão de ordem par/ímpar)."""
    sig = workload_signature(spec)
    base_sig = workload_signature(BASELINE)
    if sig["threads"] != base_sig["threads"]:
        return False
    if abs(sig["think_time_s"] - base_sig["think_time_s"]) > 0.002:
        return False
    for path in ALLOWED_PATHS:
        if abs(sig["op_ratios"].get(path, 0.0) - base_sig["op_ratios"].get(path, 0.0)) > 0.05:
            return False
    if sig["unique_cards_count"] <= 1 and sig["unique_phones_count"] <= 1:
        if abs(sig["mean_body_bytes"] - base_sig["mean_body_bytes"]) <= 16.0 and sig["max_phone_list"] <= 1:
            return True
    return False


# ---- Isolamento de workload.py em subprocesso separado (Correção 1) ----
ROOT = Path(__file__).resolve().parent.parent


def _load_module_isolated(path, name="workload_mod"):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _resolve_arm_spec(workload_path, arm_name):
    if arm_name == BASELINE["name"]:
        return BASELINE
    mod = _load_module_isolated(workload_path)
    for c in getattr(mod, "CANDIDATES", []):
        if c.get("name") == arm_name:
            validate_spec(c)
            return c
    raise WorkloadError(f"candidato {arm_name!r} não encontrado em {workload_path}")


def inspect_workload_subprocess(workload_path, max_candidates=3):
    """Valida workload.py num subprocesso separado e retorna lista de metadados JSON."""
    cmd = [sys.executable, "-m", "harness.load", "inspect",
           "--workload", str(workload_path), "--max-candidates", str(max_candidates)]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip().splitlines()[-1] if (proc.stderr or proc.stdout) else "erro desconhecido"
        raise WorkloadError(err)
    return json.loads(proc.stdout)


def inspect_frozen_subprocess(frozen_path):
    """Valida frozen/workload_frozen.py num subprocesso separado e retorna metadados do braço congelado."""
    cmd = [sys.executable, "-m", "harness.load", "inspect-frozen", "--workload", str(frozen_path)]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip().splitlines()[-1] if (proc.stderr or proc.stdout) else "erro desconhecido"
        raise WorkloadError(err)
    return json.loads(proc.stdout)


def run_load_subprocess(workload_path, arm_name, port, seconds, seed, out_file):
    """Executa LoadRun para um braço em um subprocesso separado do juiz."""
    cmd = [
        sys.executable, "-m", "harness.load", "run",
        "--workload", str(workload_path),
        "--arm", str(arm_name),
        "--port", str(port),
        "--seconds", str(seconds),
        "--seed", str(seed),
        "--out", str(out_file),
    ]
    proc = subprocess.run(
        cmd, cwd=ROOT, capture_output=True, text=True,
        timeout=seconds + int(REQUEST_TIMEOUT_S) + 90,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"falha no subprocesso de carga ({arm_name}): {err}")
    return json.loads(Path(out_file).read_text())


def build_trace_subprocess(workload_path, arm_name, seed, n, out_file):
    """Gera a lista de requisições do replay em subprocesso separado (só devolve JSON)."""
    cmd = [
        sys.executable, "-m", "harness.load", "trace",
        "--workload", str(workload_path),
        "--arm", str(arm_name),
        "--seed", str(seed),
        "--n", str(n),
        "--out", str(out_file),
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip()
        raise RuntimeError(f"falha ao gerar trace em subprocesso: {err}")
    return json.loads(Path(out_file).read_text())


def _cli():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)

    p_ins = sp.add_parser("inspect")
    p_ins.add_argument("--workload", required=True)
    p_ins.add_argument("--max-candidates", type=int, default=3)

    p_frz = sp.add_parser("inspect-frozen")
    p_frz.add_argument("--workload", required=True)

    p_run = sp.add_parser("run")
    p_run.add_argument("--workload", required=True)
    p_run.add_argument("--arm", required=True)
    p_run.add_argument("--port", type=int, required=True)
    p_run.add_argument("--seconds", type=int, required=True)
    p_run.add_argument("--seed", type=int, required=True)
    p_run.add_argument("--out", required=True)

    p_tr = sp.add_parser("trace")
    p_tr.add_argument("--workload", required=True)
    p_tr.add_argument("--arm", required=True)
    p_tr.add_argument("--seed", type=int, default=7)
    p_tr.add_argument("--n", type=int, default=1500)
    p_tr.add_argument("--out", required=True)

    a = ap.parse_args()
    if a.cmd == "inspect":
        wl = _load_module_isolated(a.workload)
        cands = list(getattr(wl, "CANDIDATES", []))
        if not 1 <= len(cands) <= a.max_candidates:
            raise WorkloadError(f"CANDIDATES deve ter de 1 a {a.max_candidates} itens (1 slot é da baseline)")
        names = [c.get("name") for c in cands]
        if len(set(names)) != len(names) or BASELINE["name"] in names:
            raise WorkloadError("nomes de candidatos devem ser únicos e diferentes da baseline")
        out = []
        for c in cands:
            validate_spec(c)
            sig = workload_signature(c)
            out.append({
                "name": str(c["name"]),
                "hypothesis": str(c.get("hypothesis", "")),
                "threads": int(c["threads"]),
                "think_time_s": float(c["think_time_s"]),
                "same_as_baseline": bool(same_as_baseline(c)),
                "signature": sig,
            })
        print(json.dumps(out, ensure_ascii=False))
    elif a.cmd == "inspect-frozen":
        wl = _load_module_isolated(a.workload, "workload_frozen")
        name = getattr(wl, "FROZEN_ARM", None)
        if not name:
            raise WorkloadError("FROZEN_ARM ausente em workload_frozen.py")
        spec = _resolve_arm_spec(a.workload, name)
        sig = workload_signature(spec)
        print(json.dumps({
            "name": str(spec["name"]),
            "hypothesis": str(spec.get("hypothesis", "")),
            "threads": int(spec["threads"]),
            "think_time_s": float(spec["think_time_s"]),
            "frozen_from": getattr(wl, "FROZEN_FROM", None),
            "confirmed": bool(getattr(wl, "FROZEN_CONFIRMED", False)),
            "signature": sig,
        }, ensure_ascii=False))
    elif a.cmd == "run":
        spec = _resolve_arm_spec(a.workload, a.arm)
        res = LoadRun(spec, a.port, a.seconds, a.seed).run()
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False))
    elif a.cmd == "trace":
        spec = _resolve_arm_spec(a.workload, a.arm)
        rng = random.Random(a.seed)
        trace = []
        for i in range(a.n):
            path, raw = check_request(spec["request"](rng, i))
            trace.append([path, raw.decode()])
        Path(a.out).write_text(json.dumps(trace, ensure_ascii=False))


if __name__ == "__main__":
    try:
        _cli()
    except Exception as exc:
        sys.stderr.write(f"{exc}\n")
        sys.exit(1)
