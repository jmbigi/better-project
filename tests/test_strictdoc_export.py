#!/usr/bin/env python3
"""Tests del runner de export StrictDoc (REQ-032): casos límite que PUEDEN fallar (P1.1).

El runner no importa strictdoc (solo stdlib; habla con el binario por
subprocess). Los tests simulan el binario con mocks (sin instalar la capa,
P1.21) y añaden un E2E real que se omite donde la capa no está instalada.
"""

import ast
import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import strictdoc_export as se  # noqa: E402


def _run_simulado(stdout_version: str = "0.30.1", rc_export: int = 0, crea_html: bool = True):
    """Mock de subprocess.run: responde a --version y simula el export."""

    def fake(cmd, **kwargs):
        if "--version" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=stdout_version, stderr="")
        if rc_export != 0:
            return subprocess.CompletedProcess(cmd, rc_export, stdout="", stderr="fallo simulado")
        if crea_html:
            out = Path(cmd[cmd.index("--output-dir") + 1])
            html = out / "html"
            html.mkdir(parents=True, exist_ok=True)
            (html / "index.html").write_text("<html>SDOC-001 fake</html>", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, stdout="export ok", stderr="")

    return fake


class TestFunciones(unittest.TestCase):
    def test_pin_leido_del_requirements(self):
        self.assertEqual(se.pin_esperado(), "0.30.1")

    def test_localizar_override_inexistente_no_cae_al_venv(self):
        with mock.patch.dict("os.environ", {"STRICTDOC_BIN": "/no/existe"}):
            self.assertIsNone(se.localizar())

    def test_localizar_override_existente(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "strictdoc"
            fake.write_text("#!/bin/sh\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {"STRICTDOC_BIN": str(fake)}):
                self.assertEqual(se.localizar(), fake)

    def test_localizar_venv_aislado_en_root_dado(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cand = root / ".local" / "strictdoc-venv" / "bin" / "strictdoc"
            cand.parent.mkdir(parents=True)
            cand.write_text("#!/bin/sh\n", encoding="utf-8")
            with mock.patch.dict("os.environ", {"STRICTDOC_BIN": ""}):
                self.assertEqual(se.localizar(root), cand)

    def test_sdoc_files_del_repo_incluye_dogfood(self):
        archivos = se.sdoc_files()
        self.assertTrue(any(p.name == "puente-strictdoc.sdoc" for p in archivos))

    def test_sdoc_files_root_vacio(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(se.sdoc_files(Path(tmp)), [])

    def test_script_es_stdlib_puro(self):
        arbol = ast.parse((SCRIPTS / "strictdoc_export.py").read_text(encoding="utf-8"))
        externos = set()
        for n in ast.walk(arbol):
            if isinstance(n, ast.Import):
                externos |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module:
                externos.add(n.module.split(".")[0])
        self.assertLessEqual(externos, set(sys.stdlib_module_names), externos)

    def test_normalizar_arbol_mapea_uuid_de_forma_consistente(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            uuid = "12310813c36b49e78c7d92f2cd99b864"
            (raiz / "a.html").write_text(
                '<meta name="strictdoc-search-index-timestamp" content="1791044876.02">\n'
                f'<li data-nodeid="{uuid}">', encoding="utf-8")
            (raiz / "b.js").write_text(
                f'{{"_LINK":"{uuid}","x":"42c3dea3a81145d68164637e1b4407f2"}}', encoding="utf-8")
            n = se.normalizar_arbol(raiz)
            self.assertEqual(n, 2)
            a = (raiz / "a.html").read_text(encoding="utf-8")
            b = (raiz / "b.js").read_text(encoding="utf-8")
            self.assertIn('content="0"', a)
            self.assertNotIn(uuid, a + b)
            reemplazo = a.split('data-nodeid="')[1].split('"')[0]
            self.assertIn(reemplazo, b)

    def test_normalizar_arbol_es_idempotente(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "a.html").write_text(
                'data-nodeid="12310813c36b49e78c7d92f2cd99b864"', encoding="utf-8")
            se.normalizar_arbol(raiz)
            primera = (raiz / "a.html").read_text(encoding="utf-8")
            se.normalizar_arbol(raiz)
            self.assertEqual((raiz / "a.html").read_text(encoding="utf-8"), primera)

    def test_normalizar_arbol_no_toca_texto_sin_patrones(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            (raiz / "a.txt").write_text("texto normal sin uuid", encoding="utf-8")
            self.assertEqual(se.normalizar_arbol(raiz), 0)
            self.assertEqual((raiz / "a.txt").read_text(encoding="utf-8"), "texto normal sin uuid")

    def test_normalizar_search_index_ordena_y_preserva_sufijo(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            js = raiz / "static_html_search_index.js"
            js.write_text(
                'window.StrictDoc.search.index = {"b":[2,1],"a":{"x":";"}};\n'
                'window.StrictDoc.search.extra = 1;\n', encoding="utf-8")
            se.normalizar_arbol(raiz)
            self.assertEqual(
                js.read_text(encoding="utf-8"),
                'window.StrictDoc.search.index = {"a":{"x":";"},"b":[1,2]};\n'
                'window.StrictDoc.search.extra = 1;\n')


class TestCLI(unittest.TestCase):
    def _main(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = se.main(argv)
        return rc, out.getvalue(), err.getvalue()

    def test_check_ok(self):
        with mock.patch.object(se, "localizar", return_value=Path("/fake")), \
             mock.patch.object(se.subprocess, "run", side_effect=_run_simulado()):
            rc, out, _ = self._main(["--check"])
        self.assertEqual(rc, 0)
        self.assertIn("0.30.1", out)

    def test_check_version_distinta_falla(self):
        with mock.patch.object(se, "localizar", return_value=Path("/fake")), \
             mock.patch.object(se.subprocess, "run", side_effect=_run_simulado(stdout_version="9.9.9")):
            rc, _, err = self._main(["--check"])
        self.assertEqual(rc, 1)
        self.assertIn("9.9.9", err)

    def test_sin_capa_exit_2_con_guia(self):
        with mock.patch.object(se, "localizar", return_value=None):
            rc, out, _ = self._main(["--check"])
        self.assertEqual(rc, 2)
        self.assertIn("setup_strictdoc.sh", out)

    def test_export_ok_crea_html(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(se, "localizar", return_value=Path("/fake")), \
             mock.patch.object(se.subprocess, "run", side_effect=_run_simulado()):
            rc, out, _ = self._main(["--output-dir", tmp, "--inputs",
                                     str(ROOT / ".docs" / "requirements" / "puente-strictdoc.sdoc")])
            self.assertEqual(rc, 0)
            self.assertTrue((Path(tmp) / "html" / "index.html").exists())

    def test_export_fallido_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(se, "localizar", return_value=Path("/fake")), \
             mock.patch.object(se.subprocess, "run", side_effect=_run_simulado(rc_export=1)):
            rc, _, err = self._main(["--output-dir", tmp])
        self.assertEqual(rc, 1)
        self.assertIn("fallo simulado", err)

    def test_export_sin_html_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp, \
             mock.patch.object(se, "localizar", return_value=Path("/fake")), \
             mock.patch.object(se.subprocess, "run", side_effect=_run_simulado(crea_html=False)):
            rc, _, err = self._main(["--output-dir", tmp])
        self.assertEqual(rc, 1)
        self.assertIn("no genero HTML", err)

    def test_smoke_ok(self):
        with mock.patch.object(se, "localizar", return_value=Path("/fake")), \
             mock.patch.object(se.subprocess, "run", side_effect=_run_simulado()):
            rc, out, _ = self._main(["--smoke"])
        self.assertEqual(rc, 0)
        self.assertIn("smoke OK", out)

    def test_sin_sdoc_nada_que_hacer(self):
        with mock.patch.object(se, "localizar", return_value=Path("/fake")), \
             mock.patch.object(se, "sdoc_files", return_value=[]), \
             mock.patch.object(se.subprocess, "run", side_effect=_run_simulado()):
            rc, out, _ = self._main([])
        self.assertEqual(rc, 0)
        self.assertIn("sin .sdoc", out)


class TestE2EReal(unittest.TestCase):
    """E2E con el binario real; se omite si la capa no está instalada."""

    @unittest.skipIf(se.localizar() is None, "capa StrictDoc no instalada (REQ-032)")
    def test_check_smoke_y_repro_con_binario_real(self):
        for modo in ("--check", "--smoke", "--repro"):
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "strictdoc_export.py"), modo],
                capture_output=True, text=True, timeout=300,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
