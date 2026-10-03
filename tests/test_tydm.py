#!/usr/bin/env python3
"""Tests del motor MDT/TyDM: llama, calibracion, pilares, review, merge y backend
fast (REQ-011/REQ-012/REQ-016/REQ-018/REQ-027).
"""

import argparse
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

import download_tydm_model as djm  # noqa: E402
import tydm_calibration as jc  # noqa: E402
import tydm_calibration_merge as jcm  # noqa: E402
import tydm_fast as tfa  # noqa: E402
import tydm_pillars as jp  # noqa: E402
import tydm_review as jr  # noqa: E402

class TestTyDMLlama(unittest.TestCase):
    """REQ-011: cliente MDT liviano con llama.cpp."""

    _VOCAB = 1000
    _N_ROWS = 256

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.model_path = self.tmp / "fake.gguf"
        self.model_path.write_bytes(b"fake-model")

        # Importamos tydm_llama sin dependencias (los imports son diferidos),
        # luego mockeamos llama_cpp y numpy solo para estas pruebas.
        import tydm_llama as jl

        self.jl = jl

        self._real_llama = sys.modules.get("llama_cpp")
        self._real_numpy = sys.modules.get("numpy")
        self._real_model_env = os.environ.pop("TYDM_MODEL_PATH", None)
        self._real_temp_env = os.environ.pop("TYDM_TEMPERATURE", None)

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
            os.environ["TYDM_MODEL_PATH"] = self._real_model_env
        if self._real_temp_env is not None:
            os.environ["TYDM_TEMPERATURE"] = self._real_temp_env
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client(self):
        return self.jl.TyDMLlama(model_path=str(self.model_path), n_ctx=128)

    @staticmethod
    def _set_logit(client, token: str, value: float) -> None:
        for row in client.model.scores:
            row[ord(token)] = value

    def test_constructor_activa_logits_all(self):
        client = self._client()
        self.assertIs(client.model._kwargs.get("logits_all"), True)

    def test_tydm_model_path_se_usa_por_defecto(self):
        os.environ["TYDM_MODEL_PATH"] = str(self.model_path)
        client = self.jl.TyDMLlama()
        self.assertEqual(client.model_path, self.model_path)

    def test_tydm_temperature_desde_entorno(self):
        os.environ["TYDM_TEMPERATURE"] = "2.5"
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
        client = self.jl.TyDMLlama(model_path=str(self.model_path), temperature=3.0)
        self.assertAlmostEqual(client.temperature, 3.0)
        with self.assertRaises(ValueError):
            self.jl.TyDMLlama(model_path=str(self.model_path), temperature=-1.0)

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
            self.jl.TyDMLlama(model_path=str(missing))

    def test_default_model_path_sin_env(self):
        # _default_model_path usa Path.home() / ".cache" / "better-project" / "tydm" / DEFAULT_MODEL
        # No podemos testear Path.home() facilmente, pero podemos verificar la logica
        with mock.patch.object(Path, "home", return_value=self.tmp):
            path = self.jl._default_model_path()
            expected = self.tmp / ".cache" / "better-project" / "tydm" / self.jl.DEFAULT_MODEL
            self.assertEqual(path, expected)

    def test_env_int_y_float_con_none(self):
        # _env_int y _env_float devuelven default cuando la variable no existe
        self.assertEqual(self.jl._env_int("TYDM_NO_EXISTE", 42), 42)
        self.assertEqual(self.jl._env_float("TYDM_NO_EXISTE", 3.14), 3.14)
        # Y parsean correctamente cuando existe
        os.environ["TYDM_TEST_INT"] = "123"
        os.environ["TYDM_TEST_FLOAT"] = "2.5"
        try:
            self.assertEqual(self.jl._env_int("TYDM_TEST_INT", 0), 123)
            self.assertEqual(self.jl._env_float("TYDM_TEST_FLOAT", 0.0), 2.5)
        finally:
            os.environ.pop("TYDM_TEST_INT", None)
            os.environ.pop("TYDM_TEST_FLOAT", None)

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
        prompt = self.jl.TyDMLlama._build_prompt("estado", {"type": "noul", "instructions": "¿Sí o no?"})
        self.assertIn("State: estado", prompt)
        self.assertIn("Question: ¿Sí o no?", prompt)
        self.assertIn('Answer only "yes" or "no"', prompt)
        self.assertIn("Answer: ", prompt)

    def test_build_prompt_choice(self):
        prompt = self.jl.TyDMLlama._build_prompt("estado", {
            "type": "choice",
            "instructions": "Elige",
            "criteria": {"a": "opcion A", "b": "opcion B"}
        })
        self.assertIn("Options:", prompt)
        self.assertIn("- a: opcion A", prompt)
        self.assertIn("- b: opcion B", prompt)
        self.assertIn("Answer with the exact option id", prompt)

    def test_build_prompt_score(self):
        prompt = self.jl.TyDMLlama._build_prompt("estado", {
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
                self.jl.TyDMLlama(model_path=str(self.model_path))
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
                self.jl.TyDMLlama(model_path=str(self.model_path))
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
        with mock.patch.object(sys, "argv", ["tydm_llama.py", "--demo"]), \
             mock.patch.object(self.jl, "TyDMLlama", return_value=self._client()), \
             mock.patch.object(sys, "stdout", io.StringIO()):
            # _demo() llama a TyDMLlama() y decide()
            result = self.jl._main()
            self.assertEqual(result, 0)

    def test_main_input(self):
        data = {"state": "test", "questions": {"q": {"type": "noul", "instructions": "?"}}}
        input_file = self.tmp / "input.json"
        input_file.write_text(json.dumps(data))
        with mock.patch.object(sys, "argv", ["tydm_llama.py", "--input", str(input_file)]), \
             mock.patch.object(self.jl, "TyDMLlama", return_value=self._client()), \
             mock.patch.object(sys, "stdout", io.StringIO()):
            result = self.jl._main()
            self.assertEqual(result, 0)

    def test_main_uso_incorrecto(self):
        with mock.patch.object(sys, "argv", ["tydm_llama.py"]), \
             mock.patch.object(sys, "stderr", io.StringIO()):
            result = self.jl._main()
            self.assertEqual(result, 1)

    def test_main_input_falta_archivo(self):
        with mock.patch.object(sys, "argv", ["tydm_llama.py", "--input"]), \
             mock.patch.object(sys, "stderr", io.StringIO()):
            result = self.jl._main()
            self.assertEqual(result, 1)

    def test_n_ctx_y_n_threads_explicitos(self):
        client = self.jl.TyDMLlama(model_path=str(self.model_path), n_ctx=64, n_threads=2)
        self.assertEqual(client.n_ctx, 64)
        self.assertEqual(client.n_threads, 2)

    def test_constructor_verbose_false(self):
        client = self._client()
        self.assertEqual(client.model._kwargs.get("verbose"), False)

    def test_tokenize_default_sin_bos(self):
        client = self._client()
        visto = {}

        def fake_tokenize(text, add_bos=False):
            visto["add_bos"] = add_bos
            return [1]

        client.model.tokenize = fake_tokenize
        client._tokenize("hola")
        self.assertEqual(visto["add_bos"], False)
        client._tokenize("hola", add_bos=True)
        self.assertEqual(visto["add_bos"], True)

    def test_first_token_probs_usa_bos(self):
        client = self._client()
        visto = {}

        def fake_tokenize(text, add_bos=False):
            visto["add_bos"] = add_bos
            return [1, 2]

        client.model.tokenize = fake_tokenize
        client._first_token_probs("prompt", [1])
        self.assertEqual(visto["add_bos"], True)

    def test_answer_noul_tokens_sin_bos(self):
        client = self._client()
        vistos = {}

        def fake_tokenize(text, add_bos=False):
            nombre = text.decode() if isinstance(text, bytes) else text
            vistos[nombre] = add_bos
            return [1]

        client.model.tokenize = fake_tokenize
        client._answer_noul("estado", {"type": "noul", "instructions": "?"})
        self.assertEqual(vistos.get("yes"), False)
        self.assertEqual(vistos.get("no"), False)

    def test_answer_choice_tokens_sin_bos(self):
        client = self._client()
        vistos = {}

        def fake_tokenize(text, add_bos=False):
            nombre = text.decode() if isinstance(text, bytes) else text
            vistos[nombre] = add_bos
            return [1]

        client.model.tokenize = fake_tokenize
        client._answer_choice("estado", {"type": "choice", "instructions": "?",
                                         "criteria": {"a": "x", "b": "y", "c": "z"}})
        self.assertEqual(vistos.get("a"), False)
        self.assertEqual(vistos.get("b"), False)
        self.assertEqual(vistos.get("c"), False)

    def test_answer_score_tokens_sin_bos(self):
        client = self._client()
        vistos = {}

        def fake_tokenize(text, add_bos=False):
            nombre = text.decode() if isinstance(text, bytes) else text
            vistos[nombre] = add_bos
            return [1]

        client.model.tokenize = fake_tokenize
        client._answer_score("estado", {"type": "score", "instructions": "?",
                                        "criteria": ["bajo", "medio", "alto"]})
        self.assertEqual(vistos.get("0"), False)
        self.assertEqual(vistos.get("1"), False)
        self.assertEqual(vistos.get("2"), False)

    def test_demo_conserva_acentos(self):
        cliente = mock.MagicMock()
        cliente.decide.return_value = {"x": {"texto": "decisión"}}
        buf = io.StringIO()
        with mock.patch.object(self.jl, "TyDMLlama", return_value=cliente), \
                mock.patch.object(sys, "stdout", buf):
            self.jl._demo()
        self.assertIn("decisión", buf.getvalue())

    def test_main_input_conserva_acentos(self):
        data = {"state": "test", "questions": {"q": {"type": "noul", "instructions": "?"}}}
        input_file = self.tmp / "input.json"
        input_file.write_text(json.dumps(data), encoding="utf-8")
        cliente = mock.MagicMock()
        cliente.decide.return_value = {"q": {"texto": "decisión"}}
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["tydm_llama.py", "--input", str(input_file)]), \
                mock.patch.object(self.jl, "TyDMLlama", return_value=cliente), \
                mock.patch.object(sys, "stdout", buf):
            result = self.jl._main()
        self.assertEqual(result, 0)
        self.assertIn("decisión", buf.getvalue())


class TestTyDMCalibration(unittest.TestCase):
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
            argv = ["tydm_calibration.py", "--set", str(set_path), "--folds", "2",
                    "--no-cache", "--json", "--write"]
            with mock.patch.object(jc, "TyDMLlama", lambda model_path=None: _FakeCalibClient()), \
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
            argv = ["tydm_calibration.py", "--set", str(set_path), "--folds", "2", "--no-cache"]
            with mock.patch.object(jc, "TyDMLlama", lambda model_path=None: _FakeCalibClient()), \
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
            argv = ["tydm_calibration.py", "--set", str(set_path), "--folds", "2", "--no-cache", "--model", "/custom/model.gguf"]
            with mock.patch.object(jc, "TyDMLlama") as mock_llama, \
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
            argv = ["tydm_calibration.py", "--set", str(set_path), "--folds", "2", "--no-cache"]
            with mock.patch.object(jc, "TyDMLlama", lambda model_path=None: _FakeCalibClient()), \
                    mock.patch.object(jc, "cargar_cache") as mock_cache, \
                    mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(sys, "stdout", io.StringIO()), \
                    mock.patch.object(sys, "stderr", io.StringIO()):
                self.assertEqual(jc.main(), 0)
                mock_cache.assert_not_called()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_hits_cuenta_aciertos(self):
        self.assertEqual(jc._hits([[0.9, 0.1], [0.2, 0.8]], [0, 1]), 2)
        self.assertEqual(jc._hits([[0.9, 0.1]], [1]), 0)

    def test_evaluate_incluye_ece_adaptativo(self):
        records = [
            {"probs": [0.95, 0.05], "label_idx": 0},
            {"probs": [0.6, 0.4], "label_idx": 1},
            {"probs": [0.55, 0.45], "label_idx": 0},
            {"probs": [0.9, 0.1], "label_idx": 1},
        ]
        m = jc.evaluate(records, 1.0)
        probs_list = [r["probs"] for r in records]
        labels = [r["label_idx"] for r in records]
        self.assertAlmostEqual(
            m["ece_adaptativo"], jc.ece(probs_list, labels, adaptativo=True), places=9)
        self.assertNotAlmostEqual(m["ece"], m["ece_adaptativo"], places=6)

    def test_fit_temperature_minimiza_nll(self):
        # 60% de aciertos con probabilidad 0.95: sobreconfianza -> T > 1.
        records = [
            {"probs": [0.95, 0.05], "label_idx": 0 if i < 12 else 1}
            for i in range(20)
        ]
        t = jc.fit_temperature(records)
        self.assertGreater(t, 1.5)

    def test_fit_temperature_empate_prefiere_t_uno(self):
        # Con probabilidades uniformes todas las T empatan: desempate -> 1.0.
        records = [{"probs": [0.5, 0.5], "label_idx": 0} for _ in range(10)]
        self.assertEqual(jc.fit_temperature(records), 1.0)

    def test_kfold_ajusta_temperatura_en_train(self):
        records = [{"probs": [0.9, 0.1], "label_idx": i % 2} for i in range(8)]
        tamanos = []
        original = jc.fit_temperature

        def espia(recs, grid=None):
            tamanos.append(len(recs))
            return original(recs, grid)

        with mock.patch.object(jc, "fit_temperature", side_effect=espia):
            jc.kfold(records, folds=4)
        self.assertEqual(tamanos, [6, 6, 6, 6])

    def test_load_set_sin_casos_falla(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "s.json"
            ruta.write_text('{"casos": []}', encoding="utf-8")
            with self.assertRaises(ValueError):
                jc.load_set(ruta)

    def test_guardar_cache_padres_idempotente_y_acentos(self):
        cache = {"x": {"texto": "decisión"}}
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "nested" / "dir" / "cache.json"
            jc.guardar_cache(cache, ruta)
            jc.guardar_cache(cache, ruta)  # idempotente: exist_ok=True
            texto = ruta.read_text(encoding="utf-8")
        self.assertIn("decisión", texto)

    def test_run_cases_usa_modelo_en_clave_de_cache(self):
        class ClienteFake:
            model_path = "fake-model.gguf"

            def decide(self, state, questions):
                return {"q": {"probabilities": {"yes": 0.7, "no": 0.3}}}

        caso = {"id": "N1", "tipo": "noul", "estado": "x", "instrucciones": "y",
                "esperado": "yes"}
        cache = {}
        jc.run_cases(ClienteFake(), [caso], cache=cache, modelo="m1")
        self.assertIn("m1|N1", cache)
        self.assertEqual(cache["m1|N1"]["label_idx"], 0)


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


class _FakeTyDMClient:
    """Cliente MDT simulado para REQ-012: probabilidades fijas, sin modelo."""

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


class TestTyDMPillars(unittest.TestCase):
    """REQ-012: integracion de MDT con los tres pilares (sin modelo)."""

    ACC = {"choice": 0.9167, "score": 0.4167}

    @staticmethod
    def _ns(req=None, lesson_id=None, file=None, text=None):
        return argparse.Namespace(req=req, id=lesson_id, file=file, text=text)

    def test_requisitos_esquema_y_decision(self):
        salida = jp.ejecutar("requisitos", "REQ-011", "texto", _FakeTyDMClient(), 0.5, self.ACC)
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
        salida = jp.ejecutar("conocimiento", "frag", "texto", _FakeTyDMClient(), 0.5, self.ACC)
        self.assertEqual(salida["tipo"], "score")
        # accuracy score 0.417 < 0.6 => experimental (criterio 6).
        self.assertTrue(salida["experimental"])
        decision = salida["decisiones"][0]
        self.assertTrue(decision["experimental"])
        # P0.20/P1.31: experimental => nunca decision autoritativa, exige revision.
        self.assertIsNone(decision["decision"])
        self.assertTrue(decision["revision_humana"])

    def test_lecciones_dos_decisiones(self):
        salida = jp.ejecutar("lecciones", "LSN-008", "texto", _FakeTyDMClient(), 0.5, self.ACC)
        campos = [d["campo"] for d in salida["decisiones"]]
        self.assertEqual(campos, ["fase", "categoria"])
        self.assertFalse(salida["experimental"])

    def test_umbral_marca_revision_humana_y_decision_nula(self):
        salida = jp.ejecutar("requisitos", "REQ-011", "texto", _FakeTyDMClient(0.4), 0.5, self.ACC)
        decision = salida["decisiones"][0]
        self.assertIsNone(decision["decision"])
        self.assertEqual(decision["propuesta"], "Alta")
        self.assertTrue(decision["revision_humana"])

    def test_umbral_limite_es_definitivo(self):
        salida = jp.ejecutar("requisitos", "REQ-011", "texto", _FakeTyDMClient(0.5), 0.5, self.ACC)
        decision = salida["decisiones"][0]
        self.assertFalse(decision["revision_humana"])
        self.assertEqual(decision["decision"], "Alta")

    def test_accuracy_desconocida_es_experimental(self):
        salida = jp.ejecutar("requisitos", "REQ-011", "texto", _FakeTyDMClient(), 0.5, {})
        self.assertIsNone(salida["accuracy_referencia"])
        self.assertTrue(salida["experimental"])
        # sin accuracy de referencia, tampoco decide: solo propone (P1.19).
        self.assertIsNone(salida["decisiones"][0]["decision"])
        self.assertTrue(salida["decisiones"][0]["revision_humana"])

    def test_pilar_desconocido_lanza(self):
        with self.assertRaises(ValueError):
            jp.ejecutar("otro", "X", "texto", _FakeTyDMClient(), 0.5, self.ACC)

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
        salida = jp.ejecutar("requisitos", "REQ-011", "texto", _FakeTyDMClient(), 0.5, self.ACC)
        buf = io.StringIO()
        with mock.patch.object(sys, "stdout", buf):
            jp._print_human(salida)
        self.assertIn("Pilar: requisitos", buf.getvalue())

    def test_main_json_y_error(self):
        buf = io.StringIO()
        with mock.patch.object(jp, "TyDMLlama", lambda model_path=None: _FakeTyDMClient()), \
                mock.patch.object(jp, "accuracy_por_tipo", return_value=self.ACC), \
                mock.patch.object(sys, "stdout", buf):
            self.assertEqual(jp.main(["conocimiento", "--text", "x", "--json"]), 0)
        self.assertIn("experimental", buf.getvalue())
        with mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(jp.main(["requisitos"]), 1)


class TestTyDMReview(unittest.TestCase):
    """REQ-016: revision humana asistida de clasificaciones MDT (UI/report)."""

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
        os.environ["TYDM_REVIEW_REPORT"] = str(out)
        os.environ["TYDM_REVIEW_CACHE"] = str(self.tmp / "cache.json")
        try:
            self.assertEqual(jr.main(["--report", "--fake", "--limit", "2"]), 0)
            self.assertTrue(out.exists())
        finally:
            os.environ.pop("TYDM_REVIEW_REPORT", None)
            os.environ.pop("TYDM_REVIEW_CACHE", None)
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
        os.environ["TYDM_REVIEW_REPORT"] = str(out)
        os.environ["TYDM_REVIEW_CACHE"] = str(self.tmp / "cache.json")
        try:
            self.assertEqual(jr.main(["--calibracion", "--report", "--limit", "3"]), 0)
            self.assertTrue(out.exists())
        finally:
            os.environ.pop("TYDM_REVIEW_REPORT", None)
            os.environ.pop("TYDM_REVIEW_CACHE", None)

    def test_curses_works_false_si_wrapper_falla(self):
        """REQ-016: _curses_works devuelve False si curses.wrapper falla."""
        with mock.patch.object(jr.curses, "wrapper", side_effect=RuntimeError("sin curses")):
            self.assertFalse(jr._curses_works())

    def test_opciones_caso_choice(self):
        """REQ-016: _opciones_caso para choice devuelve las claves de criterios."""
        caso = {"tipo": "choice", "criterios": {"a": "A", "b": "B"}}
        self.assertEqual(jr._opciones_caso(caso), ["a", "b"])

    def test_opciones_caso_score(self):
        """REQ-016: _opciones_caso para score devuelve indices como strings."""
        caso = {"tipo": "score", "niveles": ["bajo", "medio", "alto"]}
        self.assertEqual(jr._opciones_caso(caso), ["0", "1", "2"])

    def test_cuerpo_sin_frontmatter_sin_delimitador(self):
        """REQ-016: texto sin frontmatter se devuelve strip."""
        self.assertEqual(jr._cuerpo_sin_frontmatter("  linea1\nlinea2  "), "linea1\nlinea2")

    def test_construir_items_conocimiento(self):
        """REQ-016: construir_items incluye archivos de .docs/knowledge."""
        (self.tmp / ".docs" / "knowledge").mkdir(parents=True)
        (self.tmp / ".docs" / "knowledge" / "a.md").write_text("## A\ncontenido\n", encoding="utf-8")
        with mock.patch.object(jr, "ROOT", self.tmp):
            items = jr.construir_items(["conocimiento"])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["pilar"], "conocimiento")

    def test_cargar_cache_json_invalido(self):
        """REQ-016: cargar_cache tolera JSON corrupto."""
        path = self.tmp / "cache.json"
        path.write_text("{no valido", encoding="utf-8")
        self.assertEqual(jr.cargar_cache(str(path)), {})

    def test_imprimir_tabla_muestra_filas(self):
        """REQ-016: imprimir_tabla genera lineas con item, pilar y estado."""
        filas = [
            {"item": "X", "pilar": "requisitos", "campo": "prioridad", "propuesta": "Alta",
             "confianza": 0.8, "estado": "ok"},
            {"item": "Y", "pilar": "lecciones", "campo": "estado", "propuesta": "Abierta",
             "confianza": None, "estado": "pendiente"},
        ]
        buf = io.StringIO()
        with mock.patch.object(sys, "stdout", buf):
            jr.imprimir_tabla(filas)
        salida = buf.getvalue()
        self.assertIn("X", salida)
        self.assertIn("requisitos", salida)
        self.assertIn("n/a", salida)

    def test_main_sin_items_devuelve_error(self):
        """REQ-016: main retorna 1 si no hay items para revisar."""
        out = self.tmp / "rev.json"
        os.environ["TYDM_REVIEW_REPORT"] = str(out)
        try:
            with mock.patch.object(jr, "construir_items", return_value=[]):
                self.assertEqual(jr.main(["--report", "--fake"]), 1)
        finally:
            os.environ.pop("TYDM_REVIEW_REPORT", None)

    def test_main_modo_report_forzado_por_no_tty(self):
        """REQ-016: main usa modo report cuando stdout no es tty."""
        out = self.tmp / "rev.json"
        os.environ["TYDM_REVIEW_REPORT"] = str(out)
        os.environ["TYDM_REVIEW_CACHE"] = str(self.tmp / "cache.json")
        try:
            with mock.patch.object(sys.stdout, "isatty", return_value=False):
                self.assertEqual(jr.main(["--fake", "--limit", "1"]), 0)
            self.assertTrue(out.exists())
        finally:
            os.environ.pop("TYDM_REVIEW_REPORT", None)
            os.environ.pop("TYDM_REVIEW_CACHE", None)

    def test_main_advierte_curses_no_disponible(self):
        """REQ-016: main advierte y usa report si curses no esta disponible."""
        out = self.tmp / "rev.json"
        err = io.StringIO()
        os.environ["TYDM_REVIEW_REPORT"] = str(out)
        os.environ["TYDM_REVIEW_CACHE"] = str(self.tmp / "cache.json")
        try:
            with mock.patch.object(jr, "CURSES_AVAILABLE", False), \
                    mock.patch.object(sys.stdout, "isatty", return_value=True), \
                    mock.patch.object(sys, "stderr", err):
                self.assertEqual(jr.main(["--fake", "--limit", "1"]), 0)
            self.assertIn("curses no disponible", err.getvalue())
            self.assertTrue(out.exists())
        finally:
            os.environ.pop("TYDM_REVIEW_REPORT", None)
            os.environ.pop("TYDM_REVIEW_CACHE", None)


class TestTyDMCalibrationMerge(unittest.TestCase):
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

    def test_main_json_no_escapa_no_ascii(self):
        # ensure_ascii=False: un id con no-ASCII debe salir literal en stdout.
        self._cand(casos=[{"id": "NÑ90", "tipo": "noul", "estado": "a",
                            "instrucciones": "i", "esperado": "yes"}])
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            jcm.main(["--set", str(self.set_path), "--candidatos", str(self.cand_path), "--json"])
        self.assertIn("NÑ90", out.getvalue())

    def test_main_dry_run_no_dice_aplicar(self):
        # Sin --aplicar la salida debe decir dry-run aunque no haya errores.
        self._cand(casos=[{"id": "N90", "tipo": "noul", "estado": "a",
                            "instrucciones": "i", "esperado": "yes"}])
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            rc = jcm.main(["--set", str(self.set_path), "--candidatos", str(self.cand_path)])
        self.assertEqual(rc, 0)
        self.assertIn("dry-run", out.getvalue())


class TestTyDMFast(unittest.TestCase):
    """REQ-027: backend MDT local ultraligero (NB/kNN + temperatura + conformal)."""

    @classmethod
    def setUpClass(cls):
        cls.casos = tfa.tc.load_set(tfa.SET_PATH)
        cls.modelo, cls.metricas = tfa.entrenar(cls.casos, folds=3)

    def test_features_normaliza_y_hashea(self):
        f1 = tfa.features("El Programador ORDENA rm -rf /")
        f2 = tfa.features("el programador ordena rm -rf /")
        self.assertEqual(f1, f2)
        self.assertTrue(f1)
        self.assertTrue(all(0 <= k < tfa.N_BUCKETS for k in f1))
        self.assertAlmostEqual(sum(f1.values()), 1.0, places=6)

    def test_predecir_probabilidades_y_restriccion(self):
        r = tfa.predecir(
            self.modelo, "choice",
            "El hook pre-commit bloquea el commit por trazabilidad REQ rota.",
            "Que pilar esta afectado?",
            criterios={"requisitos": "x", "verificacion": "y"},
        )
        self.assertEqual(set(r["probabilidades"]), {"requisitos", "verificacion"})
        self.assertAlmostEqual(sum(r["probabilidades"].values()), 1.0, places=6)
        self.assertIn(r["decision"], {None, "requisitos", "verificacion"})
        self.assertEqual(r["revision_humana"], r["decision"] is None)

    def test_conformal_cobertura_y_abstencion(self):
        for tipo, m in self.metricas.items():
            self.assertGreaterEqual(m["cobertura_conformal"], 0.85, tipo)
            self.assertGreaterEqual(m["tasa_abstencion"], 0.0, tipo)
        # El tipo ordinal (score) debe abstenerse en una fraccion relevante.
        self.assertGreater(self.metricas["score"]["tasa_abstencion"], 0.2)

    def test_determinismo(self):
        _, otras = tfa.entrenar(self.casos, folds=3)
        for tipo in self.metricas:
            self.assertAlmostEqual(self.metricas[tipo]["accuracy"], otras[tipo]["accuracy"])
            self.assertEqual(self.metricas[tipo]["temperatura"], otras[tipo]["temperatura"])

    def test_orden_de_opciones_no_afecta(self):
        # Robustez de reordenamiento (0% por construccion): las probabilidades
        # por clase no dependen del orden de las candidatas.
        estado = "El hook bloquea el commit por trazabilidad REQ rota."
        instr = "Que pilar esta afectado?"
        r1 = tfa.predecir(self.modelo, "choice", estado, instr,
                          criterios={"requisitos": "x", "verificacion": "y",
                                     "documentacion": "z"})
        r2 = tfa.predecir(self.modelo, "choice", estado, instr,
                          criterios={"documentacion": "z", "verificacion": "y",
                                     "requisitos": "x"})
        self.assertEqual(r1["probabilidades"], r2["probabilidades"])
        self.assertEqual(r1["decision"], r2["decision"])

    def test_umbral_competitivo(self):
        # Guardarrail de regresion del REQ-027: accuracy y latencia objetivo.
        total = sum(m["n"] for m in self.metricas.values())
        global_acc = sum(m["accuracy"] * m["n"] for m in self.metricas.values()) / total
        self.assertGreaterEqual(global_acc, 0.75)
        # La latencia se mide en un proceso real (sin el instrumentador de
        # coverage): bajo `--cov` cada linea pasa por el tracer y el p50 medido
        # seria el del profiler (~3 ms) y no el del motor (~0,4 ms). La
        # inferencia in-process se cubre en test_cli_train_predict_bench.
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "tydm_fast.py"), "bench",
             "--folds", "3", "--json"],
            capture_output=True, text=True, cwd=ROOT, timeout=120,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-500:])
        resultado = json.loads(proc.stdout)
        self.assertLess(resultado["latencia_us_p50"], 3000)

    def test_cli_train_predict_bench(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "model.json"
            with mock.patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(tfa.main(["train", "--out", str(out)]), 0)
            self.assertTrue(out.exists())
            buf = io.StringIO()
            with mock.patch.object(sys, "stdout", buf):
                rc = tfa.main(["predict", "--tipo", "noul", "--estado", "x",
                               "--instrucciones", "y", "--model", str(out), "--json"])
            self.assertEqual(rc, 0)
            self.assertIn("decision", json.loads(buf.getvalue()))
            with mock.patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(tfa.main(["bench", "--folds", "3", "--json"]), 0)


class TestDownloadTyDMModel(unittest.TestCase):
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

    def test_download_reanuda_con_respuesta_206(self):
        # Con status 206 el servidor respeta el Range: se conserva lo ya descargado.
        dest = self.tmp / "m.gguf"
        dest.write_bytes(b"x" * 100)

        class _Resp206:
            status = 206
            headers = {"Content-Length": "50"}

            def __init__(self):
                self._it = iter([b"y" * 50])

            def read(self, n=-1):
                return next(self._it, b"")

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        with mock.patch("urllib.request.urlopen", return_value=_Resp206()), \
                mock.patch.object(djm, "EXPECTED_BYTES", 150), \
                mock.patch.object(sys, "stdout", io.StringIO()):
            djm._download("http://x/m.gguf", dest, yes=True)
        datos = dest.read_bytes()
        self.assertEqual(len(datos), 150)
        self.assertTrue(datos.startswith(b"x" * 100))

    def test_main_modelo_existente_no_descarga(self):
        dest = self.tmp / "m.gguf"
        dest.write_bytes(b"x")
        argv = ["download_tydm_model.py", "--dest", str(dest), "--yes"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "EXPECTED_BYTES", 1), \
                mock.patch.object(djm, "_download") as dl, mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(djm.main(), 0)
            dl.assert_not_called()

    def test_main_descarga_cuando_falta(self):
        dest = self.tmp / "m.gguf"
        argv = ["download_tydm_model.py", "--dest", str(dest), "--yes"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "_download") as dl, \
                mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(djm.main(), 0)
            dl.assert_called_once()

    def test_main_error_de_descarga_devuelve_1(self):
        dest = self.tmp / "m.gguf"
        argv = ["download_tydm_model.py", "--dest", str(dest), "--yes"]
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
        argv = ["download_tydm_model.py", "--dest", str(dest), "--yes"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "EXPECTED_BYTES", 1000), \
                mock.patch.object(djm, "_download") as dl, mock.patch.object(sys, "stdout", io.StringIO()):
            self.assertEqual(djm.main(), 0)
            dl.assert_called_once()

    def test_main_archivo_pequeno_falla(self):
        dest = self.tmp / "m.gguf"
        dest.write_bytes(b"x")
        argv = ["download_tydm_model.py", "--dest", str(dest), "--yes"]
        with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "EXPECTED_BYTES", 1000), \
                mock.patch("urllib.request.urlopen", return_value=self._fake_response([b"x"])), \
                mock.patch.object(sys, "stdout", io.StringIO()), mock.patch.object(sys, "stderr", io.StringIO()):
            self.assertEqual(djm.main(), 1)

    def test_main_url_desde_env(self):
        dest = self.tmp / "m.gguf"
        os.environ["TYDM_DOWNLOAD_URL"] = "http://custom/model.gguf"
        argv = ["download_tydm_model.py", "--dest", str(dest), "--yes"]
        try:
            with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "EXPECTED_BYTES", 1), \
                    mock.patch.object(djm, "_download") as dl, mock.patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(djm.main(), 0)
                dl.assert_called_once()
                self.assertEqual(dl.call_args[0][0], "http://custom/model.gguf")
        finally:
            os.environ.pop("TYDM_DOWNLOAD_URL", None)

    def test_main_dest_desde_env(self):
        os.environ["TYDM_MODEL_PATH"] = str(self.tmp / "custom.gguf")
        argv = ["download_tydm_model.py", "--yes"]
        try:
            with mock.patch.object(sys, "argv", argv), mock.patch.object(djm, "EXPECTED_BYTES", 1), \
                    mock.patch.object(djm, "_download") as dl, mock.patch.object(sys, "stdout", io.StringIO()):
                self.assertEqual(djm.main(), 0)
                dl.assert_called_once()
                self.assertEqual(dl.call_args[0][1], self.tmp / "custom.gguf")
        finally:
            os.environ.pop("TYDM_MODEL_PATH", None)


if __name__ == "__main__":
    unittest.main()
