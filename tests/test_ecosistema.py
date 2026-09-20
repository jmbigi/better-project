#!/usr/bin/env python3
"""Suite de tests del ecosistema better-project (REQ-001..REQ-006).

stdlib unittest, sin dependencias. Ejecutar:
    python3 -m unittest discover -s tests -q
Usa directorios temporales para no tocar el estado real del repo.
"""

import argparse
import ast
import io
import json
import math
import os
import shutil
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

import adr_validator as av  # noqa: E402
import analyze_shell as ash  # noqa: E402
import auto_audit as aa  # noqa: E402
import diagnostico as diag  # noqa: E402
import download_jev_model as djm  # noqa: E402
import doc_validator as dv  # noqa: E402
import index_knowledge as ik  # noqa: E402
import jev_calibration as jc  # noqa: E402
import jev_calibration_merge as jcm  # noqa: E402
import jev_pillars as jp  # noqa: E402
import jev_review as jr  # noqa: E402
import lessons_extractor as le  # noqa: E402
import mcp_server as mcp  # noqa: E402
import mutation_check as mc  # noqa: E402
import tui  # noqa: E402

REQ_BODY = (
    "---\nid: {id}\ntitulo: {titulo}\nestado: {estado}\nprioridad: {prioridad}\n"
    "version: {version}\nfecha_creacion: {fecha}\n---\n# {id}\n"
)
VALID = {
    "id": "REQ-100",
    "titulo": "Requisito de prueba",
    "estado": "Aprobado",
    "prioridad": "Media",
    "version": "1.0",
    "fecha": "2026-08-06",
}


