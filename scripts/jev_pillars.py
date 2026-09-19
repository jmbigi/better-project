#!/usr/bin/env python3
"""jev_pillars.py — Integracion de Jev con los tres pilares del ecosistema (REQ-012).

# REQ-012

Clasificacion **asistida** (no autoritativa) con el motor de REQ-011 sobre los
tres pilares: requisitos, conocimiento y lecciones. Propone etiquetas; nunca
escribe en los documentos (la aplicacion es una accion humana).

Uso:
    python3 scripts/jev_pillars.py requisitos --req REQ-011 [--json]
    python3 scripts/jev_pillars.py conocimiento --file docs/REGLAS-COMPLETAS.md [--json]
    python3 scripts/jev_pillars.py lecciones --id LSN-008 [--json]

Configuracion por entorno:
    JEV_MODEL_PATH        ruta al GGUF (ver jev_llama.py)
    JEV_TEMPERATURE       temperatura de calibracion (ver jev_calibration.py)
    JEV_MIN_CONFIDENCE    umbral de confianza (default 0.5)
    JEV_CALIBRATION_REPORT  informe de calibracion (default .docs/.storage/jev_calibration.json)

Dependencia opcional: llama-cpp-python (via jev_llama).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import lessons_extractor as le
from jev_llama import JevLlama

ROOT = Path(__file__).resolve().parent.parent
REQ_DIR = ROOT / ".docs" / "requirements"
LESSONS_DIR = ROOT / ".docs" / "lessons"
DEFAULT_CALIBRATION_REPORT = ROOT / ".docs" / ".storage" / "jev_calibration.json"
DEFAULT_MIN_CONFIDENCE = 0.5
# Umbral de accuracy por tarea (REQ-012, criterio 6).
ACCURACY_MINIMA = 0.6

# Cada pilar declara sus preguntas (campo -> pregunta tipada de jev_llama).
PREGUNTAS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "requisitos": [
        (
            "prioridad",
            {
                "type": "choice",
                "instructions": "¿Que prioridad corresponde a este requisito?",
                "criteria": {"Baja": "Baja", "Media": "Media", "Alta": "Alta"},
            },
        )
    ],
    "conocimiento": [
        (
            "relevancia",
            {
                "type": "score",
                "instructions": "¿Que puntuacion de relevancia y calidad tiene este fragmento?",
                "criteria": ["irrelevante", "baja", "media", "alta"],
            },
        )
    ],
    "lecciones": [
        (
            "fase",
            {
                "type": "choice",
                "instructions": "¿A que fase corresponde esta leccion?",
                "criteria": {
                    "Diseno": "Diseno",
                    "Implementacion": "Implementacion",
                    "Testing": "Testing",
                    "Deploy": "Deploy",
                },
            },
        ),
        (
            "categoria",
            {
                "type": "choice",
                "instructions": "¿A que categoria corresponde esta leccion?",
                "criteria": {
                    "Proceso": "Proceso",
                    "Seguridad": "Seguridad",
                    "Riesgo_Tecnico": "Riesgo tecnico",
                },
            },
        ),
    ],
}

# Tipo de pregunta Jev asociado a cada pilar (para la accuracy de referencia).
TIPO_POR_PILAR = {"requisitos": "choice", "conocimiento": "score", "lecciones": "choice"}


def _strip_frontmatter(text: str) -> str:
    """Elimina el bloque YAML inicial (--- ... ---) para no filtrar etiquetas."""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[2].lstrip("\n")
    return text


def _leer_requisito(req_id: str) -> str:
    path = REQ_DIR / f"{req_id}.md"
    if not path.exists():
        raise FileNotFoundError(f"No existe el requisito {req_id} en {REQ_DIR}")
    # Sin frontmatter: contiene el campo 'prioridad' que es justo lo que se clasifica.
    return _strip_frontmatter(path.read_text(encoding="utf-8"))


def _buscar_leccion(lesson_id: str) -> dict[str, Any]:
    lessons, _ = le.validate()
    for lesson in lessons:
        if str(lesson.get("id")) == lesson_id:
            return lesson
    raise ValueError(f"No se encontro la leccion {lesson_id} en {LESSONS_DIR}")


def _texto_leccion(lesson: dict[str, Any]) -> str:
    problema = str(lesson.get("problema", "")).strip()
    recomendacion = str(lesson.get("recomendacion", "")).strip()
    return f"Problema: {problema}\nRecomendacion: {recomendacion}".strip()


def _texto_desde_archivo(path: Path, pilar: str) -> tuple[str, str]:
    raw = path.read_text(encoding="utf-8")
    if pilar == "lecciones":
        try:
            parsed = le._parse_yaml(raw)
        except Exception:  # noqa: BLE001 - un archivo no YAML se trata como texto
            parsed = []
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            return path.name, _texto_leccion(parsed[0])
        if isinstance(parsed, dict):
            return path.name, _texto_leccion(parsed)
    if pilar == "requisitos":
        return path.name, _strip_frontmatter(raw)
    return path.name, raw


def resolver_entrada(pilar: str, args: argparse.Namespace) -> tuple[str, str]:
    """Devuelve (id, texto) segun el pilar y las opciones, o falla explicito."""
    if pilar == "requisitos":
        if sum([bool(args.req), bool(args.file), bool(args.text)]) != 1:
            raise ValueError("requisitos requiere exactamente uno de --req, --file o --text")
        if args.req:
            return args.req, _leer_requisito(args.req)
    elif pilar == "conocimiento":
        if bool(args.file) == bool(args.text):
            raise ValueError("conocimiento requiere exactamente uno de --file o --text")
    elif pilar == "lecciones":
        if sum([bool(args.id), bool(args.file), bool(args.text)]) != 1:
            raise ValueError("lecciones requiere exactamente uno de --id, --file o --text")
        if args.id:
            return args.id, _texto_leccion(_buscar_leccion(args.id))
    else:
        raise ValueError(f"Pilar desconocido: {pilar}")

    if args.file:
        return _texto_desde_archivo(Path(args.file), pilar)
    if args.text:
        return "texto", args.text
    raise ValueError(f"{pilar}: entrada no resuelta")


def accuracy_por_tipo(report_path: Path) -> dict[str, float]:
    """Accuracy por tipo medida en el set de calibracion (REQ-011).

    Reutiliza el informe generado por jev_calibration.py. Si el informe no
    existe o no trae la seccion por tipo, devuelve {} (el consumidor debe
    marcarlo como experimental; no se inventan valores, P1.19/P1.29).
    """
    if not report_path.exists():
        return {}
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Informe de calibracion invalido {report_path}: {exc}") from exc
    por_tipo = data.get("por_tipo_Trecomendada") or data.get("por_tipo_T1") or {}
    accuracies: dict[str, float] = {}
    for tipo, metricas in por_tipo.items():
        if isinstance(metricas, dict) and "accuracy" in metricas:
            accuracies[str(tipo)] = float(metricas["accuracy"])
    return accuracies


def construir_decision(
    entry_id: str,
    campo: str,
    resultado: dict[str, Any],
    umbral: float,
    accuracy: float | None,
) -> dict[str, Any]:
    """Objeto de decision con el esquema fijo de REQ-012 (criterio 5)."""
    probs = {str(k): float(v) for k, v in resultado["probabilities"].items()}
    confianza = float(resultado["confidence"])
    propuesta = max(probs, key=probs.get)
    definitiva = confianza >= umbral
    return {
        "id": entry_id,
        "campo": campo,
        "tipo": str(resultado["type"]),
        "decision": propuesta if definitiva else None,
        "propuesta": propuesta,
        "probabilities": probs,
        "confidence": confianza,
        "revision_humana": not definitiva,
        "accuracy_referencia": accuracy,
        "experimental": accuracy is None or accuracy < ACCURACY_MINIMA,
    }


def ejecutar(
    pilar: str,
    entry_id: str,
    texto: str,
    client: Any,
    umbral: float,
    accuracy: dict[str, float],
) -> dict[str, Any]:
    """Ejecuta un pilar: construye las preguntas, decide y arma la salida."""
    if pilar not in PREGUNTAS:
        raise ValueError(f"Pilar desconocido: {pilar}")
    preguntas = dict(PREGUNTAS[pilar])
    respuestas = client.decide(texto, preguntas)
    tipo = TIPO_POR_PILAR[pilar]
    acc = accuracy.get(tipo)
    decisiones = [
        construir_decision(entry_id, campo, respuestas[campo], umbral, acc)
        for campo, _ in PREGUNTAS[pilar]
    ]
    return {
        "subcomando": pilar,
        "id": entry_id,
        "tipo": tipo,
        "accuracy_referencia": acc,
        "experimental": acc is None or acc < ACCURACY_MINIMA,
        "decisiones": decisiones,
    }


def _print_human(salida: dict[str, Any]) -> None:
    print(f"Pilar: {salida['subcomando']}  id: {salida['id']}  tipo: {salida['tipo']}")
    acc = salida["accuracy_referencia"]
    etiqueta_acc = "desconocida" if acc is None else f"{acc:.3f}"
    print(f"Accuracy de referencia: {etiqueta_acc}  experimental: {salida['experimental']}")
    for d in salida["decisiones"]:
        valor = d["decision"] if d["decision"] is not None else f"(revision) {d['propuesta']}"
        print(
            f"  {d['campo']}: {valor}  confianza={d['confidence']:.3f}"
            f"  revision_humana={d['revision_humana']}"
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clasifica los tres pilares con Jev (REQ-012)")
    parser.add_argument("pilar", choices=sorted(PREGUNTAS))
    parser.add_argument("--req", help="ID de requisito, p.ej. REQ-011")
    parser.add_argument("--id", help="ID de leccion, p.ej. LSN-008")
    parser.add_argument("--file", help="Ruta de un archivo de entrada")
    parser.add_argument("--text", help="Texto de entrada directo")
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    parser.add_argument("--model", default=None, help="Ruta al GGUF (default: JEV_MODEL_PATH)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        entry_id, texto = resolver_entrada(args.pilar, args)
        umbral = float(os.getenv("JEV_MIN_CONFIDENCE", str(DEFAULT_MIN_CONFIDENCE)))
        report_path = Path(os.getenv("JEV_CALIBRATION_REPORT", str(DEFAULT_CALIBRATION_REPORT)))
        accuracy = accuracy_por_tipo(report_path)
        client = JevLlama(model_path=args.model)
        salida = ejecutar(args.pilar, entry_id, texto, client, umbral, accuracy)
    except (ValueError, FileNotFoundError, ImportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(salida, indent=2, ensure_ascii=False))
    else:
        _print_human(salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
