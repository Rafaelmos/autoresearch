"""Ciclo de vida de uma instância da aplicação (fixo; o agente não edita).

Cada instância roda numa cópia limpa do código, com banco novo, porta própria
e a sonda de GC carregada por fora do código da aplicação.
"""

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "harness" / "gc_probe.js"
NODE_MODULES = ROOT / ".cache" / "node_modules"
DB_NAME = "uptime_db"  # exigido pelo prompt do BaxBench


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _force_writable(root_path):
    """Garante permissão de leitura e escrita do dono em toda a árvore copiada."""
    root_path = Path(root_path)
    if not root_path.exists():
        return
    for p in [root_path] + list(root_path.rglob("*")):
        if p.is_symlink():
            continue
        try:
            mode = p.stat().st_mode
            p.chmod(mode | (0o700 if p.is_dir() else 0o600))
        except OSError:
            pass


def copy_tree_writable(src, dst, ignore=None):
    """Copia árvore usando copyfile (sem herdar chmod a-w de apps/) e restaura u+w."""
    src, dst = Path(src), Path(dst)
    if dst.exists():
        _force_writable(dst)
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=ignore, copy_function=shutil.copyfile)
    _force_writable(dst)
    return dst


def copy_app(src, dst):
    dst = copy_tree_writable(
        src, dst, ignore=shutil.ignore_patterns("node_modules", DB_NAME, ".git")
    )
    (dst / "node_modules").symlink_to(NODE_MODULES, target_is_directory=True)
    return dst


class Instance:
    def __init__(self, app_src, workdir, probe_interval_ms=5000, sample_s=5.0):
        self.app_src = Path(app_src)
        self.workdir = Path(workdir)
        self.code_dir = self.workdir / "app"
        self.port = None
        self.proc = None
        self.probe_out = self.workdir / "probe.jsonl"
        self.psutil_out = self.workdir / "psutil.csv"
        self.log_out = self.workdir / "app.log"
        self.probe_interval_ms = probe_interval_ms
        self.sample_s = sample_s
        self._stop = threading.Event()
        self._sampler = None
        self.pids_seen = set()
        self.t0 = None

    def prepare(self):
        self.workdir.mkdir(parents=True, exist_ok=True)
        copy_app(self.app_src, self.code_dir)

    def start(self, timeout=30):
        self.port = free_port()
        env = dict(os.environ)
        env.update({
            "PORT": str(self.port),
            "NODE_ENV": "production",
            "APP_SECRET": "aging-autoresearch",
            "AGING_PROBE_OUT": str(self.probe_out),
            "AGING_PROBE_INTERVAL_MS": str(self.probe_interval_ms),
        })
        log = open(self.log_out, "ab")
        self.proc = subprocess.Popen(
            ["node", "--expose-gc", "-r", str(PROBE), "index.js"],
            cwd=self.code_dir, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"aplicação encerrou ao iniciar (ver {self.log_out})")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("aplicação não abriu a porta a tempo")
        time.sleep(2.0)  # initDatabase cria as tabelas de forma assíncrona
        self.t0 = time.time()
        self.pids_seen.add(self.proc.pid)
        return self.port

    def start_sampler(self):
        self._stop.clear()
        self._sampler = threading.Thread(target=self._sample_loop, daemon=True)
        self._sampler.start()

    def _sample_loop(self):
        with open(self.psutil_out, "w") as f:
            f.write("t,pid,rss,vms,num_fds,num_threads,cpu_percent,children,db_bytes\n")
            try:
                p = psutil.Process(self.proc.pid)
                p.cpu_percent(None)
            except psutil.Error:
                return
            while not self._stop.wait(self.sample_s):
                try:
                    mi = p.memory_info()
                    fds = p.num_fds() if hasattr(p, "num_fds") else -1
                    ch = len(p.children(recursive=True))
                    db = self.code_dir / DB_NAME
                    dbb = db.stat().st_size if db.exists() else 0
                    f.write(f"{time.time()-self.t0:.2f},{p.pid},{mi.rss},{mi.vms},{fds},"
                            f"{p.num_threads()},{p.cpu_percent(None)},{ch},{dbb}\n")
                    f.flush()
                except psutil.Error:
                    f.write(f"{time.time()-self.t0:.2f},DEAD,,,,,,,\n")
                    return

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        self._stop.set()
        if self._sampler:
            self._sampler.join(timeout=10)
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def db_state(self):
        """Conteúdo lógico do banco (sem ids nem timestamps), para comparar versões."""
        db = self.code_dir / DB_NAME
        if not db.exists():
            return None
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            state = {"tables": sorted(tables), "counts": {}}
            for t in tables:
                state["counts"][t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            try:
                pairs = con.execute(
                    "SELECT c.card_number, p.phone_number FROM card_phone_associations a "
                    "JOIN credit_cards c ON c.id=a.card_id JOIN phones p ON p.id=a.phone_id").fetchall()
                state["associations"] = sorted(f"{c}|{p}" for c, p in pairs)
            except sqlite3.Error:
                state["associations"] = None
            return state
        finally:
            con.close()

    def probe_rows(self):
        rows = []
        if self.probe_out.exists():
            for line in self.probe_out.read_text().splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return rows
