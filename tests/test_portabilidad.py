#!/usr/bin/env python3
"""Tests de portabilidad: verificador portable e init en proyectos externos (REQ-028).
"""

import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import portable_verifier as pv  # noqa: E402

class TestPortableVerifier(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / ".docs" / "requirements").mkdir(parents=True)
        (self.tmp / ".docs" / "lessons").mkdir()
        (self.tmp / ".docs" / "knowledge").mkdir()
        (self.tmp / ".docs" / "requirements" / "REQ-001.md").write_text(
            "# REQ-001\n", encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_run_error_os_y_timeout(self):
        with mock.patch.object(pv.subprocess, "run", side_effect=OSError("boom")):
            code, salida = pv._run(["python", "x"], self.tmp)
        self.assertEqual(code, 1)
        self.assertIn("no se pudo ejecutar", salida)
        with mock.patch.object(
            pv.subprocess, "run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)
        ):
            code, salida = pv._run(["python", "x"], self.tmp)
        self.assertEqual(code, 1)
        self.assertIn("no se pudo ejecutar", salida)

    def test_check_traceability_ok_y_fallo(self):
        with mock.patch.object(pv, "_run", return_value=(0, "ok")) as run:
            self.assertEqual(pv.check_traceability(self.tmp, strict=False)["estado"], "OK")
        self.assertEqual(run.call_args.args[0][1], pv._tools("doc_validator.py"))
        self.assertNotIn("--strict", run.call_args.args[0])
        with mock.patch.object(pv, "_run", return_value=(1, "err")) as run:
            self.assertEqual(pv.check_traceability(self.tmp, strict=True)["estado"], "FALLO")
        self.assertIn("--strict", run.call_args.args[0])

    def test_check_knowledge_skip_lite_y_sin_docs(self):
        self.assertEqual(pv.check_knowledge(self.tmp, lite=False)["estado"], "SKIP")
        (self.tmp / ".docs" / "knowledge" / "k.md").write_text("## H2\n", encoding="utf-8")
        self.assertEqual(pv.check_knowledge(self.tmp, lite=True)["estado"], "SKIP")

    def test_check_knowledge_indexa_y_verifica(self):
        (self.tmp / ".docs" / "knowledge" / "k.md").write_text("## H2\n", encoding="utf-8")
        with mock.patch.object(pv, "_run", side_effect=[(0, "indexado"), (0, "fresco")]) as run:
            self.assertEqual(pv.check_knowledge(self.tmp, lite=False)["estado"], "OK")
        self.assertEqual(run.call_count, 2)
        with mock.patch.object(pv, "_run", return_value=(1, "boom")):
            self.assertEqual(pv.check_knowledge(self.tmp, lite=False)["estado"], "FALLO")
        with mock.patch.object(pv, "_run", side_effect=[(0, ""), (1, "viejo")]):
            self.assertEqual(pv.check_knowledge(self.tmp, lite=False)["estado"], "FALLO")

    def test_check_hygiene_readme_requisitos_y_hooks(self):
        estados = {r["check"]: r["estado"] for r in pv.check_hygiene(self.tmp)}
        self.assertEqual(estados["README.md presente"], "WARN")
        self.assertEqual(estados["requisitos en .docs/requirements/"], "OK")
        self.assertNotIn("hooks sincronizados", estados)
        (self.tmp / "README.md").write_text("x", encoding="utf-8")
        (self.tmp / "scripts" / "hooks").mkdir(parents=True)
        (self.tmp / ".git" / "hooks").mkdir(parents=True)
        (self.tmp / "scripts" / "hooks" / "pre-commit").write_text("a", encoding="utf-8")
        (self.tmp / ".git" / "hooks" / "pre-commit").write_text("b", encoding="utf-8")
        estados = {r["check"]: r["estado"] for r in pv.check_hygiene(self.tmp)}
        self.assertEqual(estados["README.md presente"], "OK")
        self.assertEqual(estados["hooks sincronizados"], "WARN")
        (self.tmp / ".git" / "hooks" / "pre-commit").write_text("a", encoding="utf-8")
        estados = {r["check"]: r["estado"] for r in pv.check_hygiene(self.tmp)}
        self.assertEqual(estados["hooks sincronizados"], "OK")

    def test_check_hygiene_sin_requisitos_es_fallo(self):
        shutil.rmtree(self.tmp / ".docs" / "requirements")
        (self.tmp / ".docs" / "requirements").mkdir()
        estados = {r["check"]: r["estado"] for r in pv.check_hygiene(self.tmp)}
        self.assertEqual(estados["requisitos en .docs/requirements/"], "FALLO")

    def test_check_pre_commit(self):
        self.assertIsNone(pv.check_pre_commit(self.tmp))
        (self.tmp / ".git").mkdir()
        with mock.patch.object(pv, "_run", return_value=(0, " M x.py\n?? y.py\nM  z.py")):
            self.assertEqual(pv.check_pre_commit(self.tmp)["estado"], "FALLO")
        with mock.patch.object(pv, "_run", return_value=(0, "M  z.py")):
            self.assertEqual(pv.check_pre_commit(self.tmp)["estado"], "OK")
        with mock.patch.object(pv, "_run", return_value=(1, "fatal")):
            self.assertIsNone(pv.check_pre_commit(self.tmp))

    def test_verificar_incluye_pre_commit_si_hay_git(self):
        (self.tmp / ".git").mkdir()
        with mock.patch.object(pv, "check_traceability", return_value={"check": "t", "estado": "OK", "detalle": ""}), \
                mock.patch.object(pv, "check_lessons", return_value={"check": "l", "estado": "OK", "detalle": ""}), \
                mock.patch.object(pv, "check_knowledge", return_value={"check": "k", "estado": "SKIP", "detalle": ""}), \
                mock.patch.object(pv, "check_hygiene", return_value=[]), \
                mock.patch.object(pv, "check_pre_commit", return_value={"check": "p", "estado": "OK", "detalle": ""}):
            resultados = pv.verificar(self.tmp, lite=True, pre_commit=True)
        self.assertEqual(len(resultados), 4)
        with mock.patch.object(pv, "check_traceability", return_value={"check": "t", "estado": "OK", "detalle": ""}), \
                mock.patch.object(pv, "check_lessons", return_value={"check": "l", "estado": "OK", "detalle": ""}), \
                mock.patch.object(pv, "check_knowledge", return_value={"check": "k", "estado": "SKIP", "detalle": ""}), \
                mock.patch.object(pv, "check_hygiene", return_value=[]), \
                mock.patch.object(pv, "check_pre_commit", return_value=None):
            self.assertEqual(len(pv.verificar(self.tmp, pre_commit=True)), 3)

    def test_main_verde_y_json(self):
        with mock.patch.object(pv, "check_traceability", return_value={"check": "t", "estado": "OK", "detalle": ""}), \
                mock.patch.object(pv, "check_lessons", return_value={"check": "l", "estado": "OK", "detalle": ""}), \
                mock.patch.object(pv, "check_knowledge", return_value={"check": "k", "estado": "SKIP", "detalle": ""}), \
                mock.patch.object(pv, "check_hygiene", return_value=[]), \
                mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(pv.main(["--root", str(self.tmp)]), 0)
        self.assertIn("Resultado portable: 2 OK, 0 FALLOS, 1 SKIP", out.getvalue())

        with mock.patch.object(pv, "check_traceability", return_value={"check": "t", "estado": "FALLO", "detalle": "x"}), \
                mock.patch.object(pv, "check_lessons", return_value={"check": "l", "estado": "OK", "detalle": ""}), \
                mock.patch.object(pv, "check_knowledge", return_value={"check": "k", "estado": "SKIP", "detalle": ""}), \
                mock.patch.object(pv, "check_hygiene", return_value=[]), \
                mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(pv.main(["--root", str(self.tmp), "--json"]), 1)
        self.assertEqual(json.loads(out.getvalue())[0]["estado"], "FALLO")


class TestInitPortable(unittest.TestCase):
    def _init(self, tmp: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(SCRIPTS / "init.sh"), "--root", tmp, "--yes"],
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_init_genera_tooling_y_wrapper_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = self._init(tmp)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for rel in (
                "AGENTS.md",
                "CHECKLIST.md",
                "opencode.json",
                ".docs/requirements/REQ-001.md",
                "scripts/verificar-proyecto.sh",
                "scripts/portable_verifier.py",
                "scripts/doc_validator.py",
                "scripts/lessons_extractor.py",
                "scripts/index_knowledge.py",
                "scripts/hooks/pre-commit",
                "scripts/hooks/commit-msg",
            ):
                self.assertTrue((Path(tmp) / rel).exists(), rel)
            wrapper = (Path(tmp) / "scripts" / "verificar-proyecto.sh").read_text(encoding="utf-8")
            self.assertIn("portable_verifier.py", wrapper)
            self.assertNotIn("304 patrones", wrapper)
            self.assertNotIn("REQ-010", wrapper)

    def test_init_idempotente(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._init(tmp).returncode, 0)
            segundo = self._init(tmp)
            self.assertEqual(segundo.returncode, 0, segundo.stderr)
            self.assertIn("REQ-001.md ya existe", segundo.stdout)

    def test_verificador_portable_verde_en_proyecto_nuevo(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._init(tmp).returncode, 0)
            proc = subprocess.run(
                ["bash", "scripts/verificar-proyecto.sh"],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("0 FALLOS", proc.stdout)

    def test_init_no_contamina_trazabilidad(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._init(tmp).returncode, 0)
            cmd = [sys.executable, "scripts/doc_validator.py"]
            for item in pv.IGNORED_PATHS:
                cmd += ["--ignore", item]
            proc = subprocess.run(
                cmd, cwd=tmp, capture_output=True, text=True, timeout=120
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("Resultado: OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
