#!/usr/bin/env python3
"""Tests del verificador, la sonda de policies, la mutacion y el dashboard de
salud (REQ-010/REQ-015/REQ-024/REQ-031).
"""

import ast
import io
import json
import os
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

import health_dashboard as hd  # noqa: E402
import mutation_check as mc  # noqa: E402
import probar_policies as pp  # noqa: E402
import verificar_proyecto as vpy  # noqa: E402

class TestProbarPolicies(unittest.TestCase):
    """REQ-031: la sonda de guardarraíles en runtime se prueba con el runner
    mockeado (sin llamadas reales a opencode ni a modelos, P0.19)."""

    def _silencio(self):
        return mock.patch("sys.stdout", io.StringIO())

    def test_config_denegando_todo_menos_opencode(self):
        cfg = pp.config_denegando_todo_menos_opencode()
        pol = cfg["experimental"]["policies"]
        self.assertEqual(pol[0], {"effect": "deny", "action": "provider.use", "resource": "*"})
        self.assertEqual(pol[1]["resource"], "opencode")
        self.assertEqual(cfg["permission"]["bash"], {"*": "deny"})

    def test_proveedor_ejecuto_detecta_respuesta(self):
        self.assertTrue(pp.proveedor_ejecuto("> build · deepseek-flash\n¡Hola!"))
        self.assertFalse(pp.proveedor_ejecuto("> build · x\nError: denied"))
        self.assertFalse(pp.proveedor_ejecuto("Error: ProviderModelNotFoundError"))

    def test_sonda_provider_detecta_hueco(self):
        # el modelo responde pese al deny → la sonda debe reportar hueco (1)
        def runner_ejecuta(cwd, modelo, prompt, xdg, timeout=180):
            return subprocess.CompletedProcess([], 0, "> build · deepseek-flash\n¡Hola!", "")

        with self._silencio():
            self.assertEqual(pp.sonda_provider_denegado("deepseek/deepseek-flash", runner=runner_ejecuta), 1)

    def test_sonda_provider_bloqueo_es_ok(self):
        def runner_bloqueado(cwd, modelo, prompt, xdg, timeout=180):
            return subprocess.CompletedProcess([], 1, "", "Error: provider denied by policy")

        with self._silencio():
            self.assertEqual(pp.sonda_provider_denegado("deepseek/deepseek-flash", runner=runner_bloqueado), 0)

    def test_sonda_bash_target_sobrevive_con_deny_es_ok(self):
        def runner_bloqueado(cwd, modelo, prompt, xdg, timeout=180):
            return subprocess.CompletedProcess(
                [], 0, '> build · m\nrm -rf failed {"permission":"bash","pattern":"rm -rf *","action":"deny"}', "")

        with self._silencio():
            self.assertEqual(pp.sonda_bash_deny("modelo-x", runner=runner_bloqueado), 0)

    def test_sonda_bash_target_borrado_es_hueco(self):
        def runner_borra(cwd, modelo, prompt, xdg, timeout=180):
            shutil.rmtree(cwd / "target")
            return subprocess.CompletedProcess([], 0, "> build · m\nhecho", "")

        with self._silencio():
            self.assertEqual(pp.sonda_bash_deny("modelo-x", runner=runner_borra), 1)

    def test_sonda_bash_supervivencia_sin_evidencia_es_inconclusa(self):
        def runner_rechaza(cwd, modelo, prompt, xdg, timeout=180):
            return subprocess.CompletedProcess([], 0, "> build · m\nno puedo borrar eso", "")

        with self._silencio():
            self.assertEqual(pp.sonda_bash_deny("modelo-x", runner=runner_rechaza), 2)


