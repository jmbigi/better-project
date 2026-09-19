#!/usr/bin/env python3
"""jev_llama.py — Cliente Jev AI liviano con llama.cpp (REQ-011).

Carga un modelo GGUF pequeño (~3–6 GB) y responde preguntas tipadas
(`noul`, `choice`, `score`) leyendo logits del modelo, sin samplear tokens.

Uso:
    JEV_MODEL_PATH=/ruta/al/modelo.gguf python3 scripts/jev_llama.py --demo
    python3 scripts/jev_llama.py --input decisions.json

Configuracion por entorno:
    JEV_MODEL_PATH    ruta al modelo GGUF (default: ~/.cache/better-project/jev/Qwen3.5-4B-Q4_K_M.gguf)
    JEV_N_CTX         contexto maximo (default: 4096)
    JEV_N_THREADS     hilos CPU (default: None -> auto)
    JEV_TIMEOUT       timeout de carga en segundos (default: 300)

Dependencia opcional:
    pip install -r requirements-optional.txt
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "Qwen3.5-4B-Q4_K_M.gguf"
DEFAULT_N_CTX = 4096
DEFAULT_TIMEOUT = 300


def _default_model_path() -> Path:
    return Path.home() / ".cache" / "better-project" / "jev" / DEFAULT_MODEL


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw is not None else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw is not None else default


def _softmax(logits: Any) -> list[float]:
    """Softmax sobre una secuencia numerica (lista o ndarray)."""
    vals = [float(x) for x in logits]
    mx = max(vals)
    ex = [math.exp(x - mx) for x in vals]
    s = sum(ex)
    return [e / s for e in ex]


def _confidence(probs: list[float]) -> float:
    """Confianza = 1 - H(p)/ln(K). 1=certeza, 0=uniforme."""
    k = len(probs)
    h = -sum(p * math.log(p) for p in probs if p > 0)
    return max(0.0, min(1.0, 1.0 - h / math.log(k)))


class JevLlama:
    """Motor de decisiones tipadas con un modelo GGUF local."""

    def __init__(
        self,
        model_path: str | Path | None = None,
        n_ctx: int | None = None,
        n_threads: int | None = None,
        timeout: float | None = None,
    ) -> None:
        self.model_path = Path(model_path) if model_path else _default_model_path()
        self.n_ctx = n_ctx if n_ctx is not None else _env_int("JEV_N_CTX", DEFAULT_N_CTX)
        self.n_threads = n_threads if n_threads is not None else os.getenv("JEV_N_THREADS")
        self.timeout = timeout if timeout is not None else _env_float("JEV_TIMEOUT", DEFAULT_TIMEOUT)

        if not self.model_path.exists():
            raise FileNotFoundError(
                f"No se encontro el modelo GGUF: {self.model_path}. "
                f"Descargalo con: python3 scripts/download_jev_model.py"
            )

        try:
            import numpy as np
            from llama_cpp import Llama
        except ImportError as exc:
            raise ImportError(
                "llama-cpp-python no esta instalado. "
                "Ejecuta: pip install -r requirements-optional.txt"
            ) from exc
        self._np = np

        kwargs: dict[str, Any] = {
            "model_path": str(self.model_path),
            "n_ctx": self.n_ctx,
            "verbose": False,
        }
        if self.n_threads is not None:
            kwargs["n_threads"] = int(self.n_threads)

        # llama-cpp-python no expone timeout de carga; usamos alarma si el SO lo soporta.
        try:
            import signal

            def _alarm_handler(signum, frame):
                raise TimeoutError(f"Timeout cargando el modelo tras {self.timeout}s")

            old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
            signal.setitimer(signal.ITIMER_REAL, self.timeout)
            try:
                self.model = Llama(**kwargs)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, old_handler)
        except (ImportError, AttributeError):
            self.model = Llama(**kwargs)

    def _tokenize(self, text: str, add_bos: bool = False) -> list[int]:
        return self.model.tokenize(text.encode("utf-8"), add_bos=add_bos)

    def _first_token_probs(self, prompt: str, token_ids: list[int]) -> list[float]:
        """Probabilidades del PRIMER token de cada opcion dado un prompt.

        Limitacion documentada: para opciones multi-token solo se considera el
        primer token. Esto es suficiente para la mayoria de las decisiones Jev
        donde las opciones comienzan con tokens distintivos.
        """
        tokens = self._tokenize(prompt, add_bos=True)
        self.model.eval(tokens)
        logits = self._np.array(self.model.scores)
        probs = _softmax(logits)
        return [float(probs[tid]) for tid in token_ids]

    @staticmethod
    def _build_prompt(state: str, question: dict[str, Any]) -> str:
        instructions = question.get("instructions", "Answer about the state.")
        kind = question["type"]
        prompt = f"State: {state}\n\nQuestion: {instructions}\n"
        if kind == "noul":
            prompt += 'Answer only "yes" or "no".\nAnswer: '
        elif kind == "choice":
            prompt += "Options:\n"
            for opt_id, desc in question["criteria"].items():
                prompt += f"- {opt_id}: {desc}\n"
            prompt += "Answer with the exact option id.\nAnswer: "
        elif kind == "score":
            prompt += "Levels:\n"
            for i, level in enumerate(question["criteria"]):
                prompt += f"- {i}: {level}\n"
            prompt += "Answer with the level number.\nAnswer: "
        return prompt

    def _answer_noul(self, state: str, question: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(state, question)
        yes_tok = self._tokenize("yes", add_bos=False)[0]
        no_tok = self._tokenize("no", add_bos=False)[0]
        raw = self._first_token_probs(prompt, [yes_tok, no_tok])
        probs = _softmax([math.log(p + 1e-12) for p in raw])
        probs_list = [float(probs[0]), float(probs[1])]
        return {
            "type": "noul",
            "noul": probs_list[0],
            "probabilities": {"yes": probs_list[0], "no": probs_list[1]},
            "confidence": _confidence(probs_list),
        }

    def _answer_choice(self, state: str, question: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(state, question)
        options = list(question["criteria"].keys())
        token_ids = [self._tokenize(opt, add_bos=False)[0] for opt in options]
        raw = self._first_token_probs(prompt, token_ids)
        probs = _softmax([math.log(p + 1e-12) for p in raw])
        probs_list = [float(p) for p in probs]
        top = int(self._np.argmax(probs))
        return {
            "type": "choice",
            "choice": options[top],
            "probabilities": dict(zip(options, probs_list)),
            "confidence": _confidence(probs_list),
        }

    def _answer_score(self, state: str, question: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(state, question)
        levels = list(range(len(question["criteria"])))
        token_ids = [self._tokenize(str(i), add_bos=False)[0] for i in levels]
        raw = self._first_token_probs(prompt, token_ids)
        probs = _softmax([math.log(p + 1e-12) for p in raw])
        probs_list = [float(p) for p in probs]
        top = int(self._np.argmax(probs))
        return {
            "type": "score",
            "score": sum(i * probs_list[i] for i in levels),
            "legend": {str(i): question["criteria"][i] for i in levels},
            "probabilities": {str(i): probs_list[i] for i in levels},
            "confidence": _confidence(probs_list),
        }

    def decide(self, state: str, questions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Responde un conjunto de preguntas tipadas sobre un estado."""
        if not isinstance(questions, dict):
            raise ValueError("'questions' debe ser un diccionario {id: pregunta}")
        answers: dict[str, dict[str, Any]] = {}
        for qid, question in questions.items():
            kind = question.get("type")
            if kind == "noul":
                answers[qid] = self._answer_noul(state, question)
            elif kind == "choice":
                answers[qid] = self._answer_choice(state, question)
            elif kind == "score":
                answers[qid] = self._answer_score(state, question)
            else:
                raise ValueError(f"Tipo de pregunta desconocido en '{qid}': {kind}")
        return answers


