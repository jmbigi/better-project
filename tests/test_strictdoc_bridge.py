#!/usr/bin/env python3
"""Tests del puente StrictDoc (REQ-032): casos límite que PUEDEN fallar (P1.1).

El bridge valida .sdoc sin strictdoc instalado (stdlib); estos tests crean
proyectos mínimos en temporales y verifican estructura, UIDs, trazabilidad y
la no colisión con doc_validator (ADR-011).
"""

import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import doc_validator as dv  # noqa: E402
import strictdoc_bridge as sb  # noqa: E402

SDOC_VALIDO = """[DOCUMENT]
TITLE: Doc de prueba
OPTIONS:
  MARKUP: Markdown

[REQUIREMENT]
UID: SDOC-001
TITLE: Algo
STATEMENT: El sistema debera hacer algo.
"""

SDOC_CON_MERMAID = SDOC_VALIDO + """
[TEXT]
STATEMENT: >>>
Texto con diagrama:

```mermaid
flowchart LR
    A[uno] --> B[dos]
```
<<<
"""


def _proyecto(tmp: str, sdoc: dict[str, str] | None = None, codigo: dict[str, str] | None = None) -> Path:
    root = Path(tmp)
    for rel, txt in (sdoc or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
    for rel, txt in (codigo or {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(txt, encoding="utf-8")
    return root


class TestStrictDocBridge(unittest.TestCase):
    """REQ-032: estructura, UIDs, trazabilidad y no colisión con doc_validator."""

    def test_repo_real_valido_con_dogfood(self):
        # el repo lleva .docs/requirements/puente-strictdoc.sdoc (SDOC-001/002)
        errores, n_uids, n_refs = sb.validar(sb.ROOT)
        self.assertEqual(errores, [])
        self.assertGreaterEqual(n_uids, 2)
        self.assertGreaterEqual(n_refs, 2)

    def test_uid_duplicado_es_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            dup = SDOC_VALIDO + "\n[REQUIREMENT]\nUID: SDOC-001\nTITLE: Otro\nSTATEMENT: Repetido.\n"
            root = _proyecto(tmp, {".docs/requirements/a.sdoc": dup})
            errores, _, _ = sb.validar(root)
        self.assertTrue(any("duplicado" in e for e in errores), errores)

    def test_requirement_sin_uid_es_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            mal = SDOC_VALIDO + "\n[REQUIREMENT]\nTITLE: Sin uid\nSTATEMENT: Falta UID.\n"
            root = _proyecto(tmp, {".docs/requirements/a.sdoc": mal})
            errores, _, _ = sb.validar(root)
        self.assertTrue(any("sin UID" in e for e in errores), errores)

    def test_requirement_sin_title_ni_statement_es_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            mal = SDOC_VALIDO + "\n[REQUIREMENT]\nUID: SDOC-002\n"
            root = _proyecto(tmp, {".docs/requirements/a.sdoc": mal})
            errores, _, _ = sb.validar(root)
        self.assertTrue(any("sin TITLE ni STATEMENT" in e for e in errores), errores)

    def test_referencia_codigo_a_uid_inexistente_es_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _proyecto(
                tmp,
                {".docs/requirements/a.sdoc": SDOC_VALIDO},
                {"src/app.py": "# SDOC-999: implementa algo que no existe\n"},
            )
            errores, _, n_refs = sb.validar(root)
        self.assertEqual(n_refs, 1)
        self.assertTrue(any("SDOC-999" in e for e in errores), errores)

    def test_referencia_codigo_valida_sin_errores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _proyecto(
                tmp,
                {".docs/requirements/a.sdoc": SDOC_CON_MERMAID},
                {"src/app.py": "# SDOC-001: implementado en esta funcion\n"},
            )
            errores, n_uids, n_refs = sb.validar(root)
        self.assertEqual(errores, [])
        self.assertEqual((n_uids, n_refs), (1, 1))

    def test_multilinea_sin_cerrar_es_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            mal = SDOC_VALIDO + "\n[TEXT]\nSTATEMENT: >>>\nsin cierre\n"
            root = _proyecto(tmp, {".docs/requirements/a.sdoc": mal})
            errores, _, _ = sb.validar(root)
        self.assertTrue(any("sin cerrar" in e for e in errores), errores)

    def test_no_colision_con_doc_validator(self):
        # ADR-011: SDOC-001 NO casa con CODE_RE (REQ-\d{3}); SDOC-REQ-029 SÍ
        # casaría (por eso el esquema evita la subcadena REQ-\d{3}).
        self.assertIsNone(dv.CODE_RE.search("# SDOC-001"))
        self.assertEqual(dv.CODE_RE.search("SDOC-REQ-029").group(1), "029")

    def test_directorio_tests_excluido_del_escaneo(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _proyecto(
                tmp,
                {".docs/requirements/a.sdoc": SDOC_VALIDO},
                {"tests/test_x.py": "# SDOC-999: referencia sintética de test\n"},
            )
            errores, _, n_refs = sb.validar(root)
        self.assertEqual((errores, n_refs), ([], 0))

    def test_root_externo_sin_docs_requirements(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _proyecto(tmp, {"requisitos.sdoc": SDOC_VALIDO})
            errores, n_uids, _ = sb.validar(root)
        self.assertEqual((errores, n_uids), ([], 1))

    def test_json_maquina_legible(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _proyecto(tmp, {".docs/requirements/a.sdoc": SDOC_VALIDO})
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "strictdoc_bridge.py"), "--root", str(root), "--json"],
                capture_output=True, text=True,
            )
        datos = json.loads(proc.stdout)
        self.assertTrue(datos["ok"])
        self.assertEqual(datos["uids"], 1)
        self.assertEqual(proc.returncode, 0)

    def test_exit_1_con_errores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _proyecto(tmp, {".docs/requirements/a.sdoc": "[REQUIREMENT]\nUID: SDOC-001\n"})
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "strictdoc_bridge.py"), "--root", str(root)],
                capture_output=True, text=True,
            )
        self.assertEqual(proc.returncode, 1)

    def test_bridge_es_stdlib_puro(self):
        # ADR-011 (pre-mortem): el bridge nunca importa paquetes externos.
        arbol = ast.parse((SCRIPTS / "strictdoc_bridge.py").read_text(encoding="utf-8"))
        externos = set()
        for n in ast.walk(arbol):
            if isinstance(n, ast.Import):
                externos |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module:
                externos.add(n.module.split(".")[0])
        self.assertLessEqual(externos, set(sys.stdlib_module_names), externos)


if __name__ == "__main__":
    unittest.main()
