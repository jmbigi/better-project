#!/usr/bin/env python3
"""Tests de la cadena de suministro y analisis de comandos: SBOM, advisories y
analyze_shell (REQ-020, P0.8).
"""

import io
import json
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import analyze_shell as ash  # noqa: E402
import audit_advisories as aadm  # noqa: E402
import generate_sbom as gsb  # noqa: E402

class TestGenerateSbom(unittest.TestCase):
    """REQ-020: check_sbom valida sbom/ o verifica regeneracion real con syft."""

    def test_check_valida_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "sbom.cyclonedx.json").write_text('{"a": 1}', encoding="utf-8")
            self.assertTrue(gsb.check_sbom(d))

    def test_check_json_invalido_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "sbom.cyclonedx.json").write_text("no-json", encoding="utf-8")
            self.assertFalse(gsb.check_sbom(d))

    def test_check_sin_sbom_sin_syft_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(gsb, "check_syft", return_value=None):
                self.assertFalse(gsb.check_sbom(Path(tmp) / "no_existe"))

    def test_check_sin_sbom_regenera_con_syft(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(gsb, "check_syft", return_value="/fake/syft"), \
                    mock.patch.object(gsb, "generate_sbom", return_value=True) as gen:
                self.assertTrue(gsb.check_sbom(Path(tmp) / "no_existe"))
                gen.assert_called_once()

    def test_check_dir_vacio_con_syft_regenera(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(gsb, "check_syft", return_value="/fake/syft"), \
                    mock.patch.object(gsb, "generate_sbom", return_value=False) as gen:
                self.assertFalse(gsb.check_sbom(Path(tmp)))
                gen.assert_called_once()

    def test_normalizar_sbom_neutraliza_volatiles(self):
        cd = {"serialNumber": "urn:uuid:aaaa",
              "metadata": {"timestamp": "2026-01-01T00:00:00Z", "x": 1}}
        out = gsb.normalizar_sbom(cd, "cyclonedx")
        self.assertEqual(out["serialNumber"], gsb._SERIAL_NEUTRO)
        self.assertEqual(out["metadata"]["timestamp"], gsb._FECHA_NEUTRA)
        self.assertEqual(out["metadata"]["x"], 1)
        spdx = {"documentNamespace": "https://anchore.com/syft/dir/abc",
                "creationInfo": {"created": "algo", "creators": ["Tool: syft"]}}
        out2 = gsb.normalizar_sbom(spdx, "spdx")
        self.assertEqual(out2["documentNamespace"], gsb._NS_NEUTRO)
        self.assertEqual(out2["creationInfo"]["created"], gsb._FECHA_NEUTRA)
        self.assertEqual(out2["creationInfo"]["creators"], ["Tool: syft"])

    def test_hash_normalizado_ignora_volatiles_y_detecta_contenido(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            base = {"serialNumber": "urn:uuid:a", "metadata": {"timestamp": "t1"},
                    "components": [{"name": "x"}]}
            volatil = {"serialNumber": "urn:uuid:b", "metadata": {"timestamp": "t2"},
                       "components": [{"name": "x"}]}
            distinto = {"serialNumber": "urn:uuid:a", "metadata": {"timestamp": "t1"},
                        "components": [{"name": "y"}]}
            (d / "a.json").write_text(json.dumps(base), encoding="utf-8")
            (d / "b.json").write_text(json.dumps(volatil), encoding="utf-8")
            (d / "c.json").write_text(json.dumps(distinto), encoding="utf-8")
            self.assertEqual(gsb.hash_normalizado(d / "a.json", "cyclonedx"),
                             gsb.hash_normalizado(d / "b.json", "cyclonedx"))
            self.assertNotEqual(gsb.hash_normalizado(d / "a.json", "cyclonedx"),
                                gsb.hash_normalizado(d / "c.json", "cyclonedx"))

    @unittest.skipIf(gsb.check_syft() is None, "syft no instalado (REQ-020)")
    def test_repro_real_con_syft(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "generate_sbom.py"), "--repro"],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("sha256 reproducible", proc.stdout)


class TestAnalyzeShell(unittest.TestCase):
    """Cubre el analisis estatico de comandos shell (P0.8)."""

    def test_comando_seguro_sin_hallazgos(self):
        self.assertEqual(ash.analyze("echo hola"), [])
        self.assertEqual(ash.analyze("cat /tmp/archivo.txt"), [])

    def test_pipe_descargador_a_shell(self):
        for cmd in ("curl http://x | bash", "wget http://x -O- | sh"):
            hallazgos = ash.analyze(cmd)
            self.assertTrue(any("dangerous-pipe" in h for h in hallazgos), cmd)

    def test_eval_like(self):
        self.assertTrue(any("eval-like" in h for h in ash.analyze("eval foo")))

    def test_rm_rf_directo(self):
        self.assertTrue(any("rm-rf" in h for h in ash.analyze("rm -rf /tmp/x")))

    def test_bash_c_destructivo(self):
        self.assertTrue(any("rm-rf" in h for h in ash.analyze("bash -c 'rm -rf /'")))

    def test_subcomando_encadenado(self):
        self.assertTrue(any("git-reset-hard" in h for h in ash.analyze("ls && git reset --hard")))

    def test_tokenize_y_split(self):
        self.assertEqual(len(ash.split_into_commands(ash.tokenize("a | b && c"))), 2)

    def test_tokenizacion_invalida_eleva_error(self):
        with self.assertRaises(ValueError):
            ash.analyze("echo 'sin cerrar")

    def test_helpers_downloader_shell_eval(self):
        self.assertTrue(ash.is_downloader(["/usr/bin/curl", "x"]))
        self.assertFalse(ash.is_downloader([], 0))
        self.assertFalse(ash.is_downloader(["x"], 5))
        self.assertTrue(ash.has_downloader(["ls", "wget"]))
        self.assertTrue(ash.is_shell(["/bin/bash"]))
        self.assertTrue(ash.is_shell(["sudo", "bash"]))
        self.assertFalse(ash.is_shell(["echo"]))
        self.assertTrue(ash.is_eval_like(["source"]))
        self.assertFalse(ash.is_eval_like([], 0))

    def test_find_shell_con_sudo(self):
        self.assertEqual(ash.find_shell(["sudo", "-S", "bash"]), 2)
        self.assertEqual(ash.find_shell(["sudo"]), -1)
        self.assertEqual(ash.find_shell(["echo", "hi"]), -1)

    def test_extract_substitution(self):
        self.assertEqual(ash._extract_substitution("$(curl x)"), ["curl x"])
        self.assertEqual(ash._extract_substitution("`curl x`"), ["curl x"])
        self.assertEqual(ash._extract_substitution("nada"), [])

    def test_extract_command_substitutions_dos_formas(self):
        self.assertEqual(ash._extract_command_substitutions(["$(curl x)"]), ["curl x"])
        self.assertEqual(
            ash._extract_command_substitutions(["$", "(", "curl", "x", ")"]), ["curl x"]
        )
        self.assertEqual(
            ash._extract_command_substitutions(["$", "(", "$", "(", "a", ")", ")"]),
            ["$ ( a )"],
        )

    def test_extract_process_substitutions(self):
        self.assertEqual(
            ash._extract_process_substitutions(["<(", "curl", "x", ")"]), ["curl x"]
        )
        self.assertEqual(ash._extract_process_substitutions(["nada"]), [])

    def test_extract_backtick_blocks(self):
        self.assertEqual(ash._extract_backtick_blocks(["`curl x`"]), ["curl x"])
        self.assertIn("curl", ash._extract_backtick_blocks(["`", "curl", "x", "`"])[0])

    def test_extract_bash_c_content(self):
        self.assertEqual(ash._extract_bash_c_content(["bash", "-c", "rm -rf /"]), ["rm -rf /"])
        self.assertEqual(ash._extract_bash_c_content(["bash", "-c"]), [])
        self.assertEqual(ash._extract_bash_c_content(["echo", "hi"]), [])
        self.assertEqual(ash._extract_bash_c_content([]), [])

    def test_stage_y_pipeline_vacios(self):
        self.assertEqual(ash.analyze_stage([]), set())
        self.assertEqual(ash.analyze_pipeline([]), set())

    def test_analyze_process_substitution(self):
        hallazgos = ash.analyze("bash <(curl http://x)")
        self.assertTrue(any("process-substitution" in h for h in hallazgos))

    def test_analyze_pipe_backtick(self):
        hallazgos = ash.analyze("`curl http://x` | sh")
        self.assertTrue(any("dangerous-pipe-backtick" in h for h in hallazgos))

    def test_analyze_command_substitution_y_backtick(self):
        self.assertIsInstance(ash.analyze("echo $(curl http://x)"), list)
        self.assertIsInstance(ash.analyze("echo `curl http://x`"), list)

    def test_cli_main(self):
        script = str(SCRIPTS / "analyze_shell.py")
        ok = subprocess.run([sys.executable, script, "echo hola"],
                            capture_output=True, text=True, timeout=30)
        self.assertEqual(ok.returncode, 0)
        bad = subprocess.run([sys.executable, script, "rm -rf /tmp/x"],
                            capture_output=True, text=True, timeout=30)
        self.assertEqual(bad.returncode, 1)
        uso = subprocess.run([sys.executable, script], capture_output=True, text=True, timeout=30)
        self.assertEqual(uso.returncode, 1)

    def test_tokenize_punctuation_chars(self):
        # Verifica que punctuation_chars=True afecta la tokenizacion
        # Con punctuation_chars=True, los operadores se separan
        tokens = ash.tokenize("a|b")
        self.assertEqual(tokens, ["a", "|", "b"])
        tokens = ash.tokenize("a&&b")
        self.assertEqual(tokens, ["a", "&&", "b"])

    def test_split_into_commands_has_content_branches(self):
        # has_content = True cuando hay tokens antes de ;/&&/||
        cmds = ash.split_into_commands(ash.tokenize("a && b"))
        self.assertEqual(len(cmds), 2)
        self.assertEqual(cmds[0], [["a"]])
        self.assertEqual(cmds[1], [["b"]])

        # has_content = False al inicio y despues de ;
        cmds = ash.split_into_commands(ash.tokenize("; a"))
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0], [["a"]])

        # Pipeline: has_content = True al ver |
        cmds = ash.split_into_commands(ash.tokenize("a | b"))
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0], [["a"], ["b"]])

        # Comando vacio al final
        cmds = ash.split_into_commands(ash.tokenize("a ;"))
        self.assertEqual(len(cmds), 1)
        self.assertEqual(cmds[0], [["a"]])

    def test_find_shell_sudo_comparison(self):
        # _basename(tokens[i]) == SUDO en linea 130
        self.assertEqual(ash.find_shell(["sudo", "bash"]), 1)
        self.assertEqual(ash.find_shell(["/usr/bin/sudo", "bash"]), 1)
        self.assertEqual(ash.find_shell(["sudo", "-S", "bash"]), 2)
        self.assertEqual(ash.find_shell(["sudo", "-u", "user", "bash"]), 3)
        # sudo sin shell despues
        self.assertEqual(ash.find_shell(["sudo"]), -1)
        self.assertEqual(ash.find_shell(["sudo", "echo"]), -1)

    def test_basename_edge_cases(self):
        # _basename maneja comillas y rutas
        self.assertEqual(ash._basename("'bash'"), "bash")
        self.assertEqual(ash._basename('"bash"'), "bash")
        self.assertEqual(ash._basename("/usr/bin/bash"), "bash")
        self.assertEqual(ash._basename("bash"), "bash")
        self.assertEqual(ash._basename("'sudo'"), "sudo")

    def test_is_downloader_edge_cases(self):
        # is_downloader con index fuera de rango
        self.assertFalse(ash.is_downloader([], 0))
        self.assertFalse(ash.is_downloader(["curl"], 5))
        # is_downloader con ruta completa
        self.assertTrue(ash.is_downloader(["/usr/bin/curl", "x"]))
        self.assertTrue(ash.is_downloader(["/usr/bin/wget", "x"]))

    def test_has_downloader_edge_cases(self):
        self.assertFalse(ash.has_downloader([]))
        self.assertTrue(ash.has_downloader(["ls", "curl"]))
        self.assertTrue(ash.has_downloader(["wget", "x"]))

    def test_is_shell_edge_cases(self):
        self.assertFalse(ash.is_shell([], 0))
        self.assertFalse(ash.is_shell(["echo"], 0))
        self.assertTrue(ash.is_shell(["bash"], 0))
        self.assertTrue(ash.is_shell(["/bin/bash"], 0))
        self.assertTrue(ash.is_shell(["sudo", "bash"], 0))
        self.assertFalse(ash.is_shell(["sudo", "echo"], 0))

    def test_is_eval_like_edge_cases(self):
        self.assertFalse(ash.is_eval_like([], 0))
        self.assertFalse(ash.is_eval_like(["echo"], 0))
        self.assertTrue(ash.is_eval_like(["eval"], 0))
        self.assertTrue(ash.is_eval_like(["exec"], 0))
        self.assertTrue(ash.is_eval_like(["source"], 0))
        self.assertTrue(ash.is_eval_like(["."], 0))

    def test_extract_command_substitutions_nested(self):
        # Command substitution anidada
        result = ash._extract_command_substitutions(["$", "(", "$", "(", "a", ")", ")", "b"])
        self.assertEqual(result, ["$ ( a )"])

    def test_extract_process_substitutions_nested(self):
        # Process substitution anidada
        result = ash._extract_process_substitutions(["<(", "<(", "a", ")", ")", "b"])
        self.assertEqual(result, ["<( a )"])

    def test_extract_backtick_blocks_multiple(self):
        # Multiples bloques backtick
        result = ash._extract_backtick_blocks(["`a`", "`b`"])
        self.assertEqual(len(result), 2)
        self.assertIn("a", result[0])
        self.assertIn("b", result[1])

    def test_extract_bash_c_content_edge_cases(self):
        # bash -c con multiples argumentos
        self.assertEqual(ash._extract_bash_c_content(["bash", "-c", "echo hi", "extra"]), ["echo hi"])
        # sh -c
        self.assertEqual(ash._extract_bash_c_content(["sh", "-c", "ls"]), ["ls"])
        # zsh -c
        self.assertEqual(ash._extract_bash_c_content(["zsh", "-c", "pwd"]), ["pwd"])

    def test_tokenize_respeta_comillas_posix(self):
        # posix=True: las comillas agrupan y no quedan en el token.
        self.assertEqual(ash.tokenize('cat "a b"'), ["cat", "a b"])

    def test_split_into_commands_pipe_final(self):
        # Un pipe final deja una etapa vacia y el comando sigue contando.
        self.assertEqual(len(ash.split_into_commands(ash.tokenize("ls |"))), 1)

    def test_is_shell_y_eval_index_fuera_de_rango(self):
        self.assertFalse(ash.is_shell(["bash"], index=9))
        self.assertFalse(ash.is_eval_like(["eval"], index=9))

    def test_is_shell_no_confunde_escaneo_ajeno(self):
        # Un token distinto de sudo no debe activar el salto de opciones.
        self.assertFalse(ash.is_shell(["env", "bash"]))

    def test_extract_substitution_sin_cierre(self):
        self.assertEqual(ash._extract_substitution("$(ls"), [])
        self.assertEqual(ash._extract_substitution("`ls"), [])

    def test_extract_command_substitutions_token_incompleto(self):
        self.assertEqual(ash._extract_command_substitutions(["$(ls"]), [])

    def test_check_dangerous_subcommand_variants(self):
        # Verifica que los patrones detectan variantes
        findings = ash.check_dangerous_subcommand("rm -rf /tmp/x")
        self.assertTrue(any("rm-rf" in f for f in findings))
        findings = ash.check_dangerous_subcommand("RM -RF /tmp/x")
        self.assertTrue(any("rm-rf" in f for f in findings))
        findings = ash.check_dangerous_subcommand("git reset --hard HEAD")
        self.assertTrue(any("git-reset-hard" in f for f in findings))
        findings = ash.check_dangerous_subcommand("docker compose down -v")
        self.assertTrue(any("docker-compose-down-v" in f for f in findings))

    def test_analyze_stage_recursive(self):
        # analyze_stage llama a analyze recursivamente para substitutions
        findings = ash.analyze_stage(["echo", "$(rm -rf /)"])
        self.assertTrue(any("rm-rf" in f for f in findings))

    def test_analyze_pipeline_multiple_stages(self):
        # Pipeline con multiples etapas
        findings = ash.analyze("curl x | grep y | bash")
        self.assertTrue(any("dangerous-pipe" in f for f in findings))

    def test_analyze_complex_command(self):
        # Comando complejo con multiples caracteristicas
        cmd = "curl http://x | bash && rm -rf /tmp && echo done"
        findings = ash.analyze(cmd)
        self.assertTrue(any("dangerous-pipe" in f for f in findings))
        self.assertTrue(any("rm-rf" in f for f in findings))