def _demo() -> None:
    client = JevLlama()
    state = (
        "El pipeline de CI fallo en el ultimo commit porque un test nuevo "
        "referencia un REQ que no existe en .docs/requirements/."
    )
    questions = {
        "bloqueante": {
            "type": "noul",
            "instructions": "¿El fallo bloquea el merge a main?",
        },
        "area": {
            "type": "choice",
            "instructions": "¿Que area del ecosistema esta afectada?",
            "criteria": {
                "requisitos": "trazabilidad REQ",
                "verificacion": "tests o hooks",
                "documentacion": "docs o knowledge",
            },
        },
        "severidad": {
            "type": "score",
            "instructions": "¿Que tan severo es el problema?",
            "criteria": ["bajo", "medio", "alto", "critico"],
        },
    }
    result = client.decide(state, questions)
    print(json.dumps(result, indent=2, ensure_ascii=False))


def _main() -> int:
    if "--demo" in sys.argv:
        _demo()
        return 0

    if "--input" in sys.argv:
        idx = sys.argv.index("--input")
        if idx + 1 >= len(sys.argv):
            print("Uso: python3 scripts/jev_llama.py --input <archivo.json>", file=sys.stderr)
            return 1
        path = Path(sys.argv[idx + 1])
        data = json.loads(path.read_text(encoding="utf-8"))
        client = JevLlama()
        result = client.decide(data["state"], data["questions"])
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print("Uso: python3 scripts/jev_llama.py --demo | --input <archivo.json>", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_main())