class TestDocValidator(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.reqs = self.tmp / ".docs" / "requirements"
        self.reqs.mkdir(parents=True)
        self.old_req_dir, self.old_root = dv.REQ_DIR, dv.ROOT
        dv.REQ_DIR, dv.ROOT = self.reqs, self.tmp

    def tearDown(self):
        dv.REQ_DIR, dv.ROOT = self.old_req_dir, self.old_root

    def _req(self, rid="REQ-100", **over):
        data = {**VALID, **over, "id": rid}
        (self.reqs / f"{rid}.md").write_text(REQ_BODY.format(**data), encoding="utf-8")

    def _code(self, contenido, nombre="x.py"):
        (self.tmp / nombre).write_text(contenido, encoding="utf-8")

    def test_repo_real_sin_errores(self):
        dv.REQ_DIR, dv.ROOT = self.old_req_dir, self.old_root
        reqs = dv.collect_req_files()
        refs = dv.collect_code_refs()
        dv.analizar(reqs, refs)
        self.assertGreaterEqual(len(reqs), 6)
        self.assertEqual(dv.errors, [])
        self.assertIn("REQ-006", refs)

    def test_referencia_sin_archivo_es_error(self):
        self._req()
        self._code("# REQ-999\n")
        reqs = dv.collect_req_files()
        refs = dv.collect_code_refs()
        dv.analizar(reqs, refs)
        self.assertTrue(any("REQ-999" in e for e in dv.errors))

    def test_deprecado_referenciado_es_error(self):
        self._req(estado="Deprecado")
        self._code("# REQ-100\n")
        reqs = dv.collect_req_files()
        refs = dv.collect_code_refs()
        dv.analizar(reqs, refs)
        self.assertTrue(any("Deprecado" in e for e in dv.errors))

    def test_implementado_sin_refs_es_advertencia(self):
        self._req(estado="Implementado")
        reqs = dv.collect_req_files()
        refs = dv.collect_code_refs()
        dv.analizar(reqs, refs)
        self.assertTrue(any("REQ-100" in w and "no tiene referencias" in w for w in dv.warnings))

    def test_estado_invalido_es_error(self):
        self._req(estado="Malo")
        dv.collect_req_files()
        self.assertTrue(any("estado" in e for e in dv.errors))

    def test_id_no_coincide_con_nombre_es_error(self):
        (self.reqs / "REQ-100.md").write_text(REQ_BODY.format(**VALID), encoding="utf-8")
        (self.reqs / "REQ-100.md").write_text(
            REQ_BODY.format(**{**VALID, "id": "REQ-999"}), encoding="utf-8"
        )
        dv.collect_req_files()
        self.assertTrue(any("no coincide" in e for e in dv.errors))

    def test_prioridad_invalida_es_error(self):
        self._req(prioridad="Urgentisima")
        dv.collect_req_files()
        self.assertTrue(any("prioridad" in e for e in dv.errors))

    def test_fecha_invalida_es_error(self):
        self._req(fecha="06-08-2026")
        dv.collect_req_files()
        self.assertTrue(any("fecha_creacion" in e for e in dv.errors))

    def test_version_invalida_es_error(self):
        self._req(version="v1.0")
        dv.collect_req_files()
        self.assertTrue(any("version" in e for e in dv.errors))

    def test_coleccion_idempotente(self):
        self._req(estado="Malo")
        dv.collect_req_files()
        dv.collect_req_files()
        self.assertEqual(len([e for e in dv.errors if "estado" in e]), 1)

    def test_main_devuelve_1_con_errores(self):
        self._req(estado="Malo")
        dv.collect_req_files()
        self.assertEqual(dv.main(), 1)

    def test_demo_excluida_del_scan(self):
        reqs = dv.collect_req_files()
        refs = dv.collect_code_refs()
        dv.analizar(reqs, refs)
        self.assertEqual(dv.errors, [])
        self.assertTrue(
            all(not r.startswith("demo/") for locations in refs.values() for r in locations)
        )

    def test_root_demo_valida_proyecto_externo(self):
        proc = subprocess.run(
            [sys.executable, "scripts/doc_validator.py", "--root", "demo"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("3 REQs", proc.stdout)

    def test_sin_frontmatter_es_error(self):
        (self.reqs / "REQ-100.md").write_text("# sin frontmatter\n", encoding="utf-8")
        dv.collect_req_files()
        self.assertTrue(any("sin frontmatter" in e for e in dv.errors))

    def test_id_frontmatter_invalido_es_error(self):
        (self.reqs / "REQ-100.md").write_text(
            "---\nid: XX\ntitulo: T\nestado: Implementado\nprioridad: Alta\n"
            "version: 1.0\nfecha_creacion: 2026-08-06\n---\n", encoding="utf-8")
        dv.collect_req_files()
        self.assertTrue(any("'id' invalido" in e for e in dv.errors))

    def test_faltan_campos_es_error(self):
        (self.reqs / "REQ-100.md").write_text(
            "---\nid: REQ-100\ntitulo: T\nestado: Implementado\n---\n", encoding="utf-8")
        dv.collect_req_files()
        self.assertTrue(any("faltan campos" in e for e in dv.errors))

    def test_draft_referenciado_es_advertencia(self):
        self._req(estado="Draft")
        self._code("# REQ-100\n")
        reqs = dv.collect_req_files()
        refs = dv.collect_code_refs()
        dv.analizar(reqs, refs)
        self.assertTrue(any("Draft" in w for w in dv.warnings))

    def test_strict_falla_con_advertencias(self):
        self._req(estado="Implementado")  # sin referencias -> advertencia
        with mock.patch.object(sys, "argv", ["doc_validator.py", "--strict"]), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(dv.main(), 1)


class TestLessonsExtractor(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.old_dir = le.LESSONS_DIR
        le.LESSONS_DIR = self.tmp

    def tearDown(self):
        le.LESSONS_DIR = self.old_dir

    def _yaml(self, contenido, nombre="2026.yaml"):
        (self.tmp / nombre).write_text(contenido, encoding="utf-8")

    def test_parser_minimo_multilinea(self):
        datos = le._minimal_parser(
            '- id: LSN-001\n  proyecto: "Mod Pago"\n  problema: "texto con dos palabras"\n'
            "  estado: Resuelta\n  fecha: 2026-08-06\n"
        )
        self.assertEqual(len(datos), 1)
        self.assertEqual(datos[0]["proyecto"], "Mod Pago")
        self.assertEqual(datos[0]["problema"], "texto con dos palabras")

    def test_parser_varias_entradas(self):
        datos = le._minimal_parser(
            "- id: LSN-001\n  estado: Abierta\n  fecha: 2026-01-01\n"
            "- id: LSN-002\n  estado: Resuelta\n  fecha: 2026-01-02\n"
        )
        self.assertEqual([d["id"] for d in datos], ["LSN-001", "LSN-002"])

    def test_campo_faltante_genera_problema(self):
        self._yaml("- id: LSN-001\n  estado: Resuelta\n  fecha: 2026-08-06\n")
        _, problems = le.validate()
        self.assertTrue(any("faltan campos" in p for p in problems))

    def test_fecha_invalida_genera_problema(self):
        self._yaml(
            "- id: LSN-001\n  proyecto: x\n  fase: y\n  categoria: z\n  problema: a\n"
            "  recomendacion: b\n  estado: Resuelta\n  fecha: ayer\n"
        )
        _, problems = le.validate()
        self.assertTrue(any("fecha" in p for p in problems))

    def test_render_context_incluye_datos(self):
        datos = [
            {"id": "LSN-001", "proyecto": "P", "fase": "F", "categoria": "C",
             "problema": "prob", "recomendacion": "rec", "estado": "Resuelta", "fecha": "2026-08-06"}
        ]
        texto = le.render_context(datos)
        self.assertIn("LSN-001", texto)
        self.assertIn("prob", texto)
        self.assertIn("rec", texto)

    def test_estado_invalido_genera_problema(self):
        self._yaml(
            "- id: LSN-001\n  proyecto: P\n  fase: F\n  categoria: C\n  problema: a\n"
            "  recomendacion: b\n  estado: EnCurso\n  fecha: 2026-08-06\n"
        )
        _, problems = le.validate()
        self.assertTrue(any("estado" in p and "invalido" in p for p in problems))

    def test_parser_linea_indentada_sin_entrada(self):
        self.assertEqual(le._minimal_parser("  clave: valor\n"), [])

    def test_main_check_no_genera_contexto(self):
        self._yaml(
            "- id: LSN-001\n  proyecto: P\n  fase: F\n  categoria: C\n  problema: a\n"
            "  recomendacion: b\n  estado: Resuelta\n  fecha: 2026-08-06\n"
        )
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["lessons_extractor.py", "--check"]), \
                mock.patch.object(sys, "stdout", buf), \
                mock.patch.object(le, "OUTPUT", self.tmp / "ctx.txt"):
            rc = le.main()
        self.assertEqual(rc, 0)
        self.assertNotIn("lessons_context.txt", buf.getvalue())

    def test_main_json_conserva_acentos(self):
        self._yaml(
            "- id: LSN-001\n  proyecto: P\n  fase: F\n  categoria: C\n"
            "  problema: situación crítica\n  recomendacion: b\n  estado: Resuelta\n"
            "  fecha: 2026-08-06\n  fecha_resolucion: 2026-08-07\n"
        )
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["lessons_extractor.py", "--json"]), \
                mock.patch.object(sys, "stdout", buf), \
                mock.patch.object(le, "OUTPUT", self.tmp / "ctx.txt"):
            rc = le.main()
        self.assertEqual(rc, 0)
        self.assertIn("situación", buf.getvalue())
        json.loads(buf.getvalue())


class TestIndexKnowledge(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.know = self.tmp / "know"
        self.know.mkdir()
        self.storage = self.tmp / "storage"
        self.storage.mkdir()
        self.old = (
            ik.KNOWLEDGE_DIR, ik.STORAGE_DIR, ik.JSON_INDEX, ik.MANIFEST, ik.CHROMA_DIR,
        )
        ik.KNOWLEDGE_DIR = self.know
        ik.STORAGE_DIR = self.storage
        ik.JSON_INDEX = self.storage / "index.json"
        ik.MANIFEST = self.storage / "manifest.json"
        ik.CHROMA_DIR = self.storage / "chroma_db"

    def tearDown(self):
        (
            ik.KNOWLEDGE_DIR, ik.STORAGE_DIR, ik.JSON_INDEX, ik.MANIFEST, ik.CHROMA_DIR,
        ) = self.old

    def test_chunks_por_h2(self):
        chunks = ik._chunks(
            "intro corta\n## Seccion A\ncontenido del chunk A con mas de veinte caracteres\n"
            "## Seccion B\ncontenido del chunk B con mas de veinte caracteres\n"
        )
        self.assertEqual(len(chunks), 2)
        self.assertIn("Seccion A", chunks[0])
        self.assertIn("Seccion B", chunks[1])

    def test_tokenize_quita_stopwords(self):
        tokens = ik._tokenize("El sistema de pago no funciona")
        self.assertNotIn("el", tokens)
        self.assertIn("sistema", tokens)
        self.assertIn("pago", tokens)

    def test_build_y_busqueda_tfidf(self):
        (self.know / "a.md").write_text("## Pilar requisitos\npilar requisitos trazabilidad contrato\n")
        (self.know / "b.md").write_text("## Timeout\nservidor timeout conexiones pool\n")
        n_files, n_chunks = ik.build_json_index()
        self.assertEqual(n_files, 2)
        self.assertGreaterEqual(n_chunks, 2)
        top_pilar = ik.search_json("pilar requisitos")[0]
        self.assertIn("pilar", top_pilar["contenido"])
        top_timeout = ik.search_json("timeout")[0]
        self.assertIn("timeout", top_timeout["contenido"])

    def test_chunk_id_unico_entre_homonimos(self):
        a = self.know / "architecture" / "ecosistema.md"
        b = self.know / "business-rules" / "ecosistema.md"
        a.parent.mkdir(parents=True)
        b.parent.mkdir(parents=True)
        a.write_text("## A\ncontenido\n")
        b.write_text("## B\ncontenido\n")
        self.assertNotEqual(ik._chunk_id(a, 0), ik._chunk_id(b, 0))

    def test_check_fresh(self):
        (self.know / "a.md").write_text("## A\ncontenido\n")
        ik.build_json_index()
        self.assertTrue(ik.check_fresh())
        (self.know / "b.md").write_text("## B\nnuevo\n")
        self.assertFalse(ik.check_fresh())

    def test_check_fresh_sin_indice(self):
        self.assertFalse(ik.check_fresh())

    def test_json_index_chunk_sin_palabras_utiles(self):
        (self.know / "a.md").write_text("## S\nel la los las de del y o u a en con para por\n")
        n_files, n_chunks = ik.build_json_index()
        self.assertEqual(n_files, 1)
        self.assertGreaterEqual(n_chunks, 1)

    def test_json_index_conserva_acentos(self):
        (self.know / "a.md").write_text("## Reglas\nsituación crítica de prueba\n")
        ik.build_json_index()
        self.assertIn("situación", ik.JSON_INDEX.read_text(encoding="utf-8"))

    def test_main_search_sobre_indice_json(self):
        (self.know / "a.md").write_text("## Timeout\nservidor timeout conexiones pool\n")
        ik.build_json_index()
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["index_knowledge.py", "search", "timeout"]), \
                mock.patch.object(sys, "stdout", buf):
            rc = ik.main()
        self.assertEqual(rc, 0)
        self.assertIn("timeout", buf.getvalue())

    def test_index_all_force_reconstruye(self):
        (self.know / "a.md").write_text("## A\ncontenido de prueba largo suficiente\n")
        ik.build_json_index()
        ik.JSON_INDEX.write_text("SENTINELA", encoding="utf-8")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            ik.index_all(force=False)
        self.assertEqual(ik.JSON_INDEX.read_text(encoding="utf-8"), "SENTINELA")
        with mock.patch.object(sys, "stdout", io.StringIO()):
            ik.index_all(force=True)
        self.assertIn("chunks", ik.JSON_INDEX.read_text(encoding="utf-8"))

    def test_check_fresh_manifiesto_extra(self):
        (self.know / "a.md").write_text("## A\ncontenido largo suficiente para chunk\n")
        ik.build_json_index()
        m = json.loads(ik.MANIFEST.read_text(encoding="utf-8"))
        m["extra.md"] = 123.0
        ik.MANIFEST.write_text(json.dumps(m), encoding="utf-8")
        self.assertFalse(ik.check_fresh())

    def test_main_check_y_all(self):
        (self.know / "a.md").write_text("## A\ncontenido largo suficiente para chunk\n")
        with mock.patch.object(sys, "argv", ["index_knowledge.py"]), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            ik.main()
        with mock.patch.object(sys, "argv", ["index_knowledge.py", "--check"]), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(ik.main(), 0)
        with mock.patch.object(sys, "argv", ["index_knowledge.py", "--all"]), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(ik.main(), 0)


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
                (json.loads(l) for l in proc.stdout.splitlines() if l.strip())
            }
            self.assertEqual(respuestas[1]["result"]["serverInfo"]["name"], "better-project")
            self.assertFalse(respuestas[2]["result"]["isError"])
            self.assertIn("REQ-001", respuestas[2]["result"]["content"][0]["text"])
            # el limite de REQ-007 se aplica tambien por stdio
            self.assertTrue(respuestas[3]["result"]["isError"])
            self.assertIn("limite", respuestas[3]["result"]["content"][0]["text"])
            # la auditoria se escribio (en .docs/.storage del repo real)
            self.assertTrue(mcp.AUDIT_LOG.exists())


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
            ".git", "node_modules", "__pycache__", ".storage", "*.pyc", ".venv", "venv"
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
            shutil.copy(self.repo / "scripts" / "hooks" / "pre-commit", hooks / "pre-commit")

            # Commit verde: el hook debe dejar pasar el repo intacto.
            with (self.repo / "scripts" / "tui.py").open("a", encoding="utf-8") as fh:
                fh.write("\n# comentario inocuo para el commit verde\n")
            self._git("add", "-A")
            verde = self._git("commit", "-q", "-m", "verde")
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
            ".git", "node_modules", "__pycache__", ".storage", "*.pyc", ".venv", "venv"
        )
        shutil.copytree(ROOT, repo, ignore=ignore)
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "dummy@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "dummy"], cwd=repo, check=True)
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        # bootstrap sin hook: con HEAD no nacido git fsck emite avisos (LSN-005)
        subprocess.run(["git", "commit", "-qm", "bootstrap", "--no-verify"], cwd=repo, check=True)
        shutil.copy(repo / "scripts" / "hooks" / "pre-commit", repo / ".git" / "hooks" / "pre-commit")
        return repo

    def _verifica(self, repo):
        env = {**os.environ, "BETTER_TEST_INTEGRACION": "1"}
        return subprocess.run(
            ["bash", "scripts/verificar-proyecto.sh", "--pre-commit"],
            cwd=repo, capture_output=True, text=True, env=env,
        )

    def test_verificador_en_verde_sobre_copia_intacta(self):
        proc = self._verifica(self._copia())
        self.assertEqual(proc.returncode, 0, proc.stdout[-2000:] + proc.stderr[-2000:])

    def test_verificador_detecta_regla_p0_eliminada(self):
        repo = self._copia()
        agents = repo / "AGENTS.md"
        lineas = agents.read_text(encoding="utf-8").splitlines(keepends=True)
        self.assertTrue(any(l.startswith("### P0.20") for l in lineas))
        # eliminar la linea completa: el conteo de reglas P0 baja a 19
        agents.write_text(
            "".join(l for l in lineas if not l.startswith("### P0.20")), encoding="utf-8"
        )
        proc = self._verifica(repo)
        self.assertEqual(proc.returncode, 1, "el verificador no detecto la corrupcion")
        self.assertIn("[FALLO] 20 reglas P0 definidas en AGENTS.md", proc.stdout)