class TestVerificador(unittest.TestCase):
    """REQ-010: el propio verificador se prueba en modo fallo (P1.1):
    debe pasar sobre una copia intacta y FALLAR sobre una copia corrupta.
    """

    def _copia(self):
        if os.environ.get("BETTER_TEST_INTEGRACION"):
            self.skipTest("dentro de la copia temporal de integracion")
        tmp = Path(tempfile.mkdtemp())
        repo = tmp / "repo"
        ignore = shutil.ignore_patterns(
            ".git", "node_modules", "__pycache__", ".storage", "*.pyc", ".venv", ".venv-audit", "venv"
        )
        shutil.copytree(ROOT, repo, ignore=ignore)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "dummy@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "dummy"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        # bootstrap sin hook: con HEAD no nacido git fsck emite avisos (LSN-005)
        subprocess.run(["git", "commit", "-qm", "bootstrap", "--no-verify"], cwd=repo, check=True)
        for nombre in ("pre-commit", "commit-msg"):
            shutil.copy(repo / "scripts" / "hooks" / nombre, repo / ".git" / "hooks" / nombre)
        return repo

    def _verifica(self, repo):
        env = {**os.environ, "BETTER_TEST_INTEGRACION": "1", "BETTER_MUTATION_ACTIVE": "1"}
        return subprocess.run(
            [sys.executable, "scripts/verificar_proyecto.py", "--pre-commit"],
            cwd=repo, capture_output=True, text=True, env=env,
        )

    def test_verificador_en_verde_sobre_copia_intacta(self):
        proc = self._verifica(self._copia())
        self.assertEqual(proc.returncode, 0, proc.stdout[-2000:] + proc.stderr[-2000:])

    def test_verificador_detecta_regla_p0_eliminada(self):
        repo = self._copia()
        agents = repo / "AGENTS.md"
        lineas = agents.read_text(encoding="utf-8").splitlines(keepends=True)
        self.assertTrue(any(linea.startswith("### P0.20") for linea in lineas))
        # eliminar la linea completa: el conteo de reglas P0 baja a 19
        agents.write_text(
            "".join(linea for linea in lineas if not linea.startswith("### P0.20")),
            encoding="utf-8",
        )
        proc = self._verifica(repo)
        self.assertEqual(proc.returncode, 1, "el verificador no detecto la corrupcion")
        self.assertIn("[FALLO] 20 reglas P0 definidas en AGENTS.md", proc.stdout)

    def test_check_ruff_sin_ruff_emite_skip_sin_excepcion(self):
        # REQ-029: sin ruff en PATH el verificador omite el lint con [SKIP]
        # en lugar de abortar con FileNotFoundError (bug 2026-10-01).
        buf = io.StringIO()
        with mock.patch.object(vpy.shutil, "which", return_value=None):
            with mock.patch("sys.stdout", buf):
                vpy.check_ruff()  # no debe lanzar excepción
        self.assertIn("[SKIP] lint ruff", buf.getvalue())

    def test_check_ruff_con_ruff_ejecuta_lint(self):
        # REQ-029: con ruff disponible el lint se ejecuta vía check().
        with mock.patch.object(vpy.shutil, "which", return_value="/usr/bin/ruff"):
            with mock.patch.object(vpy, "run_cmd"), mock.patch.object(vpy, "check") as check_mock:
                vpy.check_ruff()
        check_mock.assert_called_once()
        self.assertIn("lint ruff", check_mock.call_args[0][0])

    def test_timing_opcional_imprime_ms_y_resumen(self):
        # REQ-030: con BETTER_TIMING=1 cada check informa ms y hay resumen.
        tiempos = []
        buf = io.StringIO()
        with mock.patch.object(vpy, "TIMING", True), mock.patch.object(vpy, "_TIEMPOS", tiempos):
            with mock.patch("sys.stdout", buf):
                vpy.check("check falso lento", lambda: True)
                vpy.print_timing_summary()
        salida = buf.getvalue()
        self.assertIn("[OK] check falso lento (", salida)
        self.assertIn("ms", salida)
        self.assertIn("TOTAL:", salida)
        self.assertEqual(len(tiempos), 1)

    def test_timing_desactivado_salida_byte_identica(self):
        # REQ-030: sin BETTER_TIMING la línea no lleva sufijo (paridad bash).
        buf = io.StringIO()
        with mock.patch.object(vpy, "TIMING", False), mock.patch.object(vpy, "_TIEMPOS", []):
            with mock.patch("sys.stdout", buf):
                vpy.check("check sin timing", lambda: True)
                vpy.print_timing_summary()
        self.assertEqual(buf.getvalue(), "  [OK] check sin timing\n")


