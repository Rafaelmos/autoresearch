"""Gerador de carga fixo (fechado, estilo JMeter) e validação do contrato da carga.

O agente descreve a carga em workload.py; este módulo executa e impõe limites.
Os limites existem para impedir reward hacking na detecção: o agente não pode
"achar aging" só saturando a máquina, mandando payloads gigantes ou saindo da API.
"""

import http.client
import json
import random
import threading
import time
from collections import defaultdict

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
