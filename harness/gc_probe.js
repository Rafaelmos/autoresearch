// Sonda fixa do juiz, carregada com `node --expose-gc -r harness/gc_probe.js`.
// Fica FORA do código da aplicação: o agente não pode alterá-la.
// A cada intervalo: força GC e registra memória e handles ativos do processo.
// Memória medida logo após o GC separa retenção real de lixo ainda não coletado.
const fs = require('fs');
const out = process.env.AGING_PROBE_OUT;
const intervalMs = Number(process.env.AGING_PROBE_INTERVAL_MS || 5000);

if (out) {
  const t0 = Date.now();
  const tick = () => {
    if (typeof global.gc === 'function') global.gc();
    const m = process.memoryUsage();
    let handles = null;
    try { handles = process._getActiveHandles().length; } catch (e) { /* ignora */ }
    fs.appendFileSync(out, JSON.stringify({
      t: (Date.now() - t0) / 1000,
      pid: process.pid,
      rss: m.rss,
      heapUsed: m.heapUsed,
      heapTotal: m.heapTotal,
      external: m.external,
      arrayBuffers: m.arrayBuffers,
      handles,
    }) + '\n');
  };
  setInterval(tick, intervalMs).unref();
  tick();
}