class TestJevLlama(unittest.TestCase):
    """REQ-011: cliente Jev AI liviano con llama.cpp."""

    _VOCAB = 1000
    _N_ROWS = 256

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.model_path = self.tmp / "fake.gguf"
        self.model_path.write_bytes(b"fake-model")

        # Importamos jev_llama sin dependencias (los imports son diferidos),
        # luego mockeamos llama_cpp y numpy solo para estas pruebas.
        import jev_llama as jl

        self.jl = jl

        self._real_llama = sys.modules.get("llama_cpp")
        self._real_numpy = sys.modules.get("numpy")
        self._real_model_env = os.environ.pop("JEV_MODEL_PATH", None)
        self._real_temp_env = os.environ.pop("JEV_TEMPERATURE", None)

        vocab = self._VOCAB
        rows = self._N_ROWS

        class _FakeNumpy:
            @staticmethod
            def array(x):
                return list(x)

            @staticmethod
            def log(x):
                return [math.log(v + 1e-12) for v in x]

            @staticmethod
            def argmax(x):
                return max(range(len(x)), key=lambda i: x[i])

        class _FakeLlama:
            # scores 2D (n_ctx, vocab) igual que llama-cpp-python real.
            def __init__(self, **kwargs):
                self._kwargs = kwargs
                self.scores = [[0.0] * vocab for _ in range(rows)]
                self.n_tokens = 0

            def reset(self):
                self.n_tokens = 0

            def tokenize(self, text, add_bos=False):
                # Token id = primer byte del texto; suficiente para tests.
                return [text[0] if isinstance(text, bytes) else ord(text[0])]

            def eval(self, tokens):
                self.n_tokens = len(tokens)

        sys.modules["numpy"] = _FakeNumpy()
        sys.modules["llama_cpp"] = type("_llama_cpp", (), {"Llama": _FakeLlama})()

    def tearDown(self):
        if self._real_llama is not None:
            sys.modules["llama_cpp"] = self._real_llama
        else:
            sys.modules.pop("llama_cpp", None)
        if self._real_numpy is not None:
            sys.modules["numpy"] = self._real_numpy
        else:
            sys.modules.pop("numpy", None)
        if self._real_model_env is not None:
            os.environ["JEV_MODEL_PATH"] = self._real_model_env
        if self._real_temp_env is not None:
            os.environ["JEV_TEMPERATURE"] = self._real_temp_env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client(self):
        return self.jl.JevLlama(model_path=str(self.model_path), n_ctx=128)

    @staticmethod
    def _set_logit(client, token: str, value: float) -> None:
        for row in client.model.scores:
            row[ord(token)] = value

    def test_constructor_activa_logits_all(self):
        client = self._client()
        self.assertIs(client.model._kwargs.get("logits_all"), True)

    def test_jev_model_path_se_usa_por_defecto(self):
        os.environ["JEV_MODEL_PATH"] = str(self.model_path)
        client = self.jl.JevLlama()
        self.assertEqual(client.model_path, self.model_path)

    def test_jev_temperature_desde_entorno(self):
        os.environ["JEV_TEMPERATURE"] = "2.5"
        client = self._client()
        self.assertAlmostEqual(client.temperature, 2.5)

    def test_softmax_temperatura_suaviza_y_valida(self):
        sharp = self.jl._softmax([0.0, 2.0], 1.0)
        soft = self.jl._softmax([0.0, 2.0], 4.0)
        self.assertLess(max(soft), max(sharp))
        self.assertAlmostEqual(sum(soft), 1.0, places=9)
        with self.assertRaises(ValueError):
            self.jl._softmax([0.0, 1.0], 0.0)

    def test_temperature_en_rango_desde_constructor(self):
        client = self.jl.JevLlama(model_path=str(self.model_path), temperature=3.0)
        self.assertAlmostEqual(client.temperature, 3.0)
        with self.assertRaises(ValueError):
            self.jl.JevLlama(model_path=str(self.model_path), temperature=-1.0)

    def test_noul_preferencia_yes(self):
        client = self._client()
        self._set_logit(client, "y", 5.0)
        self._set_logit(client, "n", 1.0)
        result = client.decide("test", {"q": {"type": "noul", "instructions": "Is it yes?"}})
        self.assertEqual(result["q"]["type"], "noul")
        self.assertGreater(result["q"]["noul"], 0.5)
        self.assertIn("confidence", result["q"])
        self.assertAlmostEqual(sum(result["q"]["probabilities"].values()), 1.0, places=5)

    def test_confidence_en_rango(self):
        client = self._client()
        self._set_logit(client, "y", 5.0)
        self._set_logit(client, "n", 1.0)
        result = client.decide("test", {"q": {"type": "noul", "instructions": "Is it yes?"}})
        self.assertGreaterEqual(result["q"]["confidence"], 0.0)
        self.assertLessEqual(result["q"]["confidence"], 1.0)

    def test_choice_selecciona_opcion_con_mayor_logit(self):
        client = self._client()
        self._set_logit(client, "a", 2.0)
        self._set_logit(client, "b", 5.0)
        self._set_logit(client, "c", 1.0)
        result = client.decide("test", {
            "q": {
                "type": "choice",
                "instructions": "Pick one",
                "criteria": {"a": "first", "b": "second", "c": "third"},
            }
        })
        self.assertEqual(result["q"]["type"], "choice")
        self.assertEqual(result["q"]["choice"], "b")
        self.assertEqual(len(result["q"]["probabilities"]), 3)

    def test_score_calcula_puntuacion_ponderada(self):
        client = self._client()
        self._set_logit(client, "0", 1.0)
        self._set_logit(client, "1", 2.0)
        self._set_logit(client, "2", 5.0)
        self._set_logit(client, "3", 1.0)
        result = client.decide("test", {
            "q": {
                "type": "score",
                "instructions": "How severe?",
                "criteria": ["low", "medium", "high", "critical"],
            }
        })
        self.assertEqual(result["q"]["type"], "score")
        self.assertGreater(result["q"]["score"], 1.0)
        self.assertIn("legend", result["q"])

    def test_tipo_desconocido_lanza_valueerror(self):
        client = self._client()
        with self.assertRaises(ValueError):
            client.decide("test", {"q": {"type": "unknown"}})

    def test_modelo_inexistente_lanza_filenotfound(self):
        missing = self.tmp / "no_existe.gguf"
        with self.assertRaises(FileNotFoundError):
            self.jl.JevLlama(model_path=str(missing))


