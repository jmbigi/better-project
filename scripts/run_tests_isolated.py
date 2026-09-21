#!/usr/bin/env python3
"""run_tests_isolated.py — Ejecuta cada test en un proceso separado (REQ-026).

Motivo: la suite en un unico proceso acumula el estado de todos los modulos y,
con las dependencias opcionales instaladas (torch/sentence-transformers via
``index_knowledge``, chromadb, llama.cpp), el pico de memoria puede provocar OOM
en equipos con poca RAM. Aislar cada test en su propio subproceso libera la
memoria al terminar, a costa de reimportar los modulos por test.

Uso:
    python3 scripts/run_tests_isolated.py                      # todos los tests
    python3 scripts/run_tests_isolated.py --pattern 'test_mcp*'
    python3 scripts/run_tests_isolated.py --timeout 120        # segundos por test
    python3 scripts/run_tests_isolated.py --list               # solo enumerar

Exit: 0 si todos pasan; 1 si algun test falla, da error o agota el timeout.
Sin dependencias externas (solo stdlib).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "tests"


def discover_tests(pattern: str) -> list[str]:
    """Devuelve los ids fully-qualified de todos los tests descubiertos."""
    loader = unittest.TestLoader()
    suite = loader.discover(str(TESTS_DIR), pattern=pattern, top_level_dir=str(ROOT))
    ids: list[str] = []

    def walk(item: unittest.TestSuite | unittest.TestCase) -> None:
        if isinstance(item, unittest.TestSuite):
            for child in item:
                walk(child)
        else:
            ids.append(item.id())

    walk(suite)
    return ids


def run_one(test_id: str, timeout: int) -> subprocess.CompletedProcess[str]:
    """Ejecuta un unico test en un subproceso y captura su salida."""
    return subprocess.run(
        [sys.executable, "-m", "unittest", "-q", test_id],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def run_in_process(pattern: str) -> int:
    """Ejecuta la suite completa in-process (fallback anti-recursion)."""
    loader = unittest.TestLoader()
    suite = loader.discover(str(TESTS_DIR), pattern=pattern, top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ejecuta cada test del ecosistema en un proceso separado (REQ-026)."
    )
    parser.add_argument(
        "--pattern",
        default="test*.py",
        help="Patron de descubrimiento de tests (default: test*.py).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Segundos maximos por test antes de abortarlo (default: 300).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Solo lista los tests descubiertos, sin ejecutarlos.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Muestra una linea por test (OK/FALLO) ademas del progreso.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    test_ids = discover_tests(args.pattern)

    if args.list:
        for test_id in test_ids:
            print(test_id)
        print(f"Total: {len(test_ids)} tests")
        return 0

    # Dentro de una copia temporal de integracion (REQ-010) no aplicar el
    # aislamiento: cada test de integracion correria cientos de subprocesos
    # anidados. La guarda ya omite esos tests; aqui se ejecuta el resto
    # in-process, que es rapido y no acumula memoria de deps opcionales.
    if os.environ.get("BETTER_TEST_INTEGRACION"):
        print("run_tests_isolated: BETTER_TEST_INTEGRACION activo "
              "(copia temporal): se ejecuta in-process")
        return run_in_process(args.pattern)

    if not test_ids:
        print(f"[FALLO] no se descubrieron tests con patron '{args.pattern}'")
        return 1

    print(f"run_tests_isolated: {len(test_ids)} tests, un proceso por test "
          f"(timeout {args.timeout}s)")
    started = time.monotonic()
    failures: list[tuple[str, str]] = []
    passed = 0

    for index, test_id in enumerate(test_ids, start=1):
        try:
            proc = run_one(test_id, args.timeout)
        except subprocess.TimeoutExpired:
            failures.append((test_id, f"TIMEOUT: excedio {args.timeout}s"))
            sys.stdout.write("T")
            sys.stdout.flush()
            if args.verbose:
                print(f" [{index}/{len(test_ids)}] TIMEOUT {test_id}")
            continue

        if proc.returncode == 0:
            passed += 1
            sys.stdout.write(".")
            if args.verbose:
                print(f" [{index}/{len(test_ids)}] OK {test_id}")
        else:
            failures.append((test_id, proc.stdout + proc.stderr))
            sys.stdout.write("F")
            if args.verbose:
                print(f" [{index}/{len(test_ids)}] FALLO {test_id}")
        sys.stdout.flush()

    elapsed = time.monotonic() - started
    print()
    print(f"Resultado: {passed} OK, {len(failures)} FALLOS de {len(test_ids)} "
          f"en {elapsed:.1f}s")

    if failures:
        print()
        for test_id, detail in failures:
            print(f"--- FALLO: {test_id} ---")
            print(detail.rstrip())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
