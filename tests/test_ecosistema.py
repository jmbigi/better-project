#!/usr/bin/env python3
"""Suite de tests del ecosistema better-project (REQ-001..REQ-006).

stdlib unittest, sin dependencias. Ejecutar:
    python3 -m unittest discover -s tests -q
Usa directorios temporales para no tocar el estado real del repo.
"""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import doc_validator as dv  # noqa: E402
import index_knowledge as ik  # noqa: E402
import lessons_extractor as le  # noqa: E402
import mcp_server as mcp  # noqa: E402
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

    def test_check_fresh(self):
        (self.know / "a.md").write_text("## A\ncontenido\n")
        ik.build_json_index()
        self.assertTrue(ik.check_fresh())
        (self.know / "b.md").write_text("## B\nnuevo\n")
        self.assertFalse(ik.check_fresh())

    def test_check_fresh_sin_indice(self):
        self.assertFalse(ik.check_fresh())


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


if __name__ == "__main__":
    unittest.main()