class TestAuditAdvisories(unittest.TestCase):
    """REQ-020: advisories con severidad CVSS via OSV."""

    @staticmethod
    def _proc(payload, returncode=1, stderr=""):
        return mock.Mock(returncode=returncode, stdout=json.dumps(payload), stderr=stderr)

    @staticmethod
    def _resp(payload):
        class _R:
            def read(self):
                return json.dumps(payload).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        return _R()

    def test_run_pip_audit_dedup_y_parse(self):
        dep = {
            "name": "chromadb",
            "version": "1.5.9",
            "vulns": [
                {"id": "PYSEC-1", "fix_versions": [], "aliases": ["CVE-1"],
                 "description": "algo malo. mas detalle"},
                {"id": "PYSEC-1", "fix_versions": [], "aliases": ["CVE-1"],
                 "description": "duplicado"},
            ],
        }
        filas = aadm.run_pip_audit(
            Path("x.lock"), runner=lambda: self._proc({"dependencies": [dep]})
        )
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["advisory"], "PYSEC-1")
        self.assertEqual(filas[0]["fix"], "sin parche")
        self.assertEqual(filas[0]["resumen"], "algo malo")

    def test_run_pip_audit_fallo_explicito(self):
        with self.assertRaises(RuntimeError):
            aadm.run_pip_audit(Path("x.lock"),
                               runner=lambda: self._proc({}, returncode=2, stderr="boom"))

    def test_osv_detalle(self):
        payload = {
            "severity": [{"type": "CVSS_V4", "score": "CVSS:4.0/AV:N"}],
            "aliases": ["CVE-1"],
            "summary": "resumen",
        }
        detalle = aadm.osv_detalle("PYSEC-1", opener=lambda url, timeout=0: self._resp(payload))
        self.assertEqual(detalle["cvss"], "CVSS:4.0/AV:N")
        self.assertEqual(detalle["aliases"], ["CVE-1"])

    def test_osv_detalle_error_red(self):
        def opener(url, timeout=0):
            raise urllib.error.URLError("sin red")
        with self.assertRaises(RuntimeError):
            aadm.osv_detalle("PYSEC-1", opener=opener)

    def test_enriquecer_offline(self):
        filas = [{"advisory": "PYSEC-1", "paquete": "p", "version": "1",
                  "fix": "sin parche", "aliases": [], "resumen": "r"}]
        aadm.enriquecer(filas, offline=True)
        self.assertEqual(filas[0]["cvss"], "(offline)")

    def test_render_markdown(self):
        filas = [{"advisory": "A", "paquete": "p", "version": "1", "fix": "sin parche",
                  "cvss": "CVSS:4.0/X", "aliases": ["CVE-1"], "resumen": "r"}]
        md = aadm.render_markdown(filas)
        self.assertIn("| Advisory |", md)
        self.assertIn("CVE-1", md)

    def test_main_offline(self):
        filas = [{"advisory": "A", "paquete": "p", "version": "1", "fix": "sin parche",
                  "aliases": [], "resumen": "r"}]
        with mock.patch.object(aadm, "run_pip_audit", return_value=filas), \
                mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(aadm.main(["--offline"]), 0)
        self.assertIn("(offline)", out.getvalue())

    def test_main_error_controlado(self):
        with mock.patch.object(aadm, "run_pip_audit", side_effect=RuntimeError("no pip-audit")), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(aadm.main([]), 1)

    def test_run_pip_audit_sin_pip_audit_instalado(self):
        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as cm:
                aadm.run_pip_audit(Path("x.lock"))
            self.assertIn("pip-audit no esta instalado", str(cm.exception))

    def test_run_pip_audit_sin_vulnerabilidades(self):
        filas = aadm.run_pip_audit(
            Path("x.lock"), runner=lambda: self._proc({"dependencies": []}, returncode=0)
        )
        self.assertEqual(filas, [])

    def test_osv_detalle_sin_severidad(self):
        payload = {"aliases": ["CVE-1"], "summary": "resumen"}
        detalle = aadm.osv_detalle("PYSEC-1", opener=lambda url, timeout=0: self._resp(payload))
        self.assertEqual(detalle["cvss"], "")
        self.assertEqual(detalle["aliases"], ["CVE-1"])

    def test_osv_detalle_severidad_vacia(self):
        payload = {"severity": [], "aliases": ["CVE-1"], "summary": "resumen"}
        detalle = aadm.osv_detalle("PYSEC-1", opener=lambda url, timeout=0: self._resp(payload))
        self.assertEqual(detalle["cvss"], "")

    def test_enriquecer_online(self):
        filas = [{"advisory": "PYSEC-1", "paquete": "p", "version": "1",
                  "fix": "sin parche", "aliases": [], "resumen": "r"}]
        payload = {"severity": [{"score": "CVSS:4.0/AV:N"}], "aliases": ["CVE-2"], "summary": "nuevo"}
        aadm.enriquecer(filas, offline=False, opener=lambda url, timeout=0: self._resp(payload))
        self.assertEqual(filas[0]["cvss"], "CVSS:4.0/AV:N")
        self.assertEqual(filas[0]["aliases"], ["CVE-2"])
        self.assertEqual(filas[0]["resumen"], "nuevo")

    def test_main_online(self):
        filas = [{"advisory": "A", "paquete": "p", "version": "1", "fix": "sin parche",
                  "aliases": [], "resumen": "r"}]
        payload = {"severity": [{"score": "CVSS:4.0/AV:N"}], "aliases": ["CVE-1"], "summary": "resumen"}
        with mock.patch.object(aadm, "run_pip_audit", return_value=filas), \
             mock.patch("urllib.request.urlopen", lambda url, timeout=0: self._resp(payload)), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(aadm.main([]), 0)
        self.assertIn("CVSS:4.0/AV:N", out.getvalue())

    def test_main_json(self):
        filas = [{"advisory": "A", "paquete": "p", "version": "1", "fix": "sin parche",
                  "aliases": ["CVE-1"], "resumen": "r", "cvss": "CVSS:4.0/X"}]
        with mock.patch.object(aadm, "run_pip_audit", return_value=filas), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(aadm.main(["--json", "--offline"]), 0)
        output = json.loads(out.getvalue())
        self.assertEqual(output[0]["advisory"], "A")
        self.assertEqual(output[0]["cvss"], "(offline)")

    def test_run_pip_audit_busca_en_path(self):
        # Con pip_audit_path=None debe resolver la herramienta con shutil.which.
        falso = mock.MagicMock(returncode=0, stdout='{"dependencies": []}', stderr="")
        with mock.patch.object(aadm.shutil, "which", return_value="/fake/pip-audit"), \
                mock.patch.object(aadm.subprocess, "run", return_value=falso) as run:
            filas = aadm.run_pip_audit(Path("r.lock"))
        self.assertEqual(filas, [])
        self.assertEqual(run.call_args.args[0][0], "/fake/pip-audit")

    def test_run_pip_audit_sin_herramienta_falla(self):
        with mock.patch.object(aadm.shutil, "which", return_value=None):
            with self.assertRaises(RuntimeError):
                aadm.run_pip_audit(Path("r.lock"))

    def test_runner_usa_check_false_y_captura(self):
        capturas = {}

        def fake_run(cmd, **kwargs):
            capturas.update(kwargs)
            return mock.MagicMock(returncode=0, stdout="{}", stderr="")

        with mock.patch.object(aadm.shutil, "which", return_value="/fake"), \
                mock.patch.object(aadm.subprocess, "run", fake_run):
            aadm.run_pip_audit(Path("r.lock"))
        self.assertEqual(capturas.get("check"), False)
        self.assertEqual(capturas.get("capture_output"), True)
        self.assertEqual(capturas.get("text"), True)

    def test_run_pip_audit_incluye_stderr_en_error(self):
        fallo = mock.MagicMock(returncode=2, stdout="", stderr="detalle del error")
        with self.assertRaises(RuntimeError) as ctx:
            aadm.run_pip_audit(Path("r.lock"), runner=lambda: fallo)
        self.assertIn("detalle del error", str(ctx.exception))

    def test_run_pip_audit_parsea_stdout(self):
        payload = json.dumps({"dependencies": [
            {"name": "p", "version": "1",
             "vulns": [{"id": "X", "fix_versions": [], "aliases": ["A"]}]},
        ]})
        falso = mock.MagicMock(returncode=1, stdout=payload, stderr="")
        filas = aadm.run_pip_audit(Path("r.lock"), runner=lambda: falso)
        self.assertEqual(filas[0]["advisory"], "X")
        self.assertEqual(filas[0]["fix"], "sin parche")

    def test_enriquecer_por_defecto_online(self):
        filas = [{"advisory": "PYSEC-1", "paquete": "p", "version": "1", "fix": "sin parche",
                  "aliases": [], "resumen": "r"}]
        payload = {"severity": [{"score": "CVSS:X"}], "aliases": [], "summary": "s"}
        aadm.enriquecer(filas, opener=lambda url, timeout=0: self._resp(payload))
        self.assertEqual(filas[0]["cvss"], "CVSS:X")

    def test_main_json_conserva_acentos(self):
        filas = [{"advisory": "A", "paquete": "p", "version": "1", "fix": "sin parche",
                  "aliases": [], "resumen": "decisión crítica"}]
        with mock.patch.object(aadm, "run_pip_audit", return_value=filas), \
                mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(aadm.main(["--json", "--offline"]), 0)
        self.assertIn("decisión", out.getvalue())


if __name__ == "__main__":
    unittest.main()
