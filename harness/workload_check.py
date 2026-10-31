"""Carregamento seguro de workload.py (fixo).

workload.py é escrito pelo agente e roda DENTRO do processo do juiz. Sem esta
trava, um `import harness.evaluate` no topo do arquivo bastaria para trocar a
estatística em memória (monkeypatch) sem tocar em nenhum arquivo do manifesto.

Três camadas:
1. AST com lista branca: sem import, sem class, sem global/nonlocal, sem while,
   sem acesso a atributos com "_" (fecha __class__/__globals__/__subclasses__)
   e sem nomes perigosos (eval, exec, open, getattr, format...).
2. exec com __builtins__ restrito: mesmo que algo passe pela AST, não há
   __import__ nem open no escopo.
3. Determinismo e pureza: request(rng, i) chamado duas vezes com o mesmo rng
   semeado deve dar a mesma sequência, e as constantes do módulo não podem mudar
   durante as chamadas (estado escondido = carga que muda sem o juiz ver).
"""

import ast
import copy
import random

from .load import WorkloadError

SAFE_BUILTINS = {
    "len": len, "range": range, "str": str, "int": int, "float": float, "bool": bool,
    "min": min, "max": max, "abs": abs, "sum": sum, "round": round,
    "list": list, "dict": dict, "tuple": tuple, "set": set, "frozenset": frozenset,
    "enumerate": enumerate, "zip": zip, "sorted": sorted, "reversed": reversed,
    "any": any, "all": all, "isinstance": isinstance, "map": map, "filter": filter,
    "chr": chr, "ord": ord, "divmod": divmod, "True": True, "False": False, "None": None,
    "ValueError": ValueError,
}

FORBIDDEN_NAMES = {
    "__import__", "eval", "exec", "compile", "open", "globals", "locals", "vars", "dir",
    "getattr", "setattr", "delattr", "hasattr", "type", "object", "super", "format",
    "breakpoint", "input", "help", "memoryview", "bytearray", "__builtins__", "id",
}
FORBIDDEN_ATTRS = {"format", "format_map", "seed", "setstate", "getstate", "mro"}

FORBIDDEN_NODES = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.Global, ast.Nonlocal,
                   ast.While, ast.AsyncFunctionDef, ast.Await, ast.Yield, ast.YieldFrom,
                   ast.With, ast.AsyncWith, ast.AsyncFor, ast.Delete)

DETERMINISM_SEEDS = (3, 4)
DETERMINISM_N = 300


def check_ast(src):
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise WorkloadError(f"workload.py não compila: {e}") from None
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_NODES):
            raise WorkloadError(f"construção proibida em workload.py: {type(node).__name__} "
                                f"(linha {getattr(node, 'lineno', '?')})")
        if isinstance(node, ast.Name) and (node.id in FORBIDDEN_NAMES or node.id.startswith("__")):
            raise WorkloadError(f"nome proibido em workload.py: {node.id} (linha {node.lineno})")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in FORBIDDEN_ATTRS):
            raise WorkloadError(f"atributo proibido em workload.py: .{node.attr} (linha {node.lineno})")
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            raise WorkloadError(f"decorador proibido em workload.py (linha {node.lineno})")
    for node in tree.body:
        ok = (isinstance(node, (ast.FunctionDef, ast.Assign, ast.AnnAssign))
              or (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)))
        if not ok:
            raise WorkloadError(f"só funções, constantes e docstring no topo de workload.py "
                                f"(linha {node.lineno}: {type(node).__name__})")
    return tree


def _constants(ns):
    return {k: copy.deepcopy(v) for k, v in ns.items()
            if k != "__builtins__" and not callable(v) and k != "CANDIDATES"}


def check_determinism(spec, ns):
    before = _constants(ns)
    for seed in DETERMINISM_SEEDS:
        a, b = random.Random(seed), random.Random(seed)
        seq_a = [spec["request"](a, i) for i in range(DETERMINISM_N)]
        seq_b = [spec["request"](b, i) for i in range(DETERMINISM_N)]
        if seq_a != seq_b:
            raise WorkloadError(f"{spec['name']}: request(rng, i) não é determinística "
                                "(mesmo rng e mesmo i devem dar a mesma requisição)")
    if _constants(ns) != before:
        raise WorkloadError(f"{spec['name']}: request(rng, i) altera constantes do módulo (estado escondido)")


def load_workload(path):
    """Carrega workload.py (ou a carga congelada) num namespace isolado. Retorna o namespace."""
    src = path.read_text()
    check_ast(src)
    ns = {"__builtins__": dict(SAFE_BUILTINS), "__name__": "workload"}
    try:
        exec(compile(src, str(path), "exec"), ns)
    except WorkloadError:
        raise
    except Exception as e:
        raise WorkloadError(f"erro ao executar workload.py: {type(e).__name__}: {e}") from None
    return ns
