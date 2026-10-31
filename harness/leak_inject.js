// Vazamento sintético do juiz (controle positivo), carregado com `node -r harness/leak_inject.js`.
// Fica FORA do código da aplicação. Retém AGING_LEAK_MB_PER_H MiB por hora, em parcelas
// a cada AGING_LEAK_INTERVAL_MS, independente da carga. Serve para medir se o juiz
// detecta um vazamento de taxa conhecida em 60 min (sensibilidade da métrica).
const rate = Number(process.env.AGING_LEAK_MB_PER_H || 0);
const intervalMs = Number(process.env.AGING_LEAK_INTERVAL_MS || 5000);

if (rate > 0) {
  const bytes = Math.max(1, Math.round((rate * 1024 * 1024 * intervalMs) / 3600000));
  const retained = [];
  // Buffer.alloc fora do pool; fill com valor não nulo toca as páginas, então entram no RSS.
  const tick = () => { retained.push(Buffer.alloc(bytes).fill(0xa5)); };
  setInterval(tick, intervalMs).unref();
  global.__agingLeakRetained = retained;  // evita que o GC forçado da sonda colete
}
