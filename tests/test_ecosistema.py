#!/usr/bin/env python3
"""Tests de integracion del ecosistema: el hook pre-commit ejecuta el verificador
sobre una copia temporal y aborta commits rotos (REQ-010).

El resto de la suite vive en modulos tematicos: test_pilares, test_verificador,
test_mcp_tui, test_tydm, test_cadena_suministro y test_portabilidad.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


class TestIntegracionHook(unittest.TestCase):
    """Test de integracion: el hook pre-commit ejecuta verificar-proyecto.sh
    sobre una copia temporal del repo y ABORTA un commit roto (el safeguard se
    prueba tambien en su modo de fallo, leccion de la ronda 16; P1.1).
    """

    def setUp(self):
        if os.environ.get("BETTER_TEST_INTEGRACION"):
            # El verificador ejecuta la propia suite dentro de la copia:
            # la guarda evita recursion infinita de copias.
            self.skipTest("dentro de la copia temporal de integracion")
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = self.tmp / "repo"
        ignore = shutil.ignore_patterns(
            ".git", "node_modules", "__pycache__", ".storage", "*.pyc", ".venv", ".venv-audit", "venv",
            ".local", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".benchmarks",
        )
        shutil.copytree(ROOT, self.repo, ignore=ignore)

    def _git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.repo, capture_output=True, text=True
        )

    def test_hook_aborta_commit_roto_y_permite_commit_verde(self):
        # La guarda se exporta al entorno para que la suite que el verificador
        # ejecuta DENTRO de la copia omita este mismo test (sin recursion).
        os.environ["BETTER_TEST_INTEGRACION"] = "1"
        # La mutacion ya corre en la verificacion externa: dentro de la copia
        # se omite (guarda BETTER_MUTATION_ACTIVE) para no duplicarla.
        os.environ["BETTER_MUTATION_ACTIVE"] = "1"
        try:
            self.assertEqual(self._git("init", "-q").returncode, 0)
            self._git("config", "user.email", "dummy@example.com")
            self._git("config", "user.name", "dummy")
            # Commit bootstrap SIN hook: con HEAD no nacido, git fsck emite
            # avisos que el check "sin objetos huerfanos" tomaria como fallo.
            self._git("add", "-A")
            boot = self._git("commit", "-q", "--no-verify", "-m", "bootstrap")
            self.assertEqual(boot.returncode, 0, boot.stdout + boot.stderr)
            hooks = self.repo / ".git" / "hooks"
            for nombre in ("pre-commit", "commit-msg"):
                shutil.copy(self.repo / "scripts" / "hooks" / nombre, hooks / nombre)

            # Commit verde: los hooks deben dejar pasar el repo intacto.
            # Incluye Assisted-by: porque el hook commit-msg lo exige (REQ-019).
            with (self.repo / "scripts" / "tui.py").open("a", encoding="utf-8") as fh:
                fh.write("\n# comentario inocuo para el commit verde\n")
            self._git("add", "-A")
            verde = self._git("commit", "-q", "-m", "verde", "-m", "Assisted-by: test")
            self.assertEqual(verde.returncode, 0, verde.stdout + verde.stderr)

            # Commit roto: referencia a un REQ inexistente (doc_validator falla).
            with (self.repo / "scripts" / "tui.py").open("a", encoding="utf-8") as fh:
                fh.write("\n# REQ-999 referencia rota para el test\n")
            self._git("add", "-A")
            roto = self._git("commit", "-q", "-m", "roto")
            self.assertNotEqual(roto.returncode, 0, "el hook no aborto un commit roto")
            salida = roto.stdout + roto.stderr
            # check() no propaga la salida del comando: se verifica el check concreto
            self.assertIn("[FALLO] trazabilidad REQ valida", salida)
            self.assertIn("FALLOS", salida)

            # HEAD intacto: solo quedan bootstrap + commit verde.
            log = self._git("log", "--oneline").stdout.strip().splitlines()
            self.assertEqual(len(log), 2)
        finally:
            os.environ.pop("BETTER_TEST_INTEGRACION", None)
            os.environ.pop("BETTER_MUTATION_ACTIVE", None)


class TestFlujoEcosistema(unittest.TestCase):
    """Tests rapidos (tmp dir, sin copiar el repo) del flujo nucleo del
    ecosistema: REQ -> doc_validator, y lecciones -> lessons_extractor.

    Complementan al test pesado de integracion del hook: cubren el ciclo
    REQ/leccion en segundos y pueden fallar de verdad (P1.1).
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _doc_validator(self, root: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "doc_validator.py"), "--root", str(root)],
            capture_output=True,
            text=True,
        )

    def _req_valido(self) -> str:
        return (
            "---\n"
            "id: REQ-001\n"
            "titulo: Requisito de prueba\n"
            "estado: Implementado\n"
            "prioridad: Baja\n"
            "version: 1.0\n"
            "fecha_creacion: 2026-10-05\n"
            "---\n"
            "# REQ-001: Requisito de prueba\n"
        )

    def test_req_valido_pasa_y_ref_rota_falla(self):
        req_dir = self.tmp / ".docs" / "requirements"
        req_dir.mkdir(parents=True)
        (req_dir / "REQ-001.md").write_text(self._req_valido(), encoding="utf-8")
        src = self.tmp / "src"
        src.mkdir()
        app = src / "app.py"
        app.write_text("# REQ-001\nx = 1\n", encoding="utf-8")

        verde = self._doc_validator(self.tmp)
        self.assertEqual(verde.returncode, 0, verde.stdout + verde.stderr)
        self.assertIn("Resultado: OK", verde.stdout)

        with app.open("a", encoding="utf-8") as fh:
            fh.write("# REQ-999 referencia rota\n")
        roto = self._doc_validator(self.tmp)
        self.assertNotEqual(roto.returncode, 0, "doc_validator no fallo con una ref a REQ inexistente")

    def test_leccion_valida_y_campos_faltantes(self):
        import lessons_extractor

        lessons_dir = self.tmp / "lessons"
        lessons_dir.mkdir()
        original = lessons_extractor.LESSONS_DIR
        lessons_extractor.LESSONS_DIR = lessons_dir
        self.addCleanup(setattr, lessons_extractor, "LESSONS_DIR", original)

        valida = (
            "- id: LSN-900\n"
            "  proyecto: prueba\n"
            "  fase: verificacion\n"
            "  categoria: tests\n"
            "  problema: problema de prueba\n"
            "  recomendacion: recomendacion de prueba\n"
            "  estado: Resuelta\n"
            "  fecha: 2026-10-05\n"
        )
        (lessons_dir / "2026.yaml").write_text(valida, encoding="utf-8")
        lessons, problems = lessons_extractor.validate()
        self.assertEqual(problems, [])
        self.assertEqual(len(lessons), 1)

        with (lessons_dir / "2026.yaml").open("a", encoding="utf-8") as fh:
            fh.write("- id: LSN-901\n  proyecto: prueba\n  fecha: 2026-10-05\n")
        _, problems = lessons_extractor.validate()
        self.assertTrue(problems, "lessons_extractor no detecto una leccion con campos faltantes")
        self.assertTrue(any("LSN-901" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
