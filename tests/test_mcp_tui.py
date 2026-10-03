#!/usr/bin/env python3
"""Tests del servidor MCP y la TUI (REQ-004/REQ-006/REQ-007).
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import index_knowledge as ik  # noqa: E402
import mcp_server as mcp  # noqa: E402
import tui  # noqa: E402

class TestMCPServer(unittest.TestCase):
    def test_next_lesson_id(self):
        self.assertEqual(mcp._next_lesson_id({"LSN-001", "LSN-003"}), "LSN-004")
        self.assertEqual(mcp._next_lesson_id(set()), "LSN-001")
        self.assertEqual(mcp._next_lesson_id({"basura"}), "LSN-001")

    def test_create_lesson_append_secuencial(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_dir = mcp.LESSONS_DIR
            mcp.LESSONS_DIR = Path(tmp)
            try:
                content, is_error = mcp.handle_call(
                    "create_lesson", {"problema": "p", "recomendacion": "r"}
                )
                self.assertFalse(is_error)
                content2, _ = mcp.handle_call(
                    "create_lesson", {"problema": "p2", "recomendacion": "r2"}
                )
                archivo = Path(tmp) / "2026.yaml"
                texto = archivo.read_text(encoding="utf-8")
                self.assertEqual(texto.count("- id: LSN-"), 2)
                self.assertIn("LSN-001", content[0]["text"])
                self.assertIn("LSN-002", content2[0]["text"])
            finally:
                mcp.LESSONS_DIR = old_dir

    def test_tool_desconocida_es_error(self):
        content, is_error = mcp.handle_call("no_existe", {})
        self.assertTrue(is_error)

    def test_validate_requirements_ok(self):
        content, is_error = mcp.handle_call("validate_requirements", {})
        self.assertFalse(is_error)
        report = json.loads(content[0]["text"])
        self.assertGreaterEqual(report["requisitos"], 6)
        self.assertEqual(report["estado"], "OK")

    def test_query_demasiado_larga_es_error(self):
        content, is_error = mcp.handle_call("search_knowledge", {"query": "x" * 501})
        self.assertTrue(is_error)
        self.assertIn("limite", content[0]["text"])

    def test_query_en_el_limite_pasa_validacion(self):
        self.assertIsNone(mcp._validate_limits("search_knowledge", {"query": "x" * 500}))

    def test_k_fuera_de_rango_es_error(self):
        for k in (0, 21, "grande"):
            content, is_error = mcp.handle_call("search_knowledge", {"query": "pilar", "k": k})
            self.assertTrue(is_error, k)

    def test_campo_largo_en_create_lesson_es_error(self):
        content, is_error = mcp.handle_call(
            "create_lesson", {"problema": "p" * 2001, "recomendacion": "r"}
        )
        self.assertTrue(is_error)
        self.assertIn("problema", content[0]["text"])

    def test_audit_log_registra_llamadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_log = mcp.AUDIT_LOG
            mcp.AUDIT_LOG = Path(tmp) / "audit.jsonl"
            try:
                mcp.handle_call("read_requirement", {"id": "REQ-001"})
                mcp.handle_call("no_existe", {})
                lineas = mcp.AUDIT_LOG.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(lineas), 2)
                ok_entry = json.loads(lineas[0])
                fail_entry = json.loads(lineas[1])
                self.assertTrue(ok_entry["ok"])
                self.assertFalse(fail_entry["ok"])
                self.assertEqual(ok_entry["tool"], "read_requirement")
                self.assertEqual(fail_entry["tool"], "no_existe")
                # solo tamanos de argumentos, nunca contenidos (P0.9)
                self.assertEqual(ok_entry["args"], {"id": 7})
                for campo in ("ts", "ms"):
                    self.assertIn(campo, ok_entry)
            finally:
                mcp.AUDIT_LOG = old_log

    def test_stdio_end_to_end(self):
        """Protocolo MCP real por stdio: initialize + tools/call + limite."""
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ}
            mensajes = [
                {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                 "params": {"name": "read_requirement", "arguments": {"id": "REQ-001"}}},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "search_knowledge",
                            "arguments": {"query": "x" * 501}}},
            ]
            entrada = "\n".join(json.dumps(m) for m in mensajes) + "\n"
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "mcp_server.py")],
                input=entrada, capture_output=True, text=True, timeout=30,
                cwd=tmp, env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            respuestas = {
                m["id"]: m for m in
                (json.loads(linea) for linea in proc.stdout.splitlines() if linea.strip())
            }
            self.assertEqual(respuestas[1]["result"]["serverInfo"]["name"], "better-project")
            self.assertFalse(respuestas[2]["result"]["isError"])
            self.assertIn("REQ-001", respuestas[2]["result"]["content"][0]["text"])
            # el limite de REQ-007 se aplica tambien por stdio
            self.assertTrue(respuestas[3]["result"]["isError"])
            self.assertIn("limite", respuestas[3]["result"]["content"][0]["text"])
            # la auditoria se escribio (en .docs/.storage del repo real)
            self.assertTrue(mcp.AUDIT_LOG.exists())

    def test_search_knowledge_fallback_sin_indice(self):
        with tempfile.TemporaryDirectory() as tmp:
            know = Path(tmp)
            (know / "a.md").write_text(
                "## Timeout\nservidor timeout conexiones pool timeout reintentos\n"
            )
            old_index, old_know, old_root = mcp.JSON_INDEX, mcp.KNOWLEDGE_DIR, mcp.ROOT
            mcp.JSON_INDEX = Path(tmp) / "no-index.json"
            mcp.KNOWLEDGE_DIR = know
            mcp.ROOT = know
            try:
                content = mcp.search_knowledge({"query": "timeout"})
                self.assertIn("timeout", content[0]["text"])
            finally:
                mcp.JSON_INDEX, mcp.KNOWLEDGE_DIR, mcp.ROOT = old_index, old_know, old_root

    def test_search_knowledge_sin_resultados(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_index, old_know = mcp.JSON_INDEX, mcp.KNOWLEDGE_DIR
            mcp.JSON_INDEX = Path(tmp) / "no-index.json"
            mcp.KNOWLEDGE_DIR = Path(tmp) / "vacio"
            try:
                content = mcp.search_knowledge({"query": "zzz"})
                self.assertIn("sin resultados", content[0]["text"])
            finally:
                mcp.JSON_INDEX, mcp.KNOWLEDGE_DIR = old_index, old_know

    def test_read_requirement_id_invalido_y_ausente(self):
        self.assertIn("REQ-XXX", mcp.read_requirement({"id": "nope"})[0]["text"])
        self.assertIn("no existe", mcp.read_requirement({"id": "REQ-999"})[0]["text"])

    def test_validate_requirements_con_errores(self):
        doc = mcp.doc_validator
        with mock.patch.object(doc, "collect_req_files", return_value={}), \
                mock.patch.object(doc, "collect_code_refs", return_value={}), \
                mock.patch.object(doc, "analizar",
                                  side_effect=lambda r, f: doc.errors.append("boom")):
            doc.errors.clear()
            report = json.loads(mcp.validate_requirements()[0]["text"])
        self.assertEqual(report["estado"], "con errores")
        self.assertIn("boom", report["errores"])

    def test_validate_requirements_con_advertencias(self):
        doc = mcp.doc_validator
        with mock.patch.object(doc, "collect_req_files", return_value={}), \
                mock.patch.object(doc, "collect_code_refs", return_value={}), \
                mock.patch.object(doc, "analizar",
                                  side_effect=lambda r, f: doc.warnings.append("w")):
            doc.errors.clear()
            doc.warnings.clear()
            report = json.loads(mcp.validate_requirements()[0]["text"])
        self.assertEqual(report["estado"], "con advertencias")
        self.assertIn("w", report["advertencias"])

    def test_run_verification_lanza_en_segundo_plano(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_log, old_pid = mcp.VERIFICATION_LOG, mcp.VERIFICATION_PID
            mcp.VERIFICATION_LOG = Path(tmp) / "verificacion.log"
            mcp.VERIFICATION_PID = Path(tmp) / "verificacion.pid"
            fake = mock.Mock(pid=4242)
            try:
                with mock.patch.object(mcp.subprocess, "Popen", return_value=fake) as popen:
                    content, ok = mcp.run_verification()
                self.assertTrue(ok)
                payload = json.loads(content[0]["text"])
                self.assertEqual(payload["estado"], "en curso")
                self.assertEqual(payload["pid"], 4242)
                self.assertEqual(mcp.VERIFICATION_PID.read_text(encoding="utf-8"), "4242")
                args = popen.call_args.args[0]
                self.assertEqual(args[0], "bash")
                self.assertTrue(args[1].endswith("verificar-proyecto.sh"))
                kwargs = popen.call_args.kwargs
                self.assertEqual(kwargs["cwd"], mcp.ROOT)
                self.assertIs(kwargs["stderr"], mcp.subprocess.STDOUT)
                self.assertTrue(kwargs["start_new_session"])
            finally:
                mcp.VERIFICATION_LOG, mcp.VERIFICATION_PID = old_log, old_pid

    def test_run_verification_no_duplica_si_esta_en_curso(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_log, old_pid = mcp.VERIFICATION_LOG, mcp.VERIFICATION_PID
            mcp.VERIFICATION_LOG = Path(tmp) / "verificacion.log"
            mcp.VERIFICATION_PID = Path(tmp) / "verificacion.pid"
            mcp.VERIFICATION_PID.write_text(str(os.getpid()), encoding="utf-8")
            try:
                with mock.patch.object(mcp.subprocess, "Popen") as popen:
                    content, ok = mcp.run_verification()
                self.assertTrue(ok)
                popen.assert_not_called()
                payload = json.loads(content[0]["text"])
                self.assertEqual(payload["pid"], os.getpid())
                self.assertIn("en curso", payload["mensaje"])
            finally:
                mcp.VERIFICATION_LOG, mcp.VERIFICATION_PID = old_log, old_pid

    def test_verification_running_pidfiles_ausente_invalido_o_muerto(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_pid = mcp.VERIFICATION_PID
            mcp.VERIFICATION_PID = Path(tmp) / "verificacion.pid"
            try:
                self.assertIsNone(mcp._verification_running())
                mcp.VERIFICATION_PID.write_text("no-numero", encoding="utf-8")
                self.assertIsNone(mcp._verification_running())
                mcp.VERIFICATION_PID.write_text("999999999", encoding="utf-8")
                self.assertIsNone(mcp._verification_running())
            finally:
                mcp.VERIFICATION_PID = old_pid

    @unittest.skipUnless(os.path.isdir("/proc"), "requiere /proc (Linux)")
    def test_verification_running_ignora_zombie_y_lo_recolecta(self):
        import time

        with tempfile.TemporaryDirectory() as tmp:
            old_pid = mcp.VERIFICATION_PID
            mcp.VERIFICATION_PID = Path(tmp) / "verificacion.pid"
            try:
                proc = subprocess.Popen(["true"], stdout=subprocess.DEVNULL)
                estado = ""
                deadline = time.time() + 5
                while time.time() < deadline:
                    try:
                        stat = Path(f"/proc/{proc.pid}/stat").read_text(encoding="utf-8")
                    except OSError:
                        break
                    estado = stat.split(") ", 1)[1].split()[0]
                    if estado == "Z":
                        break
                    time.sleep(0.02)
                self.assertEqual(estado, "Z", "el hijo no quedo zombie a tiempo")
                mcp.VERIFICATION_PID.write_text(str(proc.pid), encoding="utf-8")
                self.assertIsNone(mcp._verification_running())
                self.assertFalse(Path(f"/proc/{proc.pid}").exists())
                # REQ-033: recolectar también desde el test (ResourceWarning)
                proc.wait()
            finally:
                mcp.VERIFICATION_PID = old_pid

    def test_run_verification_error_de_lanzamiento(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_log, old_pid = mcp.VERIFICATION_LOG, mcp.VERIFICATION_PID
            mcp.VERIFICATION_LOG = Path(tmp) / "verificacion.log"
            mcp.VERIFICATION_PID = Path(tmp) / "verificacion.pid"
            try:
                with mock.patch.object(mcp.subprocess, "Popen", side_effect=OSError("boom")):
                    content, ok = mcp.run_verification()
                self.assertFalse(ok)
                self.assertIn("no se pudo lanzar", content[0]["text"])
            finally:
                mcp.VERIFICATION_LOG, mcp.VERIFICATION_PID = old_log, old_pid

    def test_handle_call_excepcion_es_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_log = mcp.AUDIT_LOG
            mcp.AUDIT_LOG = Path(tmp) / "a.jsonl"
            try:
                with mock.patch.object(mcp, "search_knowledge", side_effect=RuntimeError("boom")):
                    content, is_error = mcp.handle_call("search_knowledge", {"query": "x"})
                self.assertTrue(is_error)
                self.assertIn("boom", content[0]["text"])
            finally:
                mcp.AUDIT_LOG = old_log

    def test_create_lesson_sin_campos_es_error(self):
        content, is_error = mcp.handle_call("create_lesson", {"problema": "p"})
        self.assertTrue(is_error)
        self.assertIn("obligatorias", content[0]["text"])

    def test_create_lesson_archivo_sin_salto_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_dir = mcp.LESSONS_DIR
            mcp.LESSONS_DIR = Path(tmp)
            try:
                archivo = Path(tmp) / f"{mcp.date.today().year}.yaml"
                archivo.write_text("- id: LSN-001\n  estado: Abierta", encoding="utf-8")
                content, is_error = mcp.handle_call(
                    "create_lesson", {"problema": "p", "recomendacion": "r"}
                )
                self.assertFalse(is_error)
                self.assertIn("LSN-002", content[0]["text"])
                self.assertIn("\n- id: LSN-002", archivo.read_text(encoding="utf-8"))
            finally:
                mcp.LESSONS_DIR = old_dir

    def test_search_knowledge_query_vacia(self):
        content = mcp.search_knowledge({"query": "   "})
        self.assertIn("vacia", content[0]["text"])

    def test_handle_call_run_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_log, old_pid = mcp.VERIFICATION_LOG, mcp.VERIFICATION_PID
            old_audit = mcp.AUDIT_LOG
            mcp.VERIFICATION_LOG = Path(tmp) / "v.log"
            mcp.VERIFICATION_PID = Path(tmp) / "v.pid"
            mcp.AUDIT_LOG = Path(tmp) / "a.jsonl"
            try:
                with mock.patch.object(mcp.subprocess, "Popen",
                                       return_value=mock.Mock(pid=777)):
                    content, is_error = mcp.handle_call("run_verification", {})
                self.assertFalse(is_error)
                self.assertIn("en curso", content[0]["text"])
            finally:
                mcp.VERIFICATION_LOG, mcp.VERIFICATION_PID = old_log, old_pid
                mcp.AUDIT_LOG = old_audit

    def test_stdio_messages_header_incompleto(self):
        srv = mcp.StdioServer()
        srv.buffer = b"Content-Length: 10\r\n"
        self.assertEqual(srv._messages(), [])

    def test_stdio_messages_content_length_json_invalido(self):
        srv = mcp.StdioServer()
        body = b"no-json"
        srv.buffer = b"Content-Length: %d\r\n\r\n%s" % (len(body), body)
        with mock.patch.object(mcp, "log"):
            self.assertEqual(srv._messages(), [])

    def test_stdio_messages_linea_vacia_ignorada(self):
        srv = mcp.StdioServer()
        srv.buffer = b'\n{"a": 1}\n'
        self.assertEqual(srv._messages(), [{"a": 1}])

    def test_log_escribe_en_stderr(self):
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err):
            mcp.log("hola")
        self.assertIn("hola", err.getvalue())

    def test_search_knowledge_usa_indice_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            know = Path(tmp) / "know"
            know.mkdir()
            (know / "a.md").write_text("## Timeout\nservidor timeout conexiones pool\n")
            storage = Path(tmp) / "st"
            storage.mkdir()
            old = (
                mcp.JSON_INDEX, mcp.KNOWLEDGE_DIR,
                ik.KNOWLEDGE_DIR, ik.STORAGE_DIR, ik.JSON_INDEX, ik.MANIFEST, ik.CHROMA_DIR,
            )
            mcp.JSON_INDEX = storage / "index.json"
            mcp.KNOWLEDGE_DIR = know
            ik.KNOWLEDGE_DIR, ik.STORAGE_DIR = know, storage
            ik.JSON_INDEX = storage / "index.json"
            ik.MANIFEST = storage / "manifest.json"
            ik.CHROMA_DIR = storage / "chroma_db"
            try:
                ik.build_json_index()
                content = mcp.search_knowledge({"query": "timeout"})
                self.assertIn("timeout", content[0]["text"])
            finally:
                (
                    mcp.JSON_INDEX, mcp.KNOWLEDGE_DIR,
                    ik.KNOWLEDGE_DIR, ik.STORAGE_DIR, ik.JSON_INDEX, ik.MANIFEST, ik.CHROMA_DIR,
                ) = old

    def test_stdio_messages_jsonl_y_parcial(self):
        srv = mcp.StdioServer()
        srv.buffer = b'{"a": 1}\n{"b": 2}\n'
        self.assertEqual(srv._messages(), [{"a": 1}, {"b": 2}])
        self.assertEqual(srv.buffer, b"")
        srv.buffer = b'{"a": 1}'
        self.assertEqual(srv._messages(), [])

    def test_stdio_messages_content_length(self):
        srv = mcp.StdioServer()
        body = b'{"a": 1}'
        srv.buffer = b"Content-Length: %d\r\n\r\n%s" % (len(body), body)
        self.assertEqual(srv._messages(), [{"a": 1}])

    def test_stdio_messages_content_length_incompleto(self):
        srv = mcp.StdioServer()
        srv.buffer = b'Content-Length: 50\r\n\r\n{"a": 1}'
        self.assertEqual(srv._messages(), [])

    def test_stdio_messages_header_sin_length(self):
        srv = mcp.StdioServer()
        srv.buffer = b"Content-Length: abc\r\n\r\nbody"
        self.assertEqual(srv._messages(), [])
        self.assertEqual(srv.buffer, b"")

    def test_stdio_messages_json_invalido_ignorado(self):
        srv = mcp.StdioServer()
        srv.buffer = b'no-json\n{"ok": 1}\n'
        with mock.patch.object(mcp, "log"):
            self.assertEqual(srv._messages(), [{"ok": 1}])

    def test_stdio_send(self):
        srv = mcp.StdioServer()
        buf = io.StringIO()
        with mock.patch.object(sys, "stdout", buf):
            srv.send({"a": 1})
        self.assertEqual(buf.getvalue().strip(), '{"a": 1}')

    def test_stdio_dispatch_metodos(self):
        srv = mcp.StdioServer()
        enviados = []
        with mock.patch.object(srv, "send", side_effect=lambda p: enviados.append(p)), \
                mock.patch.object(mcp, "log"):
            srv._dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            srv._dispatch({"jsonrpc": "2.0", "id": 2, "method": "ping"})
            srv._dispatch({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
            srv._dispatch({"jsonrpc": "2.0", "method": "notifications/initialized"})
            srv._dispatch({"jsonrpc": "2.0", "method": "notifications/cancelled"})
            srv._dispatch({"jsonrpc": "2.0", "id": 4, "method": "desconocido"})
        self.assertEqual(enviados[0]["result"]["serverInfo"]["name"], "better-project")
        self.assertEqual(enviados[1]["result"], {})
        self.assertEqual(len(enviados[2]["result"]["tools"]), 5)
        self.assertEqual(len(enviados), 3)

    def test_stdio_dispatch_tools_call(self):
        srv = mcp.StdioServer()
        enviados = []
        with mock.patch.object(mcp, "handle_call",
                               return_value=([{"type": "text", "text": "x"}], False)), \
                mock.patch.object(srv, "send", side_effect=lambda p: enviados.append(p)):
            srv._dispatch({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                           "params": {"name": "validate_requirements", "arguments": {}}})
        self.assertFalse(enviados[0]["result"]["isError"])
        self.assertEqual(enviados[0]["id"], 9)

    def test_stdio_run_procesa_linea(self):
        srv = mcp.StdioServer()
        salida = io.StringIO()

        class _In:
            buffer = [b'{"jsonrpc": "2.0", "id": 1, "method": "ping"}\n']

        with mock.patch.object(sys, "stdin", _In()), mock.patch.object(sys, "stdout", salida):
            srv.run()
        self.assertIn('"result"', salida.getvalue())


class TestTUI(unittest.TestCase):
    def test_truncar(self):
        self.assertEqual(tui.truncar("corto", 10), "corto")
        self.assertEqual(tui.truncar("1234567890abc", 10), "123456789…")
        self.assertEqual(len(tui.truncar("1234567890abc", 10)), 10)

    def test_estado_color(self):
        self.assertEqual(tui.estado_color("Implementado"), tui.CP_OK)
        self.assertEqual(tui.estado_color("Deprecado"), tui.CP_DIM)
        self.assertEqual(tui.estado_color("Desconocido"), tui.CP_HEADER)

    def test_cambio_de_pestana(self):
        app = tui.App()
        app._tecla_principal(ord("2"))
        self.assertEqual(app.tab, 1)
        app._tecla_principal(ord("1"))
        self.assertEqual(app.tab, 0)

    def test_consulta_acumula_caracteres(self):
        app = tui.App()
        app.tab = 1
        app._tecla_principal(ord("p"))
        app._tecla_principal(ord("i"))
        self.assertEqual(app.consulta, "pi")

    def test_busqueda_directa_encuentra_pilares(self):
        app = tui.App()
        app.buscar_conocimiento("pilar")
        self.assertGreater(len(app.knowledge), 0)
        self.assertTrue(any("pilar" in hit["contenido"].lower() for hit in app.knowledge))

    def _stdscr(self):
        s = mock.MagicMock()
        s.getmaxyx.return_value = (24, 80)
        return s

    def test_buscar_conocimiento_vacio(self):
        app = tui.App()
        app.buscar_conocimiento("   ")
        self.assertEqual(app.knowledge, [])
        self.assertIn("consulta", app.mensaje)

    def test_busqueda_directa_con_terminos(self):
        with tempfile.TemporaryDirectory() as tmp:
            know = Path(tmp)
            (know / "a.md").write_text("## Timeout\nservidor timeout conexiones pool\n")
            old_know, old_root = ik.KNOWLEDGE_DIR, tui.ROOT
            ik.KNOWLEDGE_DIR = know
            tui.ROOT = know
            try:
                app = tui.App()
                res = app._busqueda_directa("timeout")
                self.assertTrue(res)
                self.assertEqual(app._busqueda_directa(""), [])
            finally:
                ik.KNOWLEDGE_DIR, tui.ROOT = old_know, old_root

    def test_indexar_mensaje(self):
        app = tui.App()
        with mock.patch.object(tui.index_knowledge, "index_all") as ia:
            app.indexar()
            ia.assert_called_once_with(force=False)
        self.assertIn("indice", app.mensaje)

    def test_ejecutar_verificar_ok_timeout_y_ausente(self):
        app = tui.App()
        with mock.patch.object(tui.subprocess, "run",
                               return_value=mock.Mock(returncode=0, stdout="ok\n", stderr="")):
            app.ejecutar_verificar()
        self.assertTrue(app.verificar_ok)
        with mock.patch.object(tui.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
            app.ejecutar_verificar()
        self.assertFalse(app.verificar_ok)
        self.assertIn("agotada", app.verificar[0])
        old_scripts = tui.SCRIPTS
        tui.SCRIPTS = Path(tempfile.mkdtemp())
        try:
            app.ejecutar_verificar()
            self.assertFalse(app.verificar_ok)
            self.assertIn("no existe", app.verificar[0])
        finally:
            tui.SCRIPTS = old_scripts

    def test_items_actuales_por_pestana(self):
        app = tui.App()
        app.requisitos = [1, 2]
        app.knowledge = [1]
        app.lecciones = [1, 2, 3]
        app.verificar = [1, 2]
        self.assertEqual(app._items_actuales(), 2)
        app.tab = 1
        self.assertEqual(app._items_actuales(), 1)
        app.tab = 2
        self.assertEqual(app._items_actuales(), 3)
        app.tab = 3
        self.assertEqual(app._items_actuales(), 2)

    def test_rango_visible(self):
        app = tui.App()
        self.assertEqual(app._rango_visible(24, 80), (0, 19))

    def test_tecla_principal_navegacion_y_consulta(self):
        app = tui.App()
        app.requisitos = [{"id": "REQ-001", "meta": {}, "path": Path("x"), "refs": 0}]
        app._tecla_principal(ord("1"))
        self.assertEqual(app.tab, 0)
        app._tecla_principal(tui.curses.KEY_DOWN)
        self.assertEqual(app.seleccion[0], 0)
        app._tecla_principal(ord("2"))
        self.assertEqual(app.tab, 1)
        app.consulta = ""
        with mock.patch.object(tui.index_knowledge, "index_all") as ia:
            app._tecla_principal(ord("i"))
            ia.assert_called_once()
        app._tecla_principal(ord("a"))
        self.assertEqual(app.consulta, "a")
        app._tecla_principal(8)
        self.assertEqual(app.consulta, "")
        app._tecla_principal(ord("x"))
        self.assertEqual(app.consulta, "x")
        app.tab = 3
        with mock.patch.object(app, "ejecutar_verificar") as ev:
            app._tecla_principal(ord("R"))
            ev.assert_called_once()

    def test_detalle_y_scroll(self):
        app = tui.App()
        app.cargar_requisitos()
        app._abrir_detalle()
        self.assertIsNotNone(app.detalle)
        stdscr = self._stdscr()
        with mock.patch.object(tui.curses, "color_pair", return_value=0):
            app._draw(stdscr)
        app._tecla_detalle(tui.curses.KEY_DOWN)
        self.assertEqual(app.detalle.offset, 1)
        app._tecla_detalle(tui.curses.KEY_UP)
        self.assertEqual(app.detalle.offset, 0)
        app._tecla_detalle(ord("j"))
        self.assertTrue(app._tecla_detalle(ord("q")))

    def test_detalle_conocimiento_y_leccion(self):
        app = tui.App()
        app.tab = 1
        app.knowledge = [{"archivo": "a.md", "contenido": "texto de prueba", "score": 3}]
        with mock.patch.object(tui.curses, "COLS", 80, create=True):
            app._abrir_detalle()
        self.assertEqual(app.detalle.titulo, "Conocimiento")
        app.tab = 2
        app.lecciones = [{"id": "LSN-001", "estado": "Abierta", "problema": "p",
                          "recomendacion": "r", "proyecto": "x", "fase": "f",
                          "categoria": "c", "fecha": "2026-01-01"}]
        app._abrir_detalle()
        self.assertEqual(app.detalle.titulo, "LSN-001")

    def test_draw_todas_las_pestanas(self):
        app = tui.App()
        app.cargar_requisitos()
        app.cargar_lecciones()
        app.knowledge = [{"archivo": "a.md", "contenido": "contenido", "score": 1}]
        app.verificar = ["linea de salida"]
        stdscr = self._stdscr()
        with mock.patch.object(tui.curses, "color_pair", return_value=0), \
                mock.patch.object(tui.curses, "has_colors", return_value=False):
            for tab in range(4):
                app.tab = tab
                app._draw(stdscr)
        self.assertTrue(stdscr.addstr.called)

    def test_init_colores_y_draw_con_color(self):
        app = tui.App()
        with mock.patch.object(tui.curses, "has_colors", return_value=True), \
                mock.patch.object(tui.curses, "start_color"), \
                mock.patch.object(tui.curses, "use_default_colors"), \
                mock.patch.object(tui.curses, "init_pair") as ip:
            app._init_colores()
            self.assertTrue(ip.called)
        stdscr = self._stdscr()
        with mock.patch.object(tui.curses, "color_pair", return_value=0), \
                mock.patch.object(tui.curses, "has_colors", return_value=True):
            app.cargar_requisitos()
            app._draw(stdscr)

    def test_draw_status_altura_minima(self):
        app = tui.App()
        stdscr = self._stdscr()
        app._draw_status(stdscr, 1, 80)
        self.assertFalse(stdscr.addstr.called)

    def test_lista_vacia_muestra_sin_datos(self):
        app = tui.App()
        app.tab = 2
        app.lecciones = []
        stdscr = self._stdscr()
        with mock.patch.object(tui.curses, "color_pair", return_value=0), \
                mock.patch.object(tui.curses, "has_colors", return_value=False):
            app._draw(stdscr)
        self.assertTrue(any("sin datos" in str(c) for c in stdscr.addstr.call_args_list))

    def test_main_envuelve_run(self):
        with mock.patch.object(tui.curses, "wrapper", return_value=0) as w:
            self.assertEqual(tui.main(), 0)
        self.assertTrue(w.called)

    def test_run_sale_con_q(self):
        app = tui.App()
        stdscr = self._stdscr()
        stdscr.getch.return_value = ord("q")
        with mock.patch.object(app, "_init_colores"), \
                mock.patch.object(app, "cargar_requisitos"), \
                mock.patch.object(app, "cargar_lecciones"), \
                mock.patch.object(app, "_draw"), \
                mock.patch.object(tui.curses, "curs_set"):
            app.run(stdscr)
        self.assertEqual(stdscr.getch.call_count, 1)

    def test_main_sin_curses_devuelve_1(self):
        """REQ-006: main devuelve 1 si curses no esta disponible."""
        with mock.patch.object(tui, "HAS_CURSES", False):
            self.assertEqual(tui.main(), 1)

    def test_busqueda_directa_sin_terminos_utiles(self):
        """REQ-006: _busqueda_directa devuelve [] si no quedan terminos utiles."""
        with tempfile.TemporaryDirectory() as tmp:
            know = Path(tmp)
            old_know, old_root = ik.KNOWLEDGE_DIR, tui.ROOT
            ik.KNOWLEDGE_DIR = know
            tui.ROOT = know
            try:
                app = tui.App()
                self.assertEqual(app._busqueda_directa("el la los"), [])
            finally:
                ik.KNOWLEDGE_DIR, tui.ROOT = old_know, old_root

    def test_run_resize_ignorado(self):
        """REQ-006: KEY_RESIZE no interrumpe el bucle."""
        app = tui.App()
        stdscr = self._stdscr()
        stdscr.getch.side_effect = [tui.curses.KEY_RESIZE, ord("q")]
        with mock.patch.object(app, "_init_colores"), \
                mock.patch.object(app, "cargar_requisitos"), \
                mock.patch.object(app, "cargar_lecciones"), \
                mock.patch.object(app, "_draw"), \
                mock.patch.object(tui.curses, "curs_set"):
            app.run(stdscr)
        self.assertEqual(stdscr.getch.call_count, 2)

    def test_tecla_detalle_vuelve_con_enter(self):
        """REQ-006: Enter en detalle cierra el detalle."""
        app = tui.App()
        app.detalle = tui.Detalle("x", ["a", "b"])
        self.assertTrue(app._tecla_detalle(ord("\n")))

    def test_tecla_principal_navegacion_lista_vacia(self):
        """REQ-006: navegacion en lista vacia no modifica seleccion."""
        app = tui.App()
        app.requisitos = []
        app._tecla_principal(tui.curses.KEY_DOWN)
        self.assertEqual(app.seleccion[0], 0)

    def test_abrir_detalle_fuera_de_rango_no_cambia(self):
        """REQ-006: abrir detalle con seleccion fuera de rango no cambia detalle."""
        app = tui.App()
        app.tab = 0
        app.seleccion[0] = 999
        app.requisitos = [{"id": "REQ-001", "meta": {}, "path": Path("x"), "refs": 0}]
        app.detalle = None
        app._abrir_detalle()
        self.assertIsNone(app.detalle)

    def test_draw_tabs_termina_si_no_cabe(self):
        """REQ-006: _draw_tabs deja de escribir pestanas si no caben."""
        app = tui.App()
        stdscr = self._stdscr()
        stdscr.getmaxyx.return_value = (24, 10)
        with mock.patch.object(tui.curses, "color_pair", return_value=0):
            app._draw_tabs(stdscr, 24, 10)
        self.assertLessEqual(stdscr.addstr.call_count, 2)

    def test_draw_requisitos_color_warn(self):
        """REQ-006: la cabecera usa CP_WARN con advertencias y CP_OK sin ellas."""
        app = tui.App()
        app.requisitos = []
        stdscr = self._stdscr()
        with mock.patch.object(tui.curses, "color_pair", side_effect=lambda par: f"CP{par}"):
            app.validacion = {"errores": 0, "advertencias": 1}
            app._draw_requisitos(stdscr, 24, 80)
            cabecera_con_warn = stdscr.addstr.call_args_list[0]
            self.assertEqual(cabecera_con_warn.args[0], 2)
            self.assertEqual(cabecera_con_warn.args[3], f"CP{tui.CP_WARN}")
            self.assertIn("1W", cabecera_con_warn.args[2])
            stdscr.addstr.reset_mock()
            app.validacion = {"errores": 0, "advertencias": 0}
            app._draw_requisitos(stdscr, 24, 80)
            self.assertEqual(stdscr.addstr.call_args_list[0].args[3], f"CP{tui.CP_OK}")

    def test_draw_detalle_sin_lineas_extra(self):
        """REQ-006: _draw_detalle no escribe fuera de las lineas disponibles."""
        app = tui.App()
        app.detalle = tui.Detalle("x", [f"linea {i}" for i in range(50)])
        stdscr = self._stdscr()
        stdscr.getmaxyx.return_value = (6, 40)
        with mock.patch.object(tui.curses, "color_pair", return_value=0):
            app._draw_detalle(stdscr)
        filas = [c.args[0] for c in stdscr.addstr.call_args_list]
        self.assertTrue(filas)
        self.assertEqual(max(filas), 5)  # ultima fila util de una pantalla de 6


if __name__ == "__main__":
    unittest.main()
