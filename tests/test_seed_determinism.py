#!/usr/bin/env python3
# REQ-011: Test empírico de determinismo (seed) para inferencias locales
# Verifica que la misma entrada produce la misma salida (varianza = 0)
import unittest
import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class TestSeedDeterminism(unittest.TestCase):
    """Test empírico de reproducibilidad determinista."""

    jev_llama_path: Path
    model_path: str | None

    @classmethod
    def setUpClass(cls):
        cls.jev_llama_path = Path(__file__).parent.parent / "scripts" / "jev_llama.py"
        cls.model_path = os.environ.get("JEV_MODEL_PATH")
        if not cls.model_path or not Path(cls.model_path).exists():
            raise unittest.SkipTest("JEV_MODEL_PATH no configurado o modelo no existe")

    def _run_jev_llama(self, prompt: str, seed: int | None = None) -> dict[str, Any]:
        """Ejecuta jev_llama.py con un prompt y retorna la respuesta parseada."""
        env = os.environ.copy()
        if seed is not None:
            env["JEV_SEED"] = str(seed)
        # Usar --input con JSON temporal
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            input_data = {
                "state": prompt,
                "questions": {
                    "q1": {"type": "noul", "instructions": "¿Sí o no?"}
                }
            }
            json.dump(input_data, f)
            input_file = f.name
        try:
            result = subprocess.run(
                [sys.executable, str(self.jev_llama_path), "--input", input_file],
                capture_output=True,
                text=True,
                timeout=60,
                env=env
            )
            return json.loads(result.stdout) if result.stdout else {}
        finally:
            Path(input_file).unlink(missing_ok=True)

    def test_deterministic_same_seed(self):
        """Mismo seed + mismo prompt = misma salida (varianza 0)."""
        prompt = "Estado de prueba para determinismo"
        seed = 42
        n_runs = 5

        results = []
        for _ in range(n_runs):
            res = self._run_jev_llama(prompt, seed)
            if "q1" in res and "noul" in res["q1"]:
                results.append(res["q1"]["noul"])

        self.assertEqual(len(results), n_runs, "Todas las ejecuciones deben producir respuesta")
        # Verificar que todas son idénticas
        first = results[0]
        for r in results[1:]:
            self.assertEqual(r, first, f"Salida no determinista: {r} != {first}")

    def test_different_seeds_different_outputs(self):
        """Seeds diferentes pueden producir salidas diferentes (no garantizado, pero probable)."""
        prompt = "Estado de prueba para variabilidad"
        results = []
        for seed in [1, 2, 3, 4, 5]:
            res = self._run_jev_llama(prompt, seed)
            if "q1" in res and "noul" in res["q1"]:
                results.append(res["q1"]["noul"])

        # Al menos 2 de 5 deberían ser diferentes (probabilidad alta)
        unique = set(results)
        self.assertGreater(len(unique), 1, "Seeds diferentes deberían producir variabilidad")

    def test_no_seed_non_deterministic(self):
        """Sin seed explícito, comportamiento no determinista (o seed aleatorio)."""
        prompt = "Estado sin seed fijo"
        results = []
        for _ in range(3):
            res = self._run_jev_llama(prompt, seed=None)
            if "q1" in res and "noul" in res["q1"]:
                results.append(res["q1"]["noul"])

        # Sin seed fijo, no garantizamos determinismo
        # Solo verificamos que no crashea
        self.assertEqual(len(results), 3)


class TestDeterminismWithoutModel(unittest.TestCase):
    """Tests de determinismo que no requieren modelo GGUF (usando mocks)."""

    def test_confidence_function_deterministic(self):
        """_confidence() es determinista para misma entrada."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        from jev_llama import _confidence

        # Distribución uniforme -> confidence = 0
        self.assertAlmostEqual(_confidence([0.5, 0.5]), 0.0, places=9)
        self.assertAlmostEqual(_confidence([1/3, 1/3, 1/3]), 0.0, places=9)

        # Distribución cierta -> confidence = 1
        self.assertAlmostEqual(_confidence([1.0, 0.0]), 1.0, places=9)
        self.assertAlmostEqual(_confidence([1.0, 0.0, 0.0]), 1.0, places=9)

        # Múltiples llamadas = mismo resultado (valor real calculado)
        expected = 0.1187091007693073
        for _ in range(10):
            self.assertAlmostEqual(_confidence([0.7, 0.3]), expected, places=9)

    def test_build_prompt_deterministic(self):
        """_build_prompt() produce salida idéntica para misma entrada."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import jev_llama as jl

        state = "estado de prueba"
        question = {"type": "noul", "instructions": "¿Sí o no?"}

        prompts = [jl.JevLlama._build_prompt(state, question) for _ in range(10)]
        self.assertEqual(len(set(prompts)), 1, "Prompt debe ser determinista")

    def test_calibration_math_deterministic(self):
        """Funciones matemáticas de calibración son deterministas."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        import jev_calibration as jc

        probs = [0.7, 0.3]
        # softmax
        for _ in range(10):
            self.assertEqual(jc.softmax(probs, 1.0), jc.softmax(probs, 1.0))
            self.assertEqual(jc.softmax(probs, 0.5), jc.softmax(probs, 0.5))

        # temperature_scale
        for _ in range(10):
            self.assertEqual(jc.temperature_scale(probs, 1.0), jc.temperature_scale(probs, 1.0))
            self.assertEqual(jc.temperature_scale(probs, 2.0), jc.temperature_scale(probs, 2.0))

        # nll, brier, ece - toman lista de floats, no records
        for _ in range(10):
            self.assertEqual(jc.nll(probs, 0), jc.nll(probs, 0))
            self.assertEqual(jc.brier(probs, 0), jc.brier(probs, 0))
            self.assertEqual(jc.ece([probs], [0], 10), jc.ece([probs], [0], 10))


if __name__ == "__main__":
    unittest.main()
