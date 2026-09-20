#!/usr/bin/env python3
"""mutation_check.py — Chequeo de mutaciones (fuerza de la suite) (REQ-015).

# REQ-015

Mutacion minima en stdlib: genera mutantes de un modulo (comparadores, booleanos
y operadores logicos), ejecuta una seleccion de tests sobre cada mutante y
reporta cuantos mueren. Un mutante que sobrevive indica un test debil o una
mutacion equivalente (P1.1).

Por defecto trabaja en una **copia temporal** del repo (no toca el original).
Es una heuristica: complementa, no reemplaza, herramientas maduras como
`mutmut` o `cosmic-ray`.

Uso:
    python3 scripts/mutation_check.py
    python3 scripts/mutation_check.py --batch [--json] [--strict] [--umbral 0.8]
    python3 scripts/mutation_check.py --module scripts/auto_audit.py \\
        --test test_ecosistema.TestAutoAudit --max-mutantes 20 [--json] [--strict]
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODULE = "scripts/adr_validator.py"
DEFAULT_TEST = "test_ecosistema.TestADRValidator"
DEFAULT_MAX = 40
DEFAULT_TIMEOUT = 60
DEFAULT_UMBRAL = 0.8

# Modulos con test acotado y rapido para el modo --batch (fuerza global).
DEFAULT_BATCH: list[tuple[str, str]] = [
    ("scripts/adr_validator.py", "test_ecosistema.TestADRValidator"),
    ("scripts/doc_validator.py", "test_ecosistema.TestDocValidator"),
    ("scripts/lessons_extractor.py", "test_ecosistema.TestLessonsExtractor"),
    ("scripts/index_knowledge.py", "test_ecosistema.TestIndexKnowledge"),
    ("scripts/auto_audit.py", "test_ecosistema.TestAutoAudit"),
    ("scripts/diagnostico.py", "test_ecosistema.TestDiagnostico"),
]

OP_MAP: dict[type, type] = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.GtE: ast.Lt,
    ast.Gt: ast.LtE,
    ast.LtE: ast.Gt,
    ast.Is: ast.IsNot,
    ast.IsNot: ast.Is,
    ast.In: ast.NotIn,
    ast.NotIn: ast.In,
}


class _Mutador(ast.NodeTransformer):
    """Aplica UNA mutacion (indice `objetivo`) y/o registra descripciones."""

    def __init__(self, objetivo: int | None = None) -> None:
        self.objetivo = objetivo
        self.indice = 0
        self.descripciones: list[str] = []

    def _toca(self, descripcion: str) -> bool:
        actual = self.indice
        self.indice += 1
        self.descripciones.append(descripcion)
        return self.objetivo is not None and actual == self.objetivo

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        nuevos = []
        for op in node.ops:
            tipo = type(op)
            if tipo in OP_MAP and self._toca(f"linea {node.lineno}: comparador {tipo.__name__}"):
                nuevos.append(OP_MAP[tipo]())
            else:
                nuevos.append(op)
        node.ops = nuevos
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, bool) and self._toca(f"linea {node.lineno}: booleano {node.value}"):
            node.value = not node.value
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        self.generic_visit(node)
        tipo = type(node.op).__name__
        if self._toca(f"linea {node.lineno}: operador logico {tipo}"):
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node


def descripciones_mutantes(source: str) -> list[str]:
    mut = _Mutador()
    mut.visit(ast.parse(source))
    return mut.descripciones


def generar_mutantes(source: str) -> list[tuple[str, str]]:
    """Devuelve [(descripcion, codigo)] con una mutacion por entrada."""
    mutantes: list[tuple[str, str]] = []
    for i, desc in enumerate(descripciones_mutantes(source)):
        arbol = ast.parse(source)
        mut = _Mutador(objetivo=i)
        mut.visit(arbol)
        ast.fix_missing_locations(arbol)
        mutantes.append((desc, ast.unparse(arbol)))
    return mutantes


def _ejecutar_tests(root: Path, test_target: str, timeout: int) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", test_target],
        cwd=str(root / "tests"), capture_output=True, text=True, timeout=timeout,
    )
    return proc.returncode


def medir(
    root: Path,
    modulo_rel: str,
    test_target: str,
    max_mutantes: int = DEFAULT_MAX,
    timeout: int = DEFAULT_TIMEOUT,
    ejecutar=None,
) -> dict:
    """Genera mutantes del modulo y ejecuta `test_target` sobre cada uno."""
    ruta = Path(root) / modulo_rel
    original = ruta.read_text(encoding="utf-8")
    mutantes = generar_mutantes(original)[:max_mutantes]
    muertos = 0
    sobrevivientes: list[str] = []
    try:
        for desc, codigo in mutantes:
            ruta.write_text(codigo, encoding="utf-8")
            try:
                rc = ejecutar(desc) if ejecutar else _ejecutar_tests(Path(root), test_target, timeout)
            except subprocess.TimeoutExpired:
                rc = 1  # un cuelgue cuenta como mutante detectado
            if rc == 0:
                sobrevivientes.append(desc)
            else:
                muertos += 1
    finally:
        ruta.write_text(original, encoding="utf-8")
    total = len(mutantes)
    return {
        "modulo": modulo_rel,
        "test": test_target,
        "total": total,
        "mutantes_muertos": muertos,
        "sobrevivientes": sobrevivientes,
        "score": (muertos / total) if total else 1.0,
    }


def medir_batch(
    root: Path,
    pares: list[tuple[str, str]] | None = None,
    max_mutantes: int = DEFAULT_MAX,
    timeout: int = DEFAULT_TIMEOUT,
    ejecutar=None,
) -> dict:
    """Mide varios modulos (module, test) y agrega el score global.

    El score global se pondera por numero de mutantes: suma de muertos entre
    suma de totales. Un modulo sin mutantes generables no altera el agregado.
    """
    resultados = [
        medir(root, modulo_rel, test_target, max_mutantes, timeout, ejecutar)
        for modulo_rel, test_target in (pares if pares is not None else DEFAULT_BATCH)
    ]
    total = sum(r["total"] for r in resultados)
    muertos = sum(r["mutantes_muertos"] for r in resultados)
    return {
        "batch": resultados,
        "total": total,
        "mutantes_muertos": muertos,
        "score": (muertos / total) if total else 1.0,
    }


def _copia_temporal(root: Path) -> Path:
    destino = Path(tempfile.mkdtemp(prefix="mutation_check_"))
    ignorar = shutil.ignore_patterns(".git", ".venv", "venv", "__pycache__", ".storage", "*.pyc")
    for sub in ("scripts", "tests"):
        shutil.copytree(root / sub, destino / sub, ignore=ignorar)
    return destino


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chequeo de mutaciones (REQ-015)")
    parser.add_argument("--module", default=DEFAULT_MODULE, help="Modulo a mutar (ruta relativa)")
    parser.add_argument("--test", default=DEFAULT_TEST, help="Objetivo unittest (modulo.Clase)")
    parser.add_argument("--batch", action="store_true", help="Mide DEFAULT_BATCH y agrega el score global")
    parser.add_argument("--max-mutantes", type=int, default=DEFAULT_MAX)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Timeout por mutante (s)")
    parser.add_argument("--umbral", type=float, default=DEFAULT_UMBRAL, help="Score minimo con --strict")
    parser.add_argument("--in-place", action="store_true", help="No usar copia temporal (avanzado)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Falla si el score < umbral")
    args = parser.parse_args(argv)

    root = ROOT if args.in_place else _copia_temporal(ROOT)
    try:
        if args.batch:
            resultado = medir_batch(root, None, args.max_mutantes, args.timeout)
        else:
            resultado = medir(root, args.module, args.test, args.max_mutantes, args.timeout)
    finally:
        if root is not ROOT:
            shutil.rmtree(root, ignore_errors=True)

    if args.json:
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    elif args.batch:
        for r in resultado["batch"]:
            print(f"  {r['modulo']:<34} {r['mutantes_muertos']:>3}/{r['total']:<3} score {r['score']:.3f}")
        print(f"Batch: {resultado['mutantes_muertos']}/{resultado['total']}  score {resultado['score']:.3f}")
        for r in resultado["batch"]:
            for s in r["sobrevivientes"]:
                print(f"  [SOBREVIVE] {r['modulo']} {s}")
    else:
        print(f"Modulo: {resultado['modulo']}  (test: {resultado['test']})")
        print(f"Mutantes: {resultado['total']}  muertos: {resultado['mutantes_muertos']}  score: {resultado['score']:.3f}")
        for s in resultado["sobrevivientes"]:
            print(f"  [SOBREVIVE] {s}")
    if resultado["total"] == 0:
        print("No se generaron mutantes (revisar el modulo o el maximo).", file=sys.stderr)
        return 1
    if args.strict and resultado["score"] < args.umbral:
        print(f"Score {resultado['score']:.3f} < umbral {args.umbral}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