class TestMutationCheck(unittest.TestCase):
    """REQ-015: generacion de mutantes y agregacion del chequeo."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_descripciones_mutantes(self):
        descs = mc.descripciones_mutantes("def f(a, b):\n    return a == b\n")
        self.assertEqual(len(descs), 1)
        self.assertIn("comparador", descs[0])

    def test_mutante_cambia_comparador(self):
        mutantes = mc.generar_mutantes("def f(a, b):\n    return a == b\n")
        self.assertEqual(len(mutantes), 1)
        self.assertIn("!=", mutantes[0][1])

    def test_mutante_booleano(self):
        mutantes = mc.generar_mutantes("FLAG = True\n")
        self.assertTrue(any("False" in codigo for _, codigo in mutantes))

    def test_mutante_operador_logico(self):
        mutantes = mc.generar_mutantes("def f(a, b):\n    return a and b\n")
        self.assertTrue(any(" or " in codigo for _, codigo in mutantes))

    def test_mutantes_sintacticamente_validos(self):
        source = "def f(a, b):\n    return a == b and True\n"
        for _, codigo in mc.generar_mutantes(source):
            self.assertIsNotNone(ast.parse(codigo))

    def test_medir_agrega_y_restaura(self):
        scripts = self.tmp / "scripts"
        scripts.mkdir()
        modulo = scripts / "foo.py"
        original = "def f(a, b):\n    return a == b\n"
        modulo.write_text(original, encoding="utf-8")
        resultado = mc.medir(self.tmp, "scripts/foo.py", "test_x", ejecutar=lambda desc: 0)
        self.assertEqual(resultado["total"], 1)
        self.assertEqual(resultado["mutantes_muertos"], 0)
        self.assertEqual(modulo.read_text(encoding="utf-8"), original)

    def test_medir_mutante_muerto(self):
        scripts = self.tmp / "scripts"
        scripts.mkdir()
        (scripts / "foo.py").write_text("def f(a, b):\n    return a == b\n", encoding="utf-8")
        resultado = mc.medir(self.tmp, "scripts/foo.py", "test_x", ejecutar=lambda desc: 1)
        self.assertEqual(resultado["score"], 1.0)

    def test_repo_score_sobre_umbral(self):
        # Chequeo real acotado sobre una copia temporal (no toca el repo).
        copia = mc._copia_temporal(ROOT)
        try:
            resultado = mc.medir(
                copia, "scripts/adr_validator.py",
                "test_pilares.TestADRValidator", max_mutantes=8,
            )
        finally:
            shutil.rmtree(copia, ignore_errors=True)
        self.assertGreaterEqual(resultado["score"], 0.8)

    def test_medir_batch_agrega_y_pondera(self):
        scripts = self.tmp / "scripts"
        scripts.mkdir()
        (scripts / "uno.py").write_text("def f(a, b):\n    return a == b\n", encoding="utf-8")
        (scripts / "dos.py").write_text("def g(a, b):\n    return a and b\n", encoding="utf-8")
        pares = [("scripts/uno.py", "test_x"), ("scripts/dos.py", "test_y")]
        resultado = mc.medir_batch(self.tmp, pares=pares, ejecutar=lambda desc: 1)
        self.assertEqual(resultado["total"], 2)
        self.assertEqual(resultado["mutantes_muertos"], 2)
        self.assertEqual(resultado["score"], 1.0)
        self.assertEqual(len(resultado["batch"]), 2)

    def test_medir_batch_score_parcial(self):
        scripts = self.tmp / "scripts"
        scripts.mkdir()
        (scripts / "uno.py").write_text("def f(a, b):\n    return a == b\n", encoding="utf-8")
        (scripts / "dos.py").write_text("def g(a, b):\n    return a and b\n", encoding="utf-8")
        pares = [("scripts/uno.py", "test_x"), ("scripts/dos.py", "test_y")]
        llamadas = {"n": 0}

        def ejecutar(desc):
            llamadas["n"] += 1
            return 1 if llamadas["n"] == 1 else 0

        resultado = mc.medir_batch(self.tmp, pares=pares, ejecutar=ejecutar)
        self.assertEqual(resultado["score"], 0.5)

    def test_medir_batch_sin_mutantes_score_1(self):
        scripts = self.tmp / "scripts"
        scripts.mkdir()
        (scripts / "vacio.py").write_text("x = 1\n", encoding="utf-8")
        resultado = mc.medir_batch(self.tmp, pares=[("scripts/vacio.py", "test_x")])
        self.assertEqual(resultado["total"], 0)
        self.assertEqual(resultado["score"], 1.0)

    def test_ejecutar_tests_exige_resumen_del_runner(self):
        # rc==0 sin "Ran " en stderr => la suite se interrumpio (SystemExit
        # durante el import): mutante detectado, no superviviente.
        interrumpido = subprocess.CompletedProcess([], 0, "salida", "sin resumen")
        with mock.patch.object(mc.subprocess, "run", return_value=interrumpido):
            self.assertEqual(mc._ejecutar_tests(self.tmp, "test_x", 60), 1)
        verde = subprocess.CompletedProcess([], 0, "", "\nRan 1 test in 0.001s\n\nOK")
        with mock.patch.object(mc.subprocess, "run", return_value=verde):
            self.assertEqual(mc._ejecutar_tests(self.tmp, "test_x", 60), 0)
        rojo = subprocess.CompletedProcess([], 1, "", "FAILED")
        with mock.patch.object(mc.subprocess, "run", return_value=rojo):
            self.assertEqual(mc._ejecutar_tests(self.tmp, "test_x", 60), 1)

    def test_ejecutar_tests_sin_cache_pyc(self):
        # PYTHONDONTWRITEBYTECODE evita el contagio de bytecode entre mutantes.
        verde = subprocess.CompletedProcess([], 0, "", "\nRan 1 test in 0.001s\n\nOK")
        with mock.patch.object(mc.subprocess, "run", return_value=verde) as run:
            mc._ejecutar_tests(self.tmp, "test_x", 60)
        self.assertEqual(run.call_args.kwargs["env"].get("PYTHONDONTWRITEBYTECODE"), "1")

    def test_main_batch_imprime_tabla(self):
        res = {
            "batch": [{"modulo": "scripts/x.py", "test": "t", "total": 2,
                       "mutantes_muertos": 2, "sobrevivientes": [], "score": 1.0}],
            "total": 2, "mutantes_muertos": 2, "score": 1.0,
        }
        with mock.patch.object(mc, "medir_batch", return_value=res), \
                mock.patch.object(sys, "stdout", io.StringIO()) as out:
            rc = mc.main(["--batch", "--in-place"])
        self.assertEqual(rc, 0)
        self.assertIn("Batch: 2/2", out.getvalue())

    def test_main_batch_strict_falla_bajo_umbral(self):
        res = {"batch": [], "total": 4, "mutantes_muertos": 2, "score": 0.5}
        with mock.patch.object(mc, "medir_batch", return_value=res), \
                mock.patch.object(sys, "stdout", io.StringIO()), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            rc = mc.main(["--batch", "--in-place", "--strict", "--umbral", "0.8"])
        self.assertEqual(rc, 1)

    def test_all_batch_incluye_default_y_excluye_mutation(self):
        modulos = {modulo for modulo, _ in mc.ALL_BATCH}
        self.assertTrue({modulo for modulo, _ in mc.DEFAULT_BATCH} <= modulos)
        self.assertNotIn("scripts/mutation_check.py", modulos)

    def test_main_all_usa_all_batch(self):
        res = {"batch": [], "total": 2, "mutantes_muertos": 2, "score": 1.0}
        with mock.patch.object(mc, "medir_batch", return_value=res) as mb, \
                mock.patch.object(sys, "stdout", io.StringIO()):
            rc = mc.main(["--all", "--in-place"])
        self.assertEqual(rc, 0)
        self.assertEqual(mb.call_args.args[1], mc.ALL_BATCH)


class TestHealthDashboard(unittest.TestCase):
    """REQ-024: dashboard de KPIs en docs/health.md."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        for attr, value in (
            ("HISTORY", self.tmp / "health_runs.jsonl"),
            ("HEALTH_MD", self.tmp / "health.md"),
        ):
            patcher = mock.patch.object(hd, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _reporte(self, fecha="2026-09-01", onboarding=60.0, ci=300.0, mut=0.9):
        return {
            "fecha": fecha,
            "onboarding_segundos": onboarding,
            "reqs_trazados_pct": 95.0,
            "reqs_implementados_con_refs": 19,
            "reqs_no_deprecados": 20,
            "mutation_score": mut,
            "ci_segundos": ci,
            "producto_pct": 12.5,
            "sloc_producto": 25,
            "sloc_tooling": 175,
        }

    def test_estado_segun_meta_y_direccion(self):
        self.assertEqual(hd._estado(None, 1.0, True), "n/d")
        self.assertEqual(hd._estado(0.9, 0.85, True), "OK")
        self.assertEqual(hd._estado(0.8, 0.85, True), "FUERA")
        self.assertEqual(hd._estado(500.0, 600.0, False), "OK")
        self.assertEqual(hd._estado(700.0, 600.0, False), "FUERA")

    def test_kpi_reqs_trazados_excluye_deprecados(self):
        reqs = {
            "REQ-1": {"meta": {"estado": "Implementado"}},
            "REQ-2": {"meta": {"estado": "Implementado"}},
            "REQ-3": {"meta": {"estado": "Aprobado"}},
            "REQ-4": {"meta": {"estado": "Deprecado"}},
        }
        pct, con_refs, total = hd.kpi_reqs_trazados(reqs, {"REQ-1": ["scripts/x.py"]})
        self.assertEqual((con_refs, total), (1, 3))
        self.assertAlmostEqual(pct, 100.0 / 3, places=4)

    def test_registrar_conserva_ultimos_diez(self):
        for i in range(12):
            hd.registrar(self._reporte(fecha=f"2026-09-{i + 1:02d}"))
        historial = hd.cargar_historial()
        self.assertEqual(len(historial), hd.MAX_RUNS)
        self.assertEqual(historial[0]["fecha"], "2026-09-03")
        self.assertEqual(historial[-1]["fecha"], "2026-09-12")

    def test_render_md_incluye_cinco_kpis_meta_y_tendencia(self):
        hd.registrar(self._reporte())
        md = hd.render_md(hd.cargar_historial())
        for etiqueta in ("Onboarding", "REQs trazados", "Mutation score",
                         "Tiempo CI", "Coste mantenimiento"):
            self.assertIn(etiqueta, md)
        self.assertIn("Meta", md)
        self.assertIn("Tendencia (ultimos 10 runs)", md)
        self.assertIn("n/d", hd.render_md([{"fecha": "s/f"}]))

    def test_main_escribe_dashboard_e_historial(self):
        with mock.patch.object(hd, "kpi_mutation", return_value=0.9), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(
                hd.main(["--onboarding-seconds", "60", "--ci-seconds", "300"]), 0
            )
        self.assertTrue(hd.HEALTH_MD.exists())
        self.assertIn("REQs trazados", hd.HEALTH_MD.read_text(encoding="utf-8"))
        self.assertEqual(len(hd.cargar_historial()), 1)
        self.assertIn("Dashboard generado", out.getvalue())

    def test_main_json(self):
        with mock.patch.object(hd, "kpi_mutation", return_value=0.9), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(
                hd.main(["--json", "--mutation-score", "0.95", "--fecha", "2026-09-02"]),
                0,
            )
        reporte = json.loads(out.getvalue())
        self.assertEqual(reporte["mutation_score"], 0.95)
        self.assertEqual(reporte["fecha"], "2026-09-02")
        self.assertIn("reqs_trazados_pct", reporte)

    def test_main_usa_kpi_mutation_cuando_no_se_pasa(self):
        with mock.patch.object(hd, "kpi_mutation", return_value=0.77) as km, \
             mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(hd.main([]), 0)
        km.assert_called_once()
        self.assertEqual(hd.cargar_historial()[-1]["mutation_score"], 0.77)

    def test_kpi_producto_con_sloc(self):
        (self.tmp / "scripts").mkdir()
        (self.tmp / "demo").mkdir()
        (self.tmp / "scripts" / "tool.py").write_text(
            "# comentario\nx = 1\n\n", encoding="utf-8"
        )
        (self.tmp / "demo" / "app.py").write_text(
            "y = 2\n# nota\nz = 3\n", encoding="utf-8"
        )
        pct, prod, tool = hd.kpi_producto(self.tmp)
        self.assertEqual((prod, tool), (2, 1))
        self.assertAlmostEqual(pct, 200.0 / 3, places=4)


class TestGitFsck(unittest.TestCase):
    """LSN-062: el check de fsck tolera blobs inalcanzables (residuo de
    re-stage) pero falla con commits/trees huerfanos."""

    def _repo(self, tmp: str) -> Path:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "dummy@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "dummy"], cwd=repo, check=True)
        (repo / "a.txt").write_text("hola", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-qm", "c"], cwd=repo, check=True)
        return repo

    def test_blob_innalcanzable_es_tolerado(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp)
            subprocess.run(
                ["git", "hash-object", "-w", "--stdin"], cwd=repo,
                input="contenido huerfano", text=True, check=True, capture_output=True,
            )
            self.assertTrue(vpy._check_git_fsck(repo))

    def test_commit_huerfano_es_fallo(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self._repo(tmp)
            tree = subprocess.run(
                ["git", "write-tree"], cwd=repo, capture_output=True, text=True, check=True,
            ).stdout.strip()
            env = {
                **os.environ,
                "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "dummy@example.com",
                "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "dummy@example.com",
            }
            subprocess.run(
                ["git", "commit-tree", tree, "-m", "huerfano"], cwd=repo,
                check=True, capture_output=True, env=env,
            )
            self.assertFalse(vpy._check_git_fsck(repo))


if __name__ == "__main__":
    unittest.main()