class TestJevCalibration(unittest.TestCase):
    """REQ-011: matematicas de calibracion (NLL/Brier/ECE/temperatura)."""

    def test_softmax_normaliza_y_temperatura(self):
        p1 = jc.softmax([1.0, 1.0], 1.0)
        self.assertAlmostEqual(sum(p1), 1.0, places=9)
        self.assertAlmostEqual(p1[0], 0.5, places=9)
        with self.assertRaises(ValueError):
            jc.softmax([1.0], 0.0)

    def test_temperature_scale_suaviza_sin_cambiar_argmax(self):
        base = [0.9, 0.07, 0.03]
        scaled = jc.temperature_scale(base, 3.0)
        self.assertAlmostEqual(sum(scaled), 1.0, places=9)
        self.assertEqual(base.index(max(base)), scaled.index(max(scaled)))
        self.assertLess(max(scaled), max(base))

    def test_brier_y_nll_valores_conocidos(self):
        self.assertAlmostEqual(jc.brier([1.0, 0.0], 0), 0.0, places=12)
        self.assertAlmostEqual(jc.nll([1.0, 0.0], 0), 0.0, places=6)
        self.assertAlmostEqual(jc.brier([0.5, 0.5], 1), 0.5, places=12)
        self.assertAlmostEqual(jc.nll([0.5, 0.5], 1), math.log(2), places=6)

    def test_accuracy(self):
        probs = [[0.9, 0.1], [0.2, 0.8], [0.6, 0.4]]
        self.assertAlmostEqual(jc._accuracy(probs, [0, 1, 1]), 2 / 3, places=9)

    def test_wilson_ci(self):
        lo, hi = jc.wilson_ci(8, 10)
        self.assertLess(lo, 0.8)
        self.assertGreater(hi, 0.8)
        self.assertEqual(jc.wilson_ci(0, 0), (0.0, 0.0))

    def test_evaluate_incluye_ci(self):
        records = [{"probs": [0.9, 0.1], "label_idx": 0}, {"probs": [0.2, 0.8], "label_idx": 0}]
        metricas = jc.evaluate(records, 1.0)
        self.assertIn("accuracy_ci95", metricas)
        self.assertEqual(len(metricas["accuracy_ci95"]), 2)

    def test_ece_adaptativo(self):
        self.assertAlmostEqual(jc.ece([[1.0, 0.0], [1.0, 0.0]], [0, 0], adaptativo=True), 0.0, places=9)
        mixto = [[0.9, 0.1], [0.6, 0.4], [0.2, 0.8], [0.5, 0.5]]
        valor = jc.ece(mixto, [0, 0, 0, 1], adaptativo=True)
        self.assertGreaterEqual(valor, 0.0)
        self.assertLessEqual(valor, 1.0)
        self.assertIn("ece_adaptativo", jc.evaluate(
            [{"probs": [0.9, 0.1], "label_idx": 0}], 1.0))

    def test_run_cases_cache(self):
        class _Fake:
            def __init__(self):
                self.model_path = Path("m.gguf")
                self.llamadas = 0

            def decide(self, state, questions):
                self.llamadas += 1
                return {"q": {"probabilities": {"yes": 0.6, "no": 0.4}}}

        caso = {"id": "N01", "tipo": "noul", "estado": "e", "instrucciones": "i", "esperado": "yes"}
        fake, cache = _Fake(), {}
        jc.run_cases(fake, [caso], cache)
        jc.run_cases(fake, [caso], cache)
        self.assertEqual(fake.llamadas, 1)

    def test_sembrar_cache_desde_informe(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            informe = tmp / "r.json"
            informe.write_text(json.dumps({
                "modelo": "m.gguf",
                "records": [{"id": "N01", "probs": [0.6, 0.4], "label_idx": 0}],
            }), encoding="utf-8")
            cache: dict = {}
            self.assertEqual(jc.sembrar_cache_desde_informe(cache, informe), 1)
            self.assertIn("m.gguf|N01", cache)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_cache_roundtrip_calibracion(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            path = tmp / "c.json"
            jc.guardar_cache({"k": 1}, path)
            self.assertEqual(jc.cargar_cache(path), {"k": 1})
            self.assertEqual(jc.cargar_cache(tmp / "no.json"), {})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_bootstrap_ci_determinista(self):
        valores = [1.0, 2.0, 3.0, 4.0]
        primero = jc.bootstrap_ci(valores)
        segundo = jc.bootstrap_ci(valores)
        self.assertEqual(primero, segundo)
        lo, hi = primero
        self.assertLessEqual(lo, hi)
        self.assertEqual(jc.bootstrap_ci([]), (0.0, 0.0))

    def test_valores_por_caso(self):
        records = [{"probs": [1.0, 0.0], "label_idx": 0}, {"probs": [0.5, 0.5], "label_idx": 1}]
        nlls, briers = jc._valores_por_caso(records, 1.0)
        self.assertEqual(len(nlls), 2)
        self.assertEqual(len(briers), 2)
        self.assertAlmostEqual(briers[0], 0.0, places=9)

    def test_ece_valor_conocido(self):
        probs = [[0.9, 0.1], [0.9, 0.1]]
        self.assertAlmostEqual(jc.ece(probs, [0, 1]), 0.4, places=9)
        self.assertAlmostEqual(jc.ece([], []), 0.0, places=9)

    def test_fit_temperature_corrige_overconfidence(self):
        # accuracy 0.5 con confianza 0.98 => T > 1 reduce el NLL.
        probs = [[0.98, 0.02], [0.98, 0.02], [0.98, 0.02], [0.98, 0.02]]
        records = [{"probs": p, "label_idx": y} for p, y in zip(probs, [0, 1, 0, 1])]
        t = jc.fit_temperature(records)
        self.assertGreater(t, 1.0)
        self.assertLess(jc.evaluate(records, t)["nll"], jc.evaluate(records, 1.0)["nll"])

    def test_load_set_y_validacion(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            good = tmp / "s.json"
            good.write_text(json.dumps({"casos": [
                {"id": "X1", "tipo": "noul", "estado": "e", "instrucciones": "i", "esperado": "yes"}
            ]}), encoding="utf-8")
            casos = jc.load_set(good)
            self.assertEqual(len(casos), 1)
            self.assertEqual(jc._options_and_label(casos[0]), (["yes", "no"], 0))

            bad = tmp / "b.json"
            bad.write_text(json.dumps({"casos": [
                {"id": "X2", "tipo": "noul", "estado": "e", "instrucciones": "i", "esperado": "quizas"}
            ]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                jc._options_and_label(jc.load_set(bad)[0])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _FakeJevClient:
    """Cliente Jev simulado para REQ-012: probabilidades fijas, sin modelo."""

    def __init__(self, confianza: float = 0.6):
        self.confianza = confianza

    def decide(self, state, questions):
        respuestas = {}
        for campo, question in questions.items():
            if question["type"] == "choice":
                opciones = list(question["criteria"])
                ganador = opciones[-1]
                probs = {
                    o: (0.7 if o == ganador else 0.3 / (len(opciones) - 1)) for o in opciones
                }
                respuestas[campo] = {
                    "type": "choice",
                    "choice": ganador,
                    "probabilities": probs,
                    "confidence": self.confianza,
                }
            else:
                probs = {str(i): [0.05, 0.1, 0.7, 0.15][i] for i in range(4)}
                respuestas[campo] = {
                    "type": "score",
                    "score": 2.0,
                    "probabilities": probs,
                    "confidence": self.confianza,
                }
        return respuestas


class TestJevPillars(unittest.TestCase):
    """REQ-012: integracion de Jev con los tres pilares (sin modelo)."""

    ACC = {"choice": 0.9167, "score": 0.4167}

    @staticmethod
    def _ns(req=None, lesson_id=None, file=None, text=None):
        return argparse.Namespace(req=req, id=lesson_id, file=file, text=text)

    def test_requisitos_esquema_y_decision(self):
        salida = jp.ejecutar("requisitos", "REQ-011", "texto", _FakeJevClient(), 0.5, self.ACC)
        self.assertEqual(salida["tipo"], "choice")
        self.assertFalse(salida["experimental"])
        decision = salida["decisiones"][0]
        self.assertEqual(
            set(decision),
            {
                "id",
                "campo",
                "tipo",
                "decision",
                "propuesta",
                "probabilities",
                "confidence",
                "revision_humana",
                "accuracy_referencia",
                "experimental",
            },
        )
        self.assertEqual(decision["campo"], "prioridad")
        self.assertEqual(decision["decision"], "Alta")
        self.assertAlmostEqual(sum(decision["probabilities"].values()), 1.0, places=6)

    def test_conocimiento_score_marca_experimental(self):
        salida = jp.ejecutar("conocimiento", "frag", "texto", _FakeJevClient(), 0.5, self.ACC)
        self.assertEqual(salida["tipo"], "score")
        # accuracy score 0.417 < 0.6 => experimental (criterio 6).
        self.assertTrue(salida["experimental"])
        self.assertTrue(salida["decisiones"][0]["experimental"])

    def test_lecciones_dos_decisiones(self):
        salida = jp.ejecutar("lecciones", "LSN-008", "texto", _FakeJevClient(), 0.5, self.ACC)
        campos = [d["campo"] for d in salida["decisiones"]]
        self.assertEqual(campos, ["fase", "categoria"])
        self.assertFalse(salida["experimental"])

    def test_umbral_marca_revision_humana_y_decision_nula(self):
        salida = jp.ejecutar("requisitos", "REQ-011", "texto", _FakeJevClient(0.4), 0.5, self.ACC)
        decision = salida["decisiones"][0]
        self.assertIsNone(decision["decision"])
        self.assertEqual(decision["propuesta"], "Alta")
        self.assertTrue(decision["revision_humana"])

    def test_umbral_limite_es_definitivo(self):
        salida = jp.ejecutar("requisitos", "REQ-011", "texto", _FakeJevClient(0.5), 0.5, self.ACC)
        decision = salida["decisiones"][0]
        self.assertFalse(decision["revision_humana"])
        self.assertEqual(decision["decision"], "Alta")

    def test_accuracy_desconocida_es_experimental(self):
        salida = jp.ejecutar("requisitos", "REQ-011", "texto", _FakeJevClient(), 0.5, {})
        self.assertIsNone(salida["accuracy_referencia"])
        self.assertTrue(salida["experimental"])

    def test_pilar_desconocido_lanza(self):
        with self.assertRaises(ValueError):
            jp.ejecutar("otro", "X", "texto", _FakeJevClient(), 0.5, self.ACC)

    def test_accuracy_por_tipo_lee_informe(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            report = tmp / "cal.json"
            report.write_text(
                json.dumps(
                    {"por_tipo_Trecomendada": {"choice": {"accuracy": 0.9}, "score": {"accuracy": 0.4}}}
                ),
                encoding="utf-8",
            )
            self.assertEqual(
                jp.accuracy_por_tipo(report), {"choice": 0.9, "score": 0.4}
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_accuracy_por_tipo_sin_informe(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(jp.accuracy_por_tipo(tmp / "no_existe.json"), {})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_accuracy_por_tipo_informe_invalido(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            report = tmp / "roto.json"
            report.write_text("{no json", encoding="utf-8")
            with self.assertRaises(ValueError):
                jp.accuracy_por_tipo(report)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_resolver_entrada_exige_opcion_unica(self):
        with self.assertRaises(ValueError):
            jp.resolver_entrada("requisitos", self._ns())
        with self.assertRaises(ValueError):
            jp.resolver_entrada("requisitos", self._ns(req="REQ-011", text="hola"))
        with self.assertRaises(ValueError):
            jp.resolver_entrada("conocimiento", self._ns(lesson_id="LSN-001"))
        with self.assertRaises(ValueError):
            jp.resolver_entrada("lecciones", self._ns())

    def test_resolver_entrada_texto(self):
        entry_id, texto = jp.resolver_entrada("conocimiento", self._ns(text="fragmento"))
        self.assertEqual((entry_id, texto), ("texto", "fragmento"))

    def test_resolver_entrada_lecciones_por_id(self):
        entry_id, texto = jp.resolver_entrada("lecciones", self._ns(lesson_id="LSN-001"))
        self.assertEqual(entry_id, "LSN-001")
        self.assertIn("Problema:", texto)

    def test_texto_desde_archivo_requisitos_no_filtra_prioridad(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            path = tmp / "REQ-999.md"
            path.write_text(
                "---\nid: REQ-999\nprioridad: Alta\n---\n# REQ-999\nCuerpo del requisito.\n",
                encoding="utf-8",
            )
            _, texto = jp._texto_desde_archivo(path, "requisitos")
            self.assertNotIn("prioridad", texto)
            self.assertIn("Cuerpo del requisito.", texto)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestADRValidator(unittest.TestCase):
    """REQ-013: validacion de ADR y auditoria de sesgos (Pilar 4)."""

    ADR_VALIDO = (
        "---\nid: ADR-100\ntitulo: Prueba\nestado: Aceptado\nfecha: 2026-09-19\n---\n"
        "# ADR-100: Prueba\n\n## Contexto\n\nProblema con 3 GB de datos.\n\n"
        "## Alternativas consideradas\n\n- **A**: opcion 1.\n- **B**: opcion 2.\n\n"
        "## Decision\n\nSe elige A por 2 razones.\n\n"
        "## Consecuencias\n\n- Positivas: 1.\n\n"
        "## Supuestos\n\n- Vale 1.\n\n"
        "## Metricas de exito\n\n- p99 < 200 ms.\n"
    )

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _adr(self, content: str, name: str = "ADR-100-prueba.md") -> Path:
        path = self.tmp / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_repo_real_sin_errores(self):
        errors, warnings = av.validate(ROOT / "docs" / "decisions")
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_adr_valido_temporal(self):
        self._adr(self.ADR_VALIDO)
        errors, warnings = av.validate(self.tmp)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_sin_frontmatter_es_error(self):
        self._adr("# sin frontmatter\n")
        errors, _ = av.validate(self.tmp)
        self.assertTrue(any("frontmatter" in e for e in errors))

    def test_falta_seccion_es_error(self):
        self._adr(self.ADR_VALIDO.replace("## Consecuencias\n\n- Positivas: 1.\n", ""))
        errors, _ = av.validate(self.tmp)
        self.assertTrue(any("consecuencias" in e.lower() for e in errors))

    def test_id_no_coincide_es_error(self):
        self._adr(self.ADR_VALIDO.replace("id: ADR-100", "id: ADR-999"))
        errors, _ = av.validate(self.tmp)
        self.assertTrue(any("no coincide" in e for e in errors))

    def test_estado_invalido_es_error(self):
        self._adr(self.ADR_VALIDO.replace("estado: Aceptado", "estado: Quizas"))
        errors, _ = av.validate(self.tmp)
        self.assertTrue(any("estado" in e for e in errors))

    def test_fecha_invalida_es_error(self):
        self._adr(self.ADR_VALIDO.replace("fecha: 2026-09-19", "fecha: 19-09-2026"))
        errors, _ = av.validate(self.tmp)
        self.assertTrue(any("fecha" in e for e in errors))

    def test_id_duplicado_es_error(self):
        self._adr(self.ADR_VALIDO, name="ADR-100-a.md")
        self._adr(self.ADR_VALIDO, name="ADR-100-b.md")
        errors, _ = av.validate(self.tmp)
        self.assertTrue(any("duplicado" in e for e in errors))

    def test_una_alternativa_alerta(self):
        self._adr(self.ADR_VALIDO.replace("- **B**: opcion 2.\n", ""))
        _, warnings = av.validate(self.tmp)
        self.assertTrue(any("alternativas" in w for w in warnings))

    def test_adjetivo_sin_metrica_alerta(self):
        self._adr(self.ADR_VALIDO.replace("Problema con 3 GB de datos.", "El sistema es escalable."))
        _, warnings = av.validate(self.tmp)
        self.assertTrue(any("escalable" in w for w in warnings))

    def test_sin_adjetivo_en_contexto_no_alerta(self):
        # Sin adjetivo ambiguo ni metrica en Contexto no debe haber alerta (mata
        # el mutante and->or de la linea 128).
        self._adr(self.ADR_VALIDO.replace("Problema con 3 GB de datos.", "Problema sencillo."))
        _, warnings = av.validate(self.tmp)
        self.assertEqual(warnings, [])

    def test_afirmacion_absoluta_alerta(self):
        self._adr(self.ADR_VALIDO.replace("Se elige A por 2 razones.", "Esto siempre funciona."))
        _, warnings = av.validate(self.tmp)
        self.assertTrue(any("siempre" in w for w in warnings))

    def test_strict_falla_con_alertas(self):
        self._adr(self.ADR_VALIDO.replace("- **B**: opcion 2.\n", ""))
        self.assertEqual(av.main(["--dir", str(self.tmp), "--strict"]), 1)
        self.assertEqual(av.main(["--dir", str(self.tmp)]), 0)

    def test_dir_inexistente_falla(self):
        self.assertEqual(av.main(["--dir", str(self.tmp / "no_existe")]), 1)


class TestAutoAudit(unittest.TestCase):
    """REQ-014: auto-auditoria (sesgos, evidencias, decisiones, tests, IA)."""

    _TEST_OK = (
        "import unittest\n\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_ok(self):\n"
        "        self.assertEqual(1 + 1, 2)\n"
    )

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write(self, name: str, content: str) -> Path:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_sesgos_detecta_garantia_absoluta(self):
        path = self._write("doc.md", "El sistema garantiza el exito total.\n")
        hallazgos = aa.auditar_sesgos([path])
        self.assertTrue(any("garantia absoluta" in h for h in hallazgos))

    def test_sesgos_ignora_lineas_de_reglas(self):
        path = self._write("doc.md", "### P0.1 Nunca afirmes sin evidencia\n")
        self.assertEqual(aa.auditar_sesgos([path]), [])

    def test_sesgos_detecta_realismo_naif(self):
        path = self._write("doc.md", "Obviamente esta es la mejor solucion.\n")
        hallazgos = aa.auditar_sesgos([path])
        self.assertTrue(any("realismo naif" in h for h in hallazgos))

    def test_evidencias_sin_sbom_es_error(self):
        errors, _ = aa.auditar_evidencias(docs_dir=self.tmp)
        self.assertTrue(any("no hay SBOM" in e for e in errors))

    def test_evidencias_sbom_antiguo_alerta(self):
        self._write("SBOM-2020-01-01.spdx.json", "{}")
        errors, warnings = aa.auditar_evidencias(docs_dir=self.tmp)
        self.assertEqual(errors, [])
        self.assertTrue(any("SBOM de" in w for w in warnings))

    def test_evidencias_sbom_reciente_ok(self):
        import datetime

        hoy = datetime.date.today().isoformat()
        self._write(f"SBOM-{hoy}.spdx.json", "{}")
        errors, warnings = aa.auditar_evidencias(docs_dir=self.tmp)
        self.assertEqual((errors, warnings), ([], []))

    def test_decisiones_req_draft(self):
        self._write("req/REQ-999.md", "---\nid: REQ-999\nestado: Draft\n---\n# x\n")
        (self.tmp / "adr").mkdir()
        warns = aa.auditar_decisiones(req_dir=self.tmp / "req", adr_dir=self.tmp / "adr")
        self.assertTrue(any("REQ-999.md" in w and "Draft" in w for w in warns))

    def test_decisiones_adr_propuesto(self):
        self._write("adr/ADR-999-x.md", "---\nid: ADR-999\nestado: Propuesto\n---\n# x\n")
        (self.tmp / "req").mkdir()
        warns = aa.auditar_decisiones(req_dir=self.tmp / "req", adr_dir=self.tmp / "adr")
        self.assertTrue(any("ADR-999" in w and "Propuesto" in w for w in warns))

    def test_tests_tautologia_es_error(self):
        test = self._write(
            "t.py",
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def test_x(self):\n        self.assertTrue(True)\n",
        )
        scripts = self.tmp / "scripts"
        scripts.mkdir()
        errors, _ = aa.auditar_tests(test_file=test, scripts_dir=scripts)
        self.assertTrue(any("tautologica" in e for e in errors))

    def test_tests_sin_asercion_alerta(self):
        test = self._write(
            "t.py",
            "import unittest\n\n\nclass T(unittest.TestCase):\n"
            "    def test_y(self):\n        x = 1 + 1\n",
        )
        scripts = self.tmp / "scripts"
        scripts.mkdir()
        _, warnings = aa.auditar_tests(test_file=test, scripts_dir=scripts)
        self.assertTrue(any("sin asercion" in w for w in warnings))

    def test_except_pass_es_error(self):
        test = self._write("t.py", self._TEST_OK)
        self._write("scripts/z.py", "def f():\n    try:\n        x = 1\n    except Exception:\n        pass\n")
        errors, _ = aa.auditar_tests(test_file=test, scripts_dir=self.tmp / "scripts")
        self.assertTrue(any("except con 'pass'" in e for e in errors))

    def test_trailer_asistido(self):
        self.assertTrue(aa._tiene_trailer("Assisted-by: opencode"))
        self.assertTrue(aa._tiene_trailer("Generated-by: x"))
        self.assertFalse(aa._tiene_trailer("commit normal sin trailer"))

    def test_repo_real_sin_errores_de_tests(self):
        errors, _ = aa.auditar_tests()
        self.assertEqual(errors, [])

    def test_vulns_con_fix(self):
        req = self._write("requirements.txt", "x\n")
        hallazgos = [{"name": "x", "version": "1.0", "id": "CVE-1", "fix_versions": ["1.1"]}]
        errors, warnings = aa.auditar_vulns(requirements=req, ejecutar=lambda: hallazgos)
        self.assertEqual(errors, [])
        self.assertTrue(any("CVE-1" in w and "fix: 1.1" in w for w in warnings))

    def test_vulns_sin_parche(self):
        req = self._write("requirements.txt", "x\n")
        hallazgos = [{"name": "x", "version": "1.0", "id": "CVE-2", "fix_versions": []}]
        _, warnings = aa.auditar_vulns(requirements=req, ejecutar=lambda: hallazgos)
        self.assertTrue(any("sin parche" in w for w in warnings))

    def test_vulns_dedupe(self):
        req = self._write("requirements.txt", "x\n")
        dup = {"name": "x", "version": "1.0", "id": "CVE-3", "fix_versions": []}
        _, warnings = aa.auditar_vulns(requirements=req, ejecutar=lambda: [dup, dict(dup)])
        self.assertEqual(len(warnings), 1)

    def test_vulns_sin_escaner(self):
        req = self._write("requirements.txt", "x\n")
        with mock.patch.object(aa, "_scanner_disponible", return_value=(None, None)):
            errors, warnings = aa.auditar_vulns(requirements=req)
        self.assertEqual(errors, [])
        self.assertTrue(any("sin escaner" in w for w in warnings))

    def test_vulns_archivo_inexistente(self):
        errors, _ = aa.auditar_vulns(requirements=self.tmp / "no_existe.txt")
        self.assertTrue(any("no existe" in e for e in errors))

    def test_vulns_fallo_scanner(self):
        def falla():
            raise RuntimeError("boom")

        req = self._write("requirements.txt", "x\n")
        errors, _ = aa.auditar_vulns(requirements=req, ejecutar=falla)
        self.assertTrue(any("fallo el escaneo" in e for e in errors))

    def test_calibracion_set_valido(self):
        errors, _ = aa.auditar_calibracion()
        self.assertEqual(errors, [])

    def test_calibracion_duplicado_es_error(self):
        s = self._write("s.json", json.dumps({"casos": [
            {"id": "N01", "tipo": "noul", "estado": "e", "instrucciones": "i", "esperado": "yes"},
            {"id": "N01", "tipo": "noul", "estado": "otro", "instrucciones": "i", "esperado": "no"},
        ]}))
        c = self._write("c.json", json.dumps({"casos": []}))
        errors, _ = aa.auditar_calibracion(s, c)
        self.assertTrue(any("duplicado" in e for e in errors))

    def test_main_all_en_verde(self):
        self.assertEqual(aa.main(["all"]), 0)


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
                "test_ecosistema.TestADRValidator", max_mutantes=8,
            )
        finally:
            shutil.rmtree(copia, ignore_errors=True)
        self.assertGreaterEqual(resultado["score"], 0.8)


class TestJevReview(unittest.TestCase):
    """REQ-016: revision humana asistida de clasificaciones Jev (UI/report)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_construir_items_requisitos(self):
        items = jr.construir_items(["requisitos"], limit=3)
        self.assertEqual(len(items), 3)
        self.assertTrue(all(i["pilar"] == "requisitos" for i in items))
        self.assertTrue(all(i["id"].startswith("REQ-") for i in items))

    def test_construir_items_lecciones(self):
        items = jr.construir_items(["lecciones"], limit=2)
        self.assertTrue(all(i["pilar"] == "lecciones" for i in items))

    def test_clasificar_con_cliente_falso(self):
        items = [{"pilar": "requisitos", "id": "REQ-999", "texto": "texto"}]
        filas = jr.clasificar(items, jr._ClienteFalso(), {"choice": 0.9})
        self.assertEqual(len(filas), 1)
        fila = filas[0]
        self.assertEqual(fila["campo"], "prioridad")
        self.assertIn(fila["propuesta"], fila["opciones"])
        self.assertEqual(fila["estado"], "pendiente")

    def test_aplicar_decisiones(self):
        fila = {"propuesta": "Alta", "estado": "pendiente", "decision_final": None}
        jr.aplicar_decision(fila, "y")
        self.assertEqual((fila["estado"], fila["decision_final"]), ("ok", "Alta"))
        fila2 = {"propuesta": "Alta", "estado": "pendiente", "decision_final": None}
        jr.aplicar_decision(fila2, "n", "Baja")
        self.assertEqual((fila2["estado"], fila2["decision_final"]), ("corregir", "Baja"))
        fila3 = {"propuesta": "Alta", "estado": "pendiente", "decision_final": None}
        jr.aplicar_decision(fila3, "s")
        self.assertEqual((fila3["estado"], fila3["decision_final"]), ("saltar", None))

    def test_guardar_revision(self):
        filas = [
            {"estado": "ok"}, {"estado": "corregir"}, {"estado": "pendiente"}, {"estado": "saltar"}
        ]
        path = self.tmp / "rev.json"
        jr.guardar_revision(filas, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["total"], 4)
        self.assertEqual(data["ok"], 1)
        self.assertEqual(data["corregir"], 1)
        self.assertEqual(data["pendiente"], 1)
        self.assertEqual(data["saltar"], 1)

    def test_main_report_fake(self):
        out = self.tmp / "rev.json"
        os.environ["JEV_REVIEW_REPORT"] = str(out)
        os.environ["JEV_REVIEW_CACHE"] = str(self.tmp / "cache.json")
        try:
            self.assertEqual(jr.main(["--report", "--fake", "--limit", "2"]), 0)
            self.assertTrue(out.exists())
        finally:
            os.environ.pop("JEV_REVIEW_REPORT", None)
            os.environ.pop("JEV_REVIEW_CACHE", None)
        self.assertNotIn(".docs/requirements", str(out))  # no escribe en los documentos

    def test_cache_evita_recalcular(self):
        llamadas = {"n": 0}

        class _Contador(jr._ClienteFalso):
            def decide(self, state, questions):
                llamadas["n"] += 1
                return super().decide(state, questions)

        item = {"pilar": "requisitos", "id": "REQ-999", "texto": "texto"}
        cache: dict = {}
        primera = jr.filas_de_item(item, _Contador(), {"choice": 0.9}, cache)
        segunda = jr.filas_de_item(item, _Contador(), {"choice": 0.9}, cache)
        self.assertEqual(llamadas["n"], 1)
        self.assertEqual(primera[0]["propuesta"], segunda[0]["propuesta"])

    def test_clave_cache_estable(self):
        a = {"pilar": "lecciones", "id": "LSN-1", "texto": "mismo"}
        b = {"pilar": "lecciones", "id": "LSN-1", "texto": "mismo"}
        self.assertEqual(jr._clave(a), jr._clave(b))

    def test_cache_roundtrip(self):
        path = self.tmp / "cache.json"
        jr.guardar_cache({"k": [{"campo": "prioridad"}]}, str(path))
        self.assertEqual(jr.cargar_cache(str(path))["k"][0]["campo"], "prioridad")
        self.assertEqual(jr.cargar_cache(str(self.tmp / "no.json")), {})

    def test_construir_items_calibracion(self):
        items = jr.construir_items(["calibracion"], limit=2, calibracion=True)
        self.assertEqual(len(items), 2)
        self.assertTrue(all("caso" in i and i["pilar"] == "calibracion" for i in items))

    def test_filas_calibracion_no_usa_modelo(self):
        items = jr.construir_items(["calibracion"], limit=1, calibracion=True)
        filas = jr.filas_de_item(items[0], client=None, accuracy={})
        self.assertEqual(filas[0]["propuesta"], str(items[0]["caso"]["esperado"]))
        self.assertIsNone(filas[0]["confianza"])
        self.assertTrue(filas[0]["opciones"])

    def test_main_calibracion_report(self):
        out = self.tmp / "cal.json"
        os.environ["JEV_REVIEW_REPORT"] = str(out)
        os.environ["JEV_REVIEW_CACHE"] = str(self.tmp / "cache.json")
        try:
            self.assertEqual(jr.main(["--calibracion", "--report", "--limit", "3"]), 0)
            self.assertTrue(out.exists())
        finally:
            os.environ.pop("JEV_REVIEW_REPORT", None)
            os.environ.pop("JEV_REVIEW_CACHE", None)


class TestDiagnostico(unittest.TestCase):
    """REQ-017: diagnostico de los cuatro pilares en proyectos externos."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_repo_real_solido(self):
        reporte = diag.evaluar(ROOT)
        nombres = [p["pilar"] for p in reporte["pilares"]]
        self.assertEqual(nombres, ["requisitos", "conocimiento", "lecciones", "pilar4", "higiene"])
        self.assertGreaterEqual(reporte["puntuacion_global"], 80)

    def test_dir_vacio_ausente_con_sugerencias(self):
        reporte = diag.evaluar(self.tmp)
        self.assertEqual(reporte["puntuacion_global"], 0)
        self.assertTrue(reporte["sugerencias"])

    def test_no_escribe_en_el_objetivo(self):
        (self.tmp / "README.md").write_text("# x\n", encoding="utf-8")
        antes = sorted(p.name for p in self.tmp.rglob("*"))
        diag.evaluar(self.tmp)
        despues = sorted(p.name for p in self.tmp.rglob("*"))
        self.assertEqual(antes, despues)

    def test_min_score(self):
        self.assertEqual(diag.main(["--root", str(self.tmp), "--min-score", "50"]), 1)
        self.assertEqual(diag.main(["--root", str(self.tmp)]), 0)

    def test_dir_inexistente(self):
        self.assertEqual(diag.main(["--root", str(self.tmp / "no_existe")]), 1)


class TestJevCalibrationMerge(unittest.TestCase):
    """REQ-018: fusion idempotente de candidatos aprobados en el set."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.set_path = self.tmp / "set.json"
        self.cand_path = self.tmp / "cand.json"
        self.set_path.write_text(json.dumps({
            "version": 2,
            "casos": [{"id": "N01", "tipo": "noul", "esperado": "yes"}],
        }), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _cand(self, estado="aprobado", casos=None):
        self.cand_path.write_text(json.dumps({
            "estado": estado,
            "casos": casos if casos is not None else [
                {"id": "N99", "tipo": "noul", "estado": "e", "instrucciones": "i", "esperado": "yes"},
                {"id": "C99", "tipo": "choice", "estado": "e", "instrucciones": "i",
                 "criterios": {"requisitos": "x", "verificacion": "y"}, "esperado": "requisitos"},
            ],
        }), encoding="utf-8")

    def test_dry_run_no_escribe(self):
        self._cand()
        antes = self.set_path.read_text(encoding="utf-8")
        set_data = jcm._leer(self.set_path)
        resultado = jcm.fusionar(set_data, jcm._leer(self.cand_path), aplicar=False)
        self.assertEqual(len(resultado["nuevos"]), 2)
        self.assertEqual(set_data["version"], 2)
        self.assertEqual(self.set_path.read_text(encoding="utf-8"), antes)

    def test_aplicar_fusiona_y_subversiona(self):
        self._cand()
        set_data = jcm._leer(self.set_path)
        resultado = jcm.fusionar(set_data, jcm._leer(self.cand_path), aplicar=True)
        self.assertEqual(resultado["errores"], [])
        self.assertEqual(set_data["version"], 3)
        self.assertEqual([c["id"] for c in set_data["casos"]], ["N01", "N99", "C99"])
        self.assertEqual(len(set_data["revision_humana"]["lotes_fusionados"]), 1)

    def test_duplicado_es_error(self):
        self._cand(casos=[{"id": "N01", "tipo": "noul", "estado": "e", "instrucciones": "i", "esperado": "yes"}])
        resultado = jcm.fusionar(jcm._leer(self.set_path), jcm._leer(self.cand_path), aplicar=True)
        self.assertTrue(any("duplicado" in e for e in resultado["errores"]))

    def test_no_aprobado_es_error_salvo_forzar(self):
        self._cand(estado="pendiente_revision")
        error = jcm.fusionar(jcm._leer(self.set_path), jcm._leer(self.cand_path))
        self.assertTrue(any("no estan aprobados" in e for e in error["errores"]))
        forzado = jcm.fusionar(jcm._leer(self.set_path), jcm._leer(self.cand_path), forzar=True)
        self.assertEqual(forzado["errores"], [])

    def test_main_dry_run(self):
        self._cand()
        self.assertEqual(jcm.main(["--set", str(self.set_path), "--candidatos", str(self.cand_path)]), 0)
        self.assertEqual(self.set_path.read_text(encoding="utf-8").count('"version": 2'), 1)

    def test_caso_invalido_es_error(self):
        self._cand(casos=[{"id": "X1", "tipo": "noul", "estado": "e", "instrucciones": "i", "esperado": "quizas"}])
        resultado = jcm.fusionar(jcm._leer(self.set_path), jcm._leer(self.cand_path), aplicar=True)
        self.assertTrue(any("esperado invalido" in e for e in resultado["errores"]))

    def test_score_invalido_es_error(self):
        self._cand(casos=[{"id": "X2", "tipo": "score", "estado": "e", "instrucciones": "i",
                            "niveles": ["a", "b"], "esperado": 9}])
        resultado = jcm.fusionar(jcm._leer(self.set_path), jcm._leer(self.cand_path), aplicar=True)
        self.assertTrue(any("fuera de niveles" in e for e in resultado["errores"]))

    def test_escenario_duplicado_advertencia(self):
        self._cand(casos=[
            {"id": "N98", "tipo": "noul", "estado": "e", "instrucciones": "i", "esperado": "yes"},
            {"id": "N97", "tipo": "noul", "estado": "e", "instrucciones": "i", "esperado": "no"},
        ])
        resultado = jcm.fusionar(jcm._leer(self.set_path), jcm._leer(self.cand_path), aplicar=True)
        self.assertTrue(any("escenario duplicado" in a for a in resultado["advertencias"]))

    def test_choice_sin_criterios_es_error(self):
        self._cand(casos=[{"id": "X3", "tipo": "choice", "estado": "e", "instrucciones": "i",
                            "criterios": {}, "esperado": "requisitos"}])
        resultado = jcm.fusionar(jcm._leer(self.set_path), jcm._leer(self.cand_path))
        self.assertTrue(any("choice sin 'criterios'" in e for e in resultado["errores"]))

    def test_score_sin_niveles_es_error(self):
        self._cand(casos=[{"id": "X4", "tipo": "score", "estado": "e", "instrucciones": "i",
                            "niveles": [], "esperado": 0}])
        resultado = jcm.fusionar(jcm._leer(self.set_path), jcm._leer(self.cand_path))
        self.assertTrue(any("score sin 'niveles'" in e for e in resultado["errores"]))

    def test_escenarios_distintos_sin_advertencia(self):
        self._cand(casos=[
            {"id": "N96", "tipo": "noul", "estado": "uno", "instrucciones": "i", "esperado": "yes"},
            {"id": "N95", "tipo": "noul", "estado": "dos", "instrucciones": "i", "esperado": "no"},
        ])
        resultado = jcm.fusionar(jcm._leer(self.set_path), jcm._leer(self.cand_path))
        self.assertEqual(resultado["advertencias"], [])

    def test_ids_unicos_sin_error(self):
        self._cand(casos=[
            {"id": "N94", "tipo": "noul", "estado": "a", "instrucciones": "i", "esperado": "yes"},
            {"id": "N93", "tipo": "noul", "estado": "b", "instrucciones": "i", "esperado": "no"},
        ])
        resultado = jcm.fusionar(jcm._leer(self.set_path), jcm._leer(self.cand_path))
        self.assertEqual(resultado["errores"], [])

    def test_main_json_aplicar_conserva_acentos(self):
        self._cand(casos=[{"id": "N91", "tipo": "noul", "estado": "situación",
                            "instrucciones": "i", "esperado": "yes"}])
        with mock.patch.object(sys, "stdout", io.StringIO()):
            rc = jcm.main(["--set", str(self.set_path), "--candidatos", str(self.cand_path),
                           "--aplicar", "--json"])
        self.assertEqual(rc, 0)
        self.assertIn("situación", self.set_path.read_text(encoding="utf-8"))


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


class TestDownloadJevModel(unittest.TestCase):
    """Cubre el helper de descarga idempotente del modelo GGUF (REQ-011)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fake_response(self, chunks):
        class _Resp:
            status = 200
            headers = {"Content-Length": str(sum(len(c) for c in chunks))}

            def __init__(self):
                self._it = iter(chunks)

            def read(self, n=-1):
                return next(self._it, b"")

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False
        return _Resp()

    def test_human_unidades(self):
        self.assertEqual(djm._human(512), "512.0 B")
        self.assertEqual(djm._human(2048), "2.0 KB")
        self.assertEqual(djm._human(5 * 1024 ** 3), "5.0 GB")

    def test_main_modelo_existente_no_descarga(self):
        dest = self.tmp / "m.gguf"
        dest.write_bytes(b"x")
        argv = ["download_jev_model.py", "--dest", str(dest), "--yes"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "EXPECTED_BYTES", 1), \
                mock.patch.object(djm, "_download") as dl, mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(djm.main(), 0)
            dl.assert_not_called()

    def test_main_descarga_cuando_falta(self):
        dest = self.tmp / "m.gguf"
        argv = ["download_jev_model.py", "--dest", str(dest), "--yes"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "_download") as dl, \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(djm.main(), 0)
            dl.assert_called_once()

    def test_main_error_de_descarga_devuelve_1(self):
        dest = self.tmp / "m.gguf"
        argv = ["download_jev_model.py", "--dest", str(dest), "--yes"]
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(djm, "_download", side_effect=RuntimeError("boom")), \
                mock.patch.object(sys, "stdout", io.StringIO()), mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(djm.main(), 1)

    def test_download_escribe_chunks(self):
        dest = self.tmp / "m.gguf"
        with mock.patch.object(djm, "EXPECTED_BYTES", 1), \
                mock.patch("urllib.request.urlopen", return_value=self._fake_response([b"ab", b"cd"])), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            djm._download("http://x/m.gguf", dest, yes=True)
        self.assertEqual(dest.read_bytes(), b"abcd")

    def test_download_error_http_eleva_runtime_error(self):
        dest = self.tmp / "m.gguf"
        err = urllib.error.HTTPError("http://x", 404, "no encontrado", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            with self.assertRaises(RuntimeError):
                djm._download("http://x/m.gguf", dest, yes=True)

    def test_download_error_red_eleva_runtime_error(self):
        dest = self.tmp / "m.gguf"
        err = urllib.error.URLError("sin red")
        with mock.patch("urllib.request.urlopen", side_effect=err), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            with self.assertRaises(RuntimeError):
                djm._download("http://x/m.gguf", dest, yes=True)


if __name__ == "__main__":
    unittest.main()
