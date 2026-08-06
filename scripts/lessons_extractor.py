#!/usr/bin/env python3
"""lessons_extractor.py — Valida y exporta lecciones de .docs/lessons/ (REQ-003).

Convierte los YAML de .docs/lessons/<anio>.yaml en un archivo plano
lessons_context.txt que los agentes leen sin parsear YAML.

Uso:
    python scripts/lessons_extractor.py            # valida + genera lessons_context.txt
    python scripts/lessons_extractor.py --check    # valida sin generar
    python scripts/lessons_extractor.py --json     # exporta a JSON por stdout
"""

import json
import sys
from pathlib import Path

try:
    import yaml

    HAS_YAML = True
except ImportError:
    HAS_YAML = False

ROOT = Path(__file__).resolve().parent.parent
LESSONS_DIR = ROOT / ".docs" / "lessons"
OUTPUT = ROOT / "lessons_context.txt"

REQUIRED_FIELDS = {"id", "proyecto", "fase", "categoria", "problema", "recomendacion", "estado", "fecha"}
ALLOWED_STATES = {"Abierta", "Resuelta", "Descartada"}


def _parse_yaml(text: str) -> list[dict]:
    if HAS_YAML:
        data = yaml.safe_load(text)
        return data if isinstance(data, list) else []
    return _minimal_parser(text)


def _minimal_parser(text: str) -> list[dict]:
    """Parser minimo para la estructura plana: lista de mapas con escalares.

    `- id: LSN-001\n  problema: "texto"` -> [{"id": "LSN-001", "problema": "texto"}]
    Solo soporta valores escalares entre comillas o en una linea.
    """
    lessons: list[dict] = []
    current: dict | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("- "):
            if current:
                lessons.append(current)
            current = {}
            key, _, value = line[2:].partition(":")
            current[key.strip()] = _clean(value)
        elif line.startswith("  ") and current is not None and ":" in line:
            key, _, value = line.strip().partition(":")
            current[key.strip()] = _clean(value)
    if current:
        lessons.append(current)
    return lessons


def _clean(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def validate() -> tuple[list[dict], list[str]]:
    lessons: list[dict] = []
    problems: list[str] = []
    for path in sorted(LESSONS_DIR.glob("*.yaml")):
        try:
            parsed = _parse_yaml(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - reportar el error con detalle
            problems.append(f"{path.name}: no se puede parsear ({exc})")
            continue
        for lesson in parsed:
            if not isinstance(lesson, dict):
                problems.append(f"{path.name}: entrada no es un mapa")
                continue
            missing = REQUIRED_FIELDS - set(lesson)
            if missing:
                problems.append(
                    f"{path.name}: {lesson.get('id', '?')} faltan campos {sorted(missing)}"
                )
            if lesson.get("estado") not in ALLOWED_STATES:
                problems.append(
                    f"{path.name}: {lesson.get('id', '?')} estado '{lesson.get('estado')}' invalido"
                )
            lessons.append(lesson)
    return lessons, problems


def render_context(lessons: list[dict]) -> str:
    lines = [
        "# Contexto de lecciones aprendidas (generado por scripts/lessons_extractor.py)",
        "# No editar: se regenera al ejecutar el extractor.",
        f"# Total: {len(lessons)}",
        "",
    ]
    for lesson in sorted(lessons, key=lambda l: str(l.get("id", ""))):
        lines.append(f"## {lesson.get('id', '?')} [{lesson.get('estado', '?')}] {lesson.get('proyecto', '')}")
        lines.append(f"- fase: {lesson.get('fase', '')}")
        lines.append(f"- categoria: {lesson.get('categoria', '')}")
        lines.append(f"- fecha: {lesson.get('fecha', '')}")
        lines.append(f"- problema: {lesson.get('problema', '')}")
        lines.append(f"- recomendacion: {lesson.get('recomendacion', '')}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    lessons, problems = validate()
    for problem in problems:
        print(f"[ERROR] {problem}")

    if "--check" in sys.argv:
        print(f"lessons_extractor: {len(lessons)} lecciones, {len(problems)} errores")
        return 1 if problems else 0

    if "--json" in sys.argv:
        print(json.dumps(lessons, ensure_ascii=False, indent=2))
        return 0

    if problems:
        print("lessons_extractor: no se genera contexto con errores de validacion")
        return 1

    OUTPUT.write_text(render_context(lessons), encoding="utf-8")
    print(f"lessons_extractor: {len(lessons)} lecciones -> lessons_context.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
