#!/usr/bin/env python3
"""Tests de las herramientas de los 4 pilares: doc_validator, lessons_extractor,
index_knowledge, ADR (validador/backfill), diagnostico y auto-auditoria.
"""

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
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import adr_backfill as ab  # noqa: E402
import adr_validator as av  # noqa: E402
import auto_audit as aa  # noqa: E402
import diagnostico as diag  # noqa: E402
import doc_validator as dv  # noqa: E402
import index_knowledge as ik  # noqa: E402
import lessons_extractor as le  # noqa: E402

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
    tmp: Path
    reqs: Path
    old_req_dir: Path
    old_root: Path

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.reqs = self.tmp / ".docs" / "requirements"
        self.reqs.mkdir(parents=True)
        self.old_req_dir, self.old_root = dv.REQ_DIR, dv.ROOT
        self.old_ignore = list(dv.IGNORE)
        dv.REQ_DIR, dv.ROOT = self.reqs, self.tmp
        dv.IGNORE[:] = []

    def tearDown(self):
        dv.REQ_DIR, dv.ROOT = self.old_req_dir, self.old_root
        dv.IGNORE[:] = self.old_ignore

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

    def test_ignore_excluye_directorio_vendor(self):
        self._req(estado="Implementado")
        vendor = self.tmp / "scripts" / "tools"
        vendor.mkdir(parents=True)
        (vendor / "tool.py").write_text("# REQ-999\n", encoding="utf-8")
        self._code("# REQ-100\n")
        dv.IGNORE[:] = [Path("scripts/tools")]
        refs = dv.collect_code_refs()
        self.assertIn("REQ-100", refs)
        self.assertNotIn("REQ-999", refs)

    def test_ignore_no_excluye_directorio_hermano(self):
        self._req(estado="Implementado")
        src = self.tmp / "src"
        src.mkdir()
        (src / "app.py").write_text("# REQ-100\n", encoding="utf-8")
        tools = self.tmp / "tools"
        tools.mkdir()
        (tools / "x.py").write_text("# REQ-999\n", encoding="utf-8")
        dv.IGNORE[:] = [Path("scripts/tools")]
        refs = dv.collect_code_refs()
        self.assertIn("REQ-100", refs)
        self.assertIn("REQ-999", refs)

    def test_main_ignore_sin_valor_es_error(self):
        with mock.patch.object(sys, "argv", ["doc_validator.py", "--ignore"]), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(dv.main(), 1)

    def test_main_aplica_ignore(self):
        self._req(estado="Implementado")
        vendor = self.tmp / "scripts" / "tools"
        vendor.mkdir(parents=True)
        (vendor / "tool.py").write_text("# REQ-999\n", encoding="utf-8")
        self._code("# REQ-100\n")
        with mock.patch.object(sys, "argv", ["doc_validator.py", "--ignore", "scripts/tools"]), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(dv.main(), 0)

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

    def test_parse_yaml_con_yaml_disponible(self):
        # Verifica que _parse_yaml usa yaml.safe_load cuando esta disponible
        if not le.HAS_YAML:
            self.skipTest("PyYAML no instalado")
        with mock.patch.object(le, "HAS_YAML", True):
            data = le._parse_yaml("- id: LSN-001\n  estado: Resuelta\n")
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["id"], "LSN-001")

    def test_parse_yaml_sin_yaml(self):
        # Verifica que _parse_yaml usa _minimal_parser cuando yaml no esta disponible
        with mock.patch.object(le, "HAS_YAML", False):
            data = le._parse_yaml("- id: LSN-001\n  estado: Resuelta\n")
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["id"], "LSN-001")

    def test_validate_yaml_parse_error(self):
        # YAML invalido genera problema
        if not le.HAS_YAML:
            self.skipTest("PyYAML no instalado")
        self._yaml("{invalid yaml: [}")
        _, problems = le.validate()
        self.assertTrue(any("no se puede parsear" in p for p in problems))

    def test_validate_entrada_no_mapa(self):
        # Entrada que no es un mapa genera problema
        if not le.HAS_YAML:
            self.skipTest("PyYAML no instalado")
        self._yaml("- 'no es un mapa'\n")
        _, problems = le.validate()
        self.assertTrue(any("no es un mapa" in p for p in problems))

    def test_validate_fecha_normalizada(self):
        # La fecha se normaliza a string AAAA-MM-DD
        self._yaml(
            "- id: LSN-001\n  proyecto: P\n  fase: F\n  categoria: C\n  problema: a\n"
            "  recomendacion: b\n  estado: Resuelta\n  fecha: 2026-08-06\n"
        )
        lessons, _ = le.validate()
        self.assertEqual(lessons[0]["fecha"], "2026-08-06")

    def test_render_context_ordenado_por_id(self):
        datos = [
            {"id": "LSN-002", "proyecto": "P", "fase": "F", "categoria": "C",
             "problema": "prob2", "recomendacion": "rec2", "estado": "Resuelta", "fecha": "2026-08-06"},
            {"id": "LSN-001", "proyecto": "P", "fase": "F", "categoria": "C",
             "problema": "prob1", "recomendacion": "rec1", "estado": "Resuelta", "fecha": "2026-08-06"},
        ]
        texto = le.render_context(datos)
        # LSN-001 debe aparecer antes que LSN-002
        idx1 = texto.index("LSN-001")
        idx2 = texto.index("LSN-002")
        self.assertLess(idx1, idx2)

    def test_main_check_con_errores(self):
        self._yaml("- id: LSN-001\n  estado: Resuelta\n  fecha: 2026-08-06\n")
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["lessons_extractor.py", "--check"]), \
                mock.patch.object(sys, "stdout", buf), \
                mock.patch.object(le, "OUTPUT", self.tmp / "ctx.txt"):
            rc = le.main()
        self.assertEqual(rc, 1)
        self.assertIn("errores", buf.getvalue())

    def test_main_genera_contexto(self):
        self._yaml(
            "- id: LSN-001\n  proyecto: P\n  fase: F\n  categoria: C\n  problema: a\n"
            "  recomendacion: b\n  estado: Resuelta\n  fecha: 2026-08-06\n"
        )
        with mock.patch.object(sys, "argv", ["lessons_extractor.py"]), \
                mock.patch.object(le, "OUTPUT", self.tmp / "ctx.txt"), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            rc = le.main()
        self.assertEqual(rc, 0)
        self.assertTrue((self.tmp / "ctx.txt").exists())

    def test_main_no_genera_con_errores(self):
        self._yaml("- id: LSN-001\n  estado: Resuelta\n  fecha: 2026-08-06\n")
        with mock.patch.object(sys, "argv", ["lessons_extractor.py"]), \
                mock.patch.object(le, "OUTPUT", self.tmp / "ctx.txt"), \
                mock.patch.object(sys, "stdout", io.StringIO()), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            rc = le.main()
        self.assertEqual(rc, 1)
        self.assertFalse((self.tmp / "ctx.txt").exists())

    def test_clean_quita_comillas(self):
        self.assertEqual(le._clean('"valor"'), "valor")
        self.assertEqual(le._clean("'valor'"), "valor")
        self.assertEqual(le._clean("valor"), "valor")
        self.assertEqual(le._clean('  "valor"  '), "valor")

    def test_minimal_parser_valor_sin_comillas(self):
        datos = le._minimal_parser('- id: LSN-001\n  problema: valor sin comillas\n')
        self.assertEqual(datos[0]["problema"], "valor sin comillas")

    def test_minimal_parser_clave_valor_multilinea(self):
        datos = le._minimal_parser(
            '- id: LSN-001\n  problema: "linea 1"\n  recomendacion: "linea 2"\n'
        )
        self.assertEqual(datos[0]["problema"], "linea 1")
        self.assertEqual(datos[0]["recomendacion"], "linea 2")

    def test_has_yaml_refleja_importabilidad(self):
        # HAS_YAML debe seguir la importabilidad real de yaml: mata los
        # mutantes de asignacion del try/except del import.
        import importlib
        import types as _types
        fake = _types.ModuleType("yaml")
        with mock.patch.dict(sys.modules, {"yaml": fake}):
            self.assertTrue(importlib.reload(le).HAS_YAML)
        with mock.patch.dict(sys.modules, {"yaml": None}):
            self.assertFalse(importlib.reload(le).HAS_YAML)
        importlib.reload(le)  # restaurar el estado real del modulo

    def test_script_como_main_ejecuta_main(self):
        # Ejecutado como script, el bloque __main__ debe delegar en main().
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "lessons_extractor.py"), "--json"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertGreater(len(proc.stdout.strip()), 0)


