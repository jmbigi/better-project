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
        self.repo = self.tmp / "repo"
        ignore = shutil.ignore_patterns(
            ".git", "node_modules", "__pycache__", ".storage", "*.pyc", ".venv", ".venv-audit", "venv"
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


if __name__ == "__main__":
    unittest.main()
