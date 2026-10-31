"""Avaliação fixa de um braço (uma instância sob uma carga)."""

from .stats import trend, percentile

MB = 1024 * 1024
ALPHA = 0.01                 # mantido apenas como referência descritiva (MK tem autocorrelação em série temporal)
MAX_EXCEPTION_RATE = 0.01    # timeouts/conexões recusadas: sinal de saturação, não de aging
MAX_SERVER_ERROR_RATE = 0.01 # 5xx da aplicação acima disso: marcado para revisão humana (E1)
MAX_SCORED_SERVER_ERROR_RATE = 0.05  # acima disso o braço não pontua (E2): "achar aging" quebrando a app
MAX_STATE_ROWS = 1000        # acima disso o crescimento pode ser estado legítimo (dados novos)
MIN_EFFECT_MB_PER_H = 10.0   # Recalibrado acima do percentil 95 / máximo dos braços nulos de det-out20 e AA
                             # (que variaram de -8,5 a +7,8 MB/h). Exige também inclinação robusta a degraus
                             # (min entre 1ª e 2ª metade >= MIN_EFFECT_MB_PER_H).
CHECKPOINT_MIN = 5           # para calcular o tempo até a detecção


def warmup_seconds(total_s):
    return min(300.0, 0.1 * total_s)


def _series(probe, key, warm):
    pts = [(r["t"], r[key]) for r in probe if r.get(key) is not None and r["t"] >= warm]
    return [t / 3600.0 for t, _ in pts], [v for _, v in pts]


def time_to_detect(probe, warm, key="rss"):
    """Primeiro checkpoint (min) a partir do qual o tamanho do efeito (global e robusto)
    supera MIN_EFFECT_MB_PER_H e assim permanece até o fim.

    Não usa p-valor do Mann-Kendall como gatilho, pois a autocorrelação da série
    temporal produz p~0 mesmo em braços sem crescimento real.
    """
    if not probe:
        return None
    end = probe[-1]["t"]
    first = None
    t = warm + CHECKPOINT_MIN * 60
    while t <= end + 1e-6:
        sub = [r for r in probe if warm <= r["t"] <= t]
        x = [r["t"] / 3600 for r in sub]
        y = [r[key] / MB for r in sub]
        tr = trend(x, y)
        sig = (tr["sen_slope_per_h"] >= MIN_EFFECT_MB_PER_H
               and tr["robust_slope_per_h"] >= MIN_EFFECT_MB_PER_H)
        if sig and first is None:
            first = t / 60.0
        elif not sig:
            first = None
        t += CHECKPOINT_MIN * 60
    return first


def evaluate_arm(name, probe, load, db_state, pids_seen, alive_at_end, total_s):
    warm = warmup_seconds(total_s)
    flags = []
    out = {"arm": name, "warmup_s": warm, "requests": load["requests"],
           "error_rate": load["error_rate"], "server_error_rate": load["server_error_rate"],
           "exception_rate": load["exception_rate"], "client_error_rate": load["client_error_rate"],
           "ops": load["ops"]}

    probe_pids = {r.get("pid") for r in probe}
    if load.get("violation"):
        flags.append("D3_fora_do_contrato")
    if load["exception_rate"] > MAX_EXCEPTION_RATE:
        flags.append("D1_saturacao")
    if load["server_error_rate"] > MAX_SERVER_ERROR_RATE:
        flags.append("E1_erros_5xx_da_app")
    if load["server_error_rate"] > MAX_SCORED_SERVER_ERROR_RATE:
        flags.append("E2_erro_dominante_revisao_humana")
    if not alive_at_end or len(probe_pids | set(pids_seen)) > 1:
        flags.append("H4_processo_reiniciado_ou_morto")
    if len(probe) < 10:
        flags.append("sem_amostras_suficientes")

    for key, label in (("rss", "rss_mb"), ("heapUsed", "heap_mb"), ("external", "external_mb")):
        x, y = _series(probe, key, warm)
        tr = trend(x, [v / MB for v in y])
        out[label] = tr
        if y:
            out[label]["first"] = y[0] / MB
            out[label]["last"] = y[-1] / MB
    x, y = _series(probe, "handles", warm)
    out["handles"] = trend(x, y)

    b = [r for r in load["buckets"] if r["t"] >= warm]
    bx = [r["t"] / 3600 for r in b]
    out["p95_ms"] = trend(bx, [r["p95_ms"] for r in b])
    out["throughput"] = trend(bx, [r["throughput_rps"] for r in b])
    out["throughput_mean_rps"] = (sum(r["throughput_rps"] for r in b) / len(b)) if b else 0.0
    out["p95_ms_median"] = percentile([r["p95_ms"] for r in b], 50)

    rows = sum((db_state or {}).get("counts", {}).values()) if db_state else 0
    out["db_rows"] = rows
    out["db_state_counts"] = (db_state or {}).get("counts")
    if rows > MAX_STATE_ROWS:
        flags.append("D2_crescimento_de_estado_legitimo")

    out["time_to_detect_min"] = time_to_detect(probe, warm)
    # Decisão pelo tamanho do efeito (global e robusto a degraus >= MIN_EFFECT_MB_PER_H).
    # O p-valor do Mann-Kendall fica registrado em rss_mb["mk_p_upward"] apenas como informação.
    out["rss_upward_significant"] = (
        out["rss_mb"]["sen_slope_per_h"] >= MIN_EFFECT_MB_PER_H
        and out["rss_mb"]["robust_slope_per_h"] >= MIN_EFFECT_MB_PER_H
    )
    out["flags"] = flags
    out["valid"] = not any(f.startswith(("D1", "D3", "H4", "sem_")) for f in flags)
    return out