class TestIndexKnowledge(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.know = self.tmp / "know"
        self.know.mkdir()
        self.storage = self.tmp / "storage"
        self.storage.mkdir()
        self.old = (
            ik.KNOWLEDGE_DIR, ik.STORAGE_DIR, ik.JSON_INDEX, ik.MANIFEST, ik.CHROMA_DIR, ik.SQLITE_DB,
        )
        ik.KNOWLEDGE_DIR = self.know
        ik.STORAGE_DIR = self.storage
        ik.JSON_INDEX = self.storage / "index.json"
        ik.MANIFEST = self.storage / "manifest.json"
        ik.CHROMA_DIR = self.storage / "chroma_db"
        ik.SQLITE_DB = self.storage / "knowledge.db"

    def tearDown(self):
        (
            ik.KNOWLEDGE_DIR, ik.STORAGE_DIR, ik.JSON_INDEX, ik.MANIFEST, ik.CHROMA_DIR, ik.SQLITE_DB,
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
        with mock.patch.object(ik, "_sqlite_available", return_value=False), \
                mock.patch.object(sys, "argv", ["index_knowledge.py", "search", "timeout"]), \
                mock.patch.object(sys, "stdout", buf):
            rc = ik.main()
        self.assertEqual(rc, 0)
        self.assertIn("timeout", buf.getvalue())

    def test_index_all_force_reconstruye(self):
        (self.know / "a.md").write_text("## A\ncontenido de prueba largo suficiente\n")
        ik.build_json_index()
        ik.JSON_INDEX.write_text("SENTINELA", encoding="utf-8")
        with mock.patch.object(ik, "_sqlite_available", return_value=False), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            ik.index_all(force=False)
        self.assertEqual(ik.JSON_INDEX.read_text(encoding="utf-8"), "SENTINELA")
        with mock.patch.object(ik, "_sqlite_available", return_value=False), \
                mock.patch.object(sys, "stdout", io.StringIO()):
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

    def test_vectors_normalizan_por_total_tokens(self):
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta\n")
        (self.know / "b.md").write_text(
            "## B\nalpha iota kappa lambda mu nu xi omicron pi rho sigma tau\n"
        )
        ik.build_json_index()
        data = json.loads(ik.JSON_INDEX.read_text(encoding="utf-8"))
        pesos = {c["archivo"]: v["alpha"] for c, v in zip(data["chunks"], data["vectors"])}
        self.assertGreater(pesos[".docs/knowledge/a.md"], pesos[".docs/knowledge/b.md"])

    def test_search_json_ordena_por_score(self):
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        (self.know / "b.md").write_text("## B\nalpha iota kappa lambda mu nu xi omicron\n")
        ik.build_json_index()
        resultados = ik.search_json("alpha beta")
        self.assertGreaterEqual(resultados[0]["score"], resultados[-1]["score"])
        self.assertIn("beta", resultados[0]["contenido"])

    def test_index_all_default_no_reconstruye(self):
        (self.know / "a.md").write_text("## A\ncontenido largo suficiente para chunk de prueba\n")
        ik.build_json_index()
        ik.JSON_INDEX.write_text("SENTINELA", encoding="utf-8")
        with mock.patch.object(ik, "_sqlite_available", return_value=False), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            ik.index_all()
        self.assertEqual(ik.JSON_INDEX.read_text(encoding="utf-8"), "SENTINELA")

    def test_index_all_crea_storage_con_padres(self):
        nuevo = self.tmp / "nested" / "storage"
        ik.STORAGE_DIR = nuevo
        ik.JSON_INDEX = nuevo / "index.json"
        ik.MANIFEST = nuevo / "manifest.json"
        ik.CHROMA_DIR = nuevo / "chroma_db"
        ik.SQLITE_DB = nuevo / "knowledge.db"
        (self.know / "a.md").write_text("## A\ncontenido largo suficiente para chunk de prueba\n")
        with mock.patch.object(ik, "_sqlite_available", return_value=False), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            ik.index_all()
        self.assertTrue(ik.JSON_INDEX.exists())

    def test_check_fresh_manifiesto_sin_indice(self):
        ik.MANIFEST.write_text("{}", encoding="utf-8")
        self.assertFalse(ik.JSON_INDEX.exists())
        self.assertFalse(ik.CHROMA_DIR.exists())
        self.assertFalse(ik.SQLITE_DB.exists())
        self.assertFalse(ik.check_fresh())

    def test_main_all_fuerza_reconstruccion(self):
        (self.know / "a.md").write_text("## A\ncontenido largo suficiente para chunk de prueba\n")
        ik.build_json_index()
        ik.JSON_INDEX.write_text("SENTINELA", encoding="utf-8")
        with mock.patch.object(ik, "_sqlite_available", return_value=False), \
                mock.patch.object(sys, "argv", ["index_knowledge.py", "--all"]), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(ik.main(), 0)
        self.assertNotEqual(ik.JSON_INDEX.read_text(encoding="utf-8"), "SENTINELA")

    def test_main_search_usa_json_si_chroma_no_disponible(self):
        (self.know / "a.md").write_text("## Timeout\nservidor timeout conexiones pool\n")
        ik.build_json_index()
        ik.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        with mock.patch.object(ik, "_chroma_available", return_value=False), \
                mock.patch.object(ik, "_sqlite_available", return_value=False), \
                mock.patch.object(sys, "argv", ["index_knowledge.py", "search", "timeout"]), \
                mock.patch.object(sys, "stdout", buf):
            rc = ik.main()
        self.assertEqual(rc, 0)
        self.assertIn("timeout", buf.getvalue())

    def test_sqlite_available_refleja_soporte_fts5(self):
        # El retorno debe coincidir con el soporte real de FTS5 del intérprete.
        import sqlite3 as _sqlite3
        try:
            conn = _sqlite3.connect(":memory:")
            conn.execute("CREATE VIRTUAL TABLE t USING fts5(c)")
            conn.close()
            esperado = True
        except Exception:
            esperado = False
        self.assertEqual(ik._sqlite_available(), esperado)

    def test_chroma_available_refleja_imports(self):
        with mock.patch.dict(sys.modules, {"chromadb": mock.MagicMock(),
                                           "sentence_transformers": mock.MagicMock()}):
            self.assertTrue(ik._chroma_available())
        with mock.patch.dict(sys.modules, {"chromadb": None}):
            self.assertFalse(ik._chroma_available())

    def test_build_sqlite_index_y_busqueda_ordenada(self):
        (self.know / "a.md").write_text("## Alpha\nalpha beta gamma delta epsilon zeta\n")
        (self.know / "b.md").write_text("## Beta\nalpha iota kappa lambda mu nu xi omicron\n")
        n_files, n_chunks = ik.build_sqlite_index()
        self.assertEqual(n_files, 2)
        self.assertGreaterEqual(n_chunks, 2)
        # Segunda construcción sobre el mismo storage: mkdir con exist_ok=True.
        ik.build_sqlite_index()
        resultados = ik.search_sqlite("alpha")
        self.assertGreaterEqual(len(resultados), 2)
        self.assertGreaterEqual(resultados[0]["score"], resultados[-1]["score"])

    def test_build_sqlite_index_storage_con_padres(self):
        nuevo = self.tmp / "nested" / "db"
        ik.STORAGE_DIR = nuevo
        ik.SQLITE_DB = nuevo / "knowledge.db"
        ik.MANIFEST = nuevo / "manifest.json"
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        self.assertEqual(ik.build_sqlite_index()[0], 1)
        self.assertTrue(ik.SQLITE_DB.exists())

    def test_build_sqlite_index_vector_normalizado_por_tokens(self):
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        ik.build_sqlite_index()
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(ik.SQLITE_DB)
        vector_json = conn.execute("SELECT vector FROM vectors").fetchone()[0]
        conn.close()
        vector = json.loads(vector_json)
        # 6 tokens útiles, 1 archivo: peso = (1/6) * log(1 + 1/2).
        esperado = (1 / 6) * math.log(1 + 1 / 2)
        self.assertAlmostEqual(vector["alpha"], esperado, places=6)

    def test_build_sqlite_index_limpia_obsoletos(self):
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        (self.know / "b.md").write_text("## B\nomega sigma tau upsilon phi chi psi\n")
        ik.build_sqlite_index()
        (self.know / "b.md").unlink()
        ik.build_sqlite_index()
        self.assertEqual(ik.search_sqlite("omega"), [])
        hits = ik.search_sqlite("alpha")
        self.assertGreaterEqual(len(hits), 1)
        self.assertIn("alpha", hits[0]["contenido"])

    def test_check_sqlite_fresh_variantes(self):
        self.assertFalse(ik.check_sqlite_fresh())
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        ik.build_sqlite_index()
        self.assertTrue(ik.check_sqlite_fresh())
        ik.MANIFEST.unlink()
        self.assertFalse(ik.check_sqlite_fresh())
        ik.build_sqlite_index()
        manifest = json.loads(ik.MANIFEST.read_text(encoding="utf-8"))
        manifest["extra.md"] = 1.0
        ik.MANIFEST.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertFalse(ik.check_sqlite_fresh())
        ik.build_sqlite_index()
        os.utime(self.know / "a.md", (1000000, 1000000))
        self.assertFalse(ik.check_sqlite_fresh())

    def test_forced_backend_argv_y_entorno(self):
        with mock.patch.object(sys, "argv", ["index_knowledge.py", "--json"]):
            self.assertEqual(ik._forced_backend(), "json")
        with mock.patch.object(sys, "argv", ["index_knowledge.py"]):
            self.assertIsNone(ik._forced_backend())
        with mock.patch.object(sys, "argv", ["index_knowledge.py"]), \
                mock.patch.dict(os.environ, {"BETTER_INDEX_BACKEND": " JSON "}):
            self.assertEqual(ik._forced_backend(), "json")
        with mock.patch.object(sys, "argv", ["index_knowledge.py"]), \
                mock.patch.dict(os.environ, {"BETTER_INDEX_BACKEND": ""}):
            self.assertIsNone(ik._forced_backend())

    def test_index_all_backend_json_fresco_no_reconstruye(self):
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        with mock.patch.object(ik, "_chroma_available", return_value=False), \
                mock.patch.object(ik, "_sqlite_available", return_value=False), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            ik.index_all(backend="json")
        ik.JSON_INDEX.write_text("SENTINELA", encoding="utf-8")
        with mock.patch.object(ik, "_chroma_available", return_value=False), \
                mock.patch.object(ik, "_sqlite_available", return_value=False), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            ik.index_all(backend="json")
        self.assertEqual(ik.JSON_INDEX.read_text(encoding="utf-8"), "SENTINELA")

    def test_index_all_backend_json_regenera_si_falta(self):
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        with mock.patch.object(ik, "_chroma_available", return_value=False), \
                mock.patch.object(ik, "_sqlite_available", return_value=False), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            ik.index_all(backend="json")
        ik.JSON_INDEX.unlink()
        with mock.patch.object(ik, "_chroma_available", return_value=False), \
                mock.patch.object(ik, "_sqlite_available", return_value=False), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            ik.index_all(backend="json")
        self.assertTrue(ik.JSON_INDEX.exists())

    def test_index_all_backend_json_no_usa_sqlite(self):
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        with mock.patch.object(ik, "_chroma_available", return_value=False), \
                mock.patch.object(ik, "_sqlite_available", return_value=True), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            ik.index_all(backend="json")
        self.assertTrue(ik.JSON_INDEX.exists())
        self.assertFalse(ik.SQLITE_DB.exists())

    def test_sqlite_available_false_si_connect_falla(self):
        # Simula un intérprete sin FTS5: la excepción debe devolver False.
        with mock.patch.object(ik.sqlite3, "connect", side_effect=Exception("sin FTS5")):
            self.assertFalse(ik._sqlite_available())

    def test_normaliza_bm25(self):
        # FTS5 devuelve BM25 negativo (menor = mejor): exp lo lleva a (0,1].
        self.assertAlmostEqual(ik._normaliza_bm25(-2.0), math.exp(-2.0), places=9)
        # Valores no negativos usan 1/(1+bm25).
        self.assertAlmostEqual(ik._normaliza_bm25(2.0), 1 / 3, places=9)

    def test_search_sqlite_tolera_chunk_sin_vector(self):
        # Caso límite: chunk presente en FTS pero sin fila en vectors
        # (DB desincronizada); el cosine debe caer a 0.0, no romper.
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        ik.build_sqlite_index()
        import sqlite3 as _sqlite3
        conn = _sqlite3.connect(ik.SQLITE_DB)
        conn.execute(
            "INSERT INTO chunks (id, archivo, contenido, tokens, mtime) VALUES (?, ?, ?, ?, ?)",
            ("huerfano", "f.md", "alpha", "[]", 0.0),
        )
        conn.commit()
        conn.close()
        resultados = ik.search_sqlite("alpha")
        self.assertGreaterEqual(len(resultados), 1)

    def test_files_sin_directorio(self):
        """REQ-002: _files devuelve [] si KNOWLEDGE_DIR no existe."""
        old = ik.KNOWLEDGE_DIR
        ik.KNOWLEDGE_DIR = self.tmp / "no_existe"
        try:
            self.assertEqual(ik._files(), [])
        finally:
            ik.KNOWLEDGE_DIR = old

    def test_search_sqlite_query_vacio(self):
        """REQ-002: search_sqlite devuelve [] para consulta sin terminos utiles."""
        self.assertEqual(ik.search_sqlite("el la los"), [])

    def test_index_all_sin_archivos(self):
        """REQ-002: index_all informa que no hay archivos cuando el directorio esta vacio."""
        old = ik.KNOWLEDGE_DIR
        ik.KNOWLEDGE_DIR = self.tmp / "vacio"
        ik.KNOWLEDGE_DIR.mkdir()
        buf = io.StringIO()
        try:
            with mock.patch.object(sys, "stdout", buf):
                ik.index_all()
            self.assertIn("no hay archivos", buf.getvalue())
        finally:
            ik.KNOWLEDGE_DIR = old

    def test_check_fresh_no_manifest(self):
        """REQ-002: check_fresh es False si no hay manifest."""
        self.assertFalse(ik.check_fresh())

    def test_check_fresh_no_index(self):
        """REQ-002: check_fresh es False si hay manifest pero no indice."""
        ik.MANIFEST.write_text("{}", encoding="utf-8")
        self.assertFalse(ik.check_fresh())

    def test_check_fresh_manifest_size(self):
        """REQ-002: check_fresh es False si cambia el numero de archivos."""
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        ik.build_json_index()
        ik.MANIFEST.write_text("{}", encoding="utf-8")
        self.assertFalse(ik.check_fresh())

    def test_check_fresh_mtime(self):
        """REQ-002: check_fresh es False si cambia el mtime de un archivo."""
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        ik.build_json_index()
        os.utime(self.know / "a.md", (1000000, 1000000))
        self.assertFalse(ik.check_fresh())

    def test_main_check_ok_y_fail(self):
        """REQ-002: main --check devuelve 0 si indice fresco y 1 si no."""
        (self.know / "a.md").write_text("## A\nalpha beta gamma delta epsilon zeta\n")
        ik.build_json_index()
        with mock.patch.object(sys, "argv", ["index_knowledge.py", "--check"]), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(ik.main(), 0)
        ik.MANIFEST.unlink()
        with mock.patch.object(sys, "argv", ["index_knowledge.py", "--check"]), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(ik.main(), 1)


class TestADRValidator(unittest.TestCase):
    """REQ-013: validacion de ADR y auditoria de sesgos (Pilar 4)."""

    ADR_VALIDO = (
        "---\nid: ADR-100\ntitulo: Prueba\nestado: Aceptado\nfecha: 2026-09-19\n---\n"
        "# ADR-100: Prueba\n\n## Contexto\n\nProblema con 3 GB de datos.\n\n"
        "## Alternativas consideradas\n\n- **A**: opcion 1.\n- **B**: opcion 2.\n\n"
        "## Decision\n\nSe elige A por 2 razones.\n\n"
        "## Consecuencias\n\n- Positivas: 1.\n\n"
        "## Supuestos\n\n- Vale 1.\n\n"
        "## Metricas de exito\n\n- p99 < 200 ms.\n\n"
        "## Pre-mortem (Analisis Prospectivo de Fallos)\n\n- Escenario 1: fallo X, mitigacion Y.\n- Escenario 2: fallo Z, mitigacion W.\n"
    )

    tmp: Path

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

    def test_propuesto_exige_premortem(self):
        sin_premortem = self.ADR_VALIDO.replace(
            "## Pre-mortem (Analisis Prospectivo de Fallos)\n\n"
            "- Escenario 1: fallo X, mitigacion Y.\n- Escenario 2: fallo Z, mitigacion W.\n",
            "",
        )
        self._adr(sin_premortem.replace("estado: Aceptado", "estado: Propuesto"))
        errors, _ = av.validate(self.tmp)
        self.assertTrue(any("pre-mortem" in e.lower() for e in errors))

    def test_reemplazado_no_exige_premortem(self):
        sin_premortem = self.ADR_VALIDO.replace(
            "## Pre-mortem (Analisis Prospectivo de Fallos)\n\n"
            "- Escenario 1: fallo X, mitigacion Y.\n- Escenario 2: fallo Z, mitigacion W.\n",
            "",
        )
        self._adr(sin_premortem.replace("estado: Aceptado", "estado: Reemplazado"))
        errors, _ = av.validate(self.tmp)
        self.assertEqual(errors, [])


class TestAutoAudit(unittest.TestCase):
    """REQ-014: auto-auditoria (sesgos, evidencias, decisiones, tests, IA)."""

    _TEST_OK = (
        "import unittest\n\n\n"
        "class T(unittest.TestCase):\n"
        "    def test_ok(self):\n"
        "        self.assertEqual(1 + 1, 2)\n"
    )

    tmp: Path

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

    def test_frontmatter_vacio(self):
        """REQ-014: _frontmatter devuelve {} si no hay frontmatter."""
        self.assertEqual(aa._frontmatter("# titulo\nsin frontmatter\n"), {})

    def test_auditar_sesgos_path_inexistente(self):
        """REQ-014: auditar_sesgos ignora paths que no existen."""
        self.assertEqual(aa.auditar_sesgos([self.tmp / "no_existe.md"]), [])

    def test_auditar_evidencias_sbom_sin_fecha(self):
        """REQ-014: SBOM con nombre no fecha genera advertencia."""
        self._write("SBOM-foo.spdx.json", "{}")
        errors, warnings = aa.auditar_evidencias(docs_dir=self.tmp)
        self.assertEqual(errors, [])
        self.assertTrue(any("no se pudo leer" in w for w in warnings))

    def test_scanner_disponible_osv(self):
        """REQ-014: _scanner_disponible elige osv-scanner si pip-audit no esta."""
        with mock.patch.object(aa.shutil, "which", side_effect=lambda x: x == "osv-scanner"):
            nombre, builder = aa._scanner_disponible()
            self.assertEqual(nombre, "osv-scanner")
            self.assertEqual(
                builder(Path("r.txt")),
                ["osv-scanner", "--format", "json", "--lockfile", str(Path("r.txt"))],
            )

    def test_parse_pip_audit(self):
        """REQ-014: _parse_pip_audit extrae vulnerabilidades del JSON."""
        payload = {
            "dependencies": [
                {"name": "x", "version": "1.0", "vulns": [
                    {"id": "CVE-1", "fix_versions": ["1.1"]}
                ]},
                {"name": "y", "version": "2.0", "vulns": None},
            ]
        }
        hallazgos = aa._parse_pip_audit(payload)
        self.assertEqual(len(hallazgos), 1)
        self.assertEqual(hallazgos[0]["id"], "CVE-1")

    def test_runner_pip_audit(self):
        """REQ-014: _runner_pip_audit ejecuta el comando y parsea la salida."""
        proc = mock.MagicMock()
        proc.returncode = 1
        proc.stdout = json.dumps({"dependencies": [{"name": "x", "version": "1.0", "vulns": []}]})
        proc.stderr = ""
        with mock.patch.object(aa.subprocess, "run", return_value=proc) as lanzado:
            run = aa._runner_pip_audit(["pip-audit", "--format", "json"])
            self.assertEqual(run(), [])
            self.assertEqual(lanzado.call_args.args[0], ["pip-audit", "--format", "json"])
        fallo = mock.MagicMock(returncode=2, stdout="", stderr="boom")
        with mock.patch.object(aa.subprocess, "run", return_value=fallo):
            with self.assertRaises(RuntimeError):
                aa._runner_pip_audit(["pip-audit"])()

    def test_auditar_decisiones_lecciones_exception(self):
        """REQ-014: auditar_decisiones reporta si lessons_extractor falla."""
        fake_module = mock.MagicMock()
        fake_module.validate.side_effect = RuntimeError("boom")
        with mock.patch.dict(sys.modules, {"lessons_extractor": fake_module}):
            warns = aa.auditar_decisiones()
        self.assertTrue(any("no se pudieron validar las lecciones" in w for w in warns))

    def test_auditar_decisiones_index_exception(self):
        """REQ-014: auditar_decisiones reporta si index_knowledge falla."""
        fake_module = mock.MagicMock()
        fake_module.check_fresh.side_effect = RuntimeError("boom")
        with mock.patch.dict(sys.modules, {"lessons_extractor": le, "index_knowledge": fake_module}):
            warns = aa.auditar_decisiones()
        self.assertTrue(any("no se pudo comprobar el indice" in w for w in warns))

    def test_es_asercion_assert_y_fail(self):
        """REQ-014: _es_asercion reconoce assert, fail y metodos assert*."""
        self.assertTrue(aa._es_asercion(ast.parse("assert x").body[0]))
        self.assertTrue(aa._es_asercion(ast.parse("self.assertEqual(1, 1)").body[0].value))
        self.assertTrue(aa._es_asercion(ast.parse("self.fail('x')").body[0].value))
        self.assertTrue(aa._es_asercion(ast.parse("fail()").body[0].value))
        self.assertFalse(aa._es_asercion(ast.parse("self.otro()").body[0].value))

    def test_tautologia_assertIs_None(self):
        """REQ-014: _tautologia detecta assertIs(None, None)."""
        node = ast.parse("self.assertIs(None, None)").body[0].value
        self.assertEqual(aa._tautologia(node), "assertIs(None)")

    def test_auditar_calibracion_set_inexistente(self):
        """REQ-014: calibracion sin set reporta error, candidatos ausentes no."""
        c = self._write("c.json", json.dumps({"casos": []}))
        errors, _ = aa.auditar_calibracion(set_path=self.tmp / "no.json", cand_path=c)
        self.assertTrue(any("no existe el set" in e for e in errors))

    def test_auditar_calibracion_json_invalido(self):
        """REQ-014: calibracion con JSON invalido reporta error."""
        s = self._write("s.json", "{no")
        c = self._write("c.json", json.dumps({"casos": []}))
        errors, _ = aa.auditar_calibracion(s, c)
        self.assertTrue(any("JSON invalido" in e for e in errors))

    def test_auditar_calibracion_escenario_duplicado(self):
        """REQ-014: calibracion advierte escenarios duplicados."""
        s = self._write("s.json", json.dumps({"casos": [
            {"id": "N01", "tipo": "noul", "estado": "mismo", "instrucciones": "i", "esperado": "yes"},
            {"id": "N02", "tipo": "noul", "estado": "Mismo", "instrucciones": "i", "esperado": "no"},
        ]}))
        c = self._write("c.json", json.dumps({"casos": []}))
        _, warnings = aa.auditar_calibracion(s, c)
        self.assertTrue(any("escenario duplicado" in w for w in warnings))

    def test_main_vulns(self):
        """REQ-014: main ejecuta subcomando vulns."""
        with mock.patch.object(aa, "auditar_vulns", return_value=([], [])) as av:
            self.assertEqual(aa.main(["vulns"]), 0)
        av.assert_called_once()

    def test_main_json_y_strict(self):
        """REQ-014: main soporta salida JSON y modo strict."""
        buf = io.StringIO()
        with mock.patch.object(aa, "auditar_tests", return_value=(["tautologica"], [])), \
                mock.patch.object(sys, "stdout", buf):
            rc = aa.main(["tests", "--json", "--strict"])
        self.assertEqual(rc, 1)
        data = json.loads(buf.getvalue())
        self.assertIn("tautologica", data["errores"])


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


class TestAdrBackfill(unittest.TestCase):
    """REQ-025: backfill de ADR desde historial Git, lecciones y pruebas."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.lessons = self.tmp / "lessons"
        self.lessons.mkdir()
        self.pruebas = self.tmp / "PRUEBAS.md"
        self.adr = self.tmp / "decisions"
        for attr, value in (
            ("LESSONS_DIR", self.lessons),
            ("PRUEBAS_FILE", self.pruebas),
            ("ADR_DIR", self.adr),
        ):
            patcher = mock.patch.object(ab, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _commit_decision(self):
        return [{
            "sha": "abc12345",
            "date": "2026-09-01",
            "subject": "adoptar sqlite como backend del indice",
        }]

    def _leccion(self, entry_id: str = "LSN-100") -> None:
        (self.lessons / "2026.yaml").write_text(
            f"- id: {entry_id}\n"
            "  proyecto: demo\n  fase: Diseno\n  categoria: Riesgo_Tecnico\n"
            "  problema: el cache crece sin limite\n"
            "  recomendacion: usar un backend de cache con expiracion\n"
            "  estado: Resuelta\n  fecha: 2026-09-01\n",
            encoding="utf-8",
        )

    def test_commit_decision_es_candidato(self):
        with mock.patch.object(ab, "run_git_log", self._commit_decision):
            candidatos = ab.generate_candidates()
        self.assertEqual(len(candidatos), 1)
        self.assertEqual(candidatos[0]["source"], "Commit abc12345")
        self.assertTrue(candidatos[0]["titulo"].startswith("Adopción de sqlite"))

    def test_leccion_source_sin_doble_prefijo(self):
        self._leccion("LSN-100")
        with mock.patch.object(ab, "run_git_log", return_value=[]):
            candidatos = ab.generate_candidates()
        self.assertEqual([c["source"] for c in candidatos], ["LSN-100"])

    def test_varias_lecciones_se_extraen_incluida_la_primera(self):
        (self.lessons / "2026.yaml").write_text(
            "- id: LSN-101\n  problema: el cache crece\n"
            "  recomendacion: usar un backend de cache\n  categoria: C1\n  fecha: 2026-09-01\n"
            "- id: LSN-102\n  problema: la cola se satura\n"
            "  recomendacion: usar una cola con limite\n  categoria: C2\n  fecha: 2026-09-02\n",
            encoding="utf-8",
        )
        with mock.patch.object(ab, "run_git_log", return_value=[]):
            candidatos = ab.generate_candidates()
        self.assertEqual([c["source"] for c in candidatos], ["LSN-101", "LSN-102"])

    def test_ronda_con_correccion_es_candidata(self):
        self.pruebas.write_text(
            "## Ronda 7\n\nCorrección: migrar el indice a sqlite\n", encoding="utf-8"
        )
        with mock.patch.object(ab, "run_git_log", return_value=[]):
            candidatos = ab.generate_candidates()
        self.assertEqual([c["source"] for c in candidatos], ["Ronda 7"])

    def test_list_no_escribe(self):
        self._leccion()
        with mock.patch.object(ab, "run_git_log", return_value=[]), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(ab.main(["--list"]), 0)
        self.assertIn("Candidatos encontrados: 1", out.getvalue())
        self.assertIn("[LSN-100]", out.getvalue())
        self.assertFalse(self.adr.exists())

    def test_dry_run_previsualiza_sin_escribir(self):
        self._leccion()
        with mock.patch.object(ab, "run_git_log", return_value=[]), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(ab.main(["--dry-run"]), 0)
        self.assertIn("DRY RUN", out.getvalue())
        self.assertIn("ADR-001", out.getvalue())
        self.assertFalse(self.adr.exists())

    def test_write_crea_borrador_con_todas_las_secciones(self):
        self._leccion()
        with mock.patch.object(ab, "run_git_log", return_value=[]), \
             mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(ab.main(["--write"]), 0)
        archivos = sorted(self.adr.glob("ADR-*.md"))
        self.assertEqual(len(archivos), 1)
        contenido = archivos[0].read_text(encoding="utf-8")
        for seccion in ("## Contexto", "## Alternativas consideradas", "## Decision",
                        "## Consecuencias", "## Supuestos", "## Metricas de exito",
                        "## Pre-mortem", "## Referencias"):
            self.assertIn(seccion, contenido)
        self.assertIn("id: ADR-001", contenido)

    def test_write_es_idempotente_por_titulo(self):
        self._leccion()
        with mock.patch.object(ab, "run_git_log", return_value=[]), \
             mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(ab.main(["--write"]), 0)
        with mock.patch.object(ab, "run_git_log", return_value=[]), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(ab.main(["--write"]), 0)
        self.assertEqual(len(list(self.adr.glob("ADR-*.md"))), 1)
        self.assertIn("[SKIP]", out.getvalue())

    def test_sin_candidatos_retorna_cero(self):
        with mock.patch.object(ab, "run_git_log", return_value=[]), \
             mock.patch.object(sys, "stdout", io.StringIO()) as out:
            self.assertEqual(ab.main([]), 0)
        self.assertIn("No se encontraron candidatos", out.getvalue())

    def test_get_next_adr_num_continua_serie(self):
        self.adr.mkdir()
        (self.adr / "ADR-012-existente.md").write_text(
            "---\nid: ADR-012\ntitulo: existente\nestado: Aceptado\nfecha: 2026-09-01\n---\n",
            encoding="utf-8",
        )
        self.assertEqual(ab.get_next_adr_num(), 13)


if __name__ == "__main__":
    unittest.main()
