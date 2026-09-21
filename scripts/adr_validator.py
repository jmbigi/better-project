#!/usr/bin/env python3
"""adr_validator.py — Valida ADR y audita sesgos de decision (REQ-013, REQ-023).

# REQ-013
# REQ-023

Valida los Registros de Decision de Arquitectura de `docs/decisions/` y emite
alertas heuristicas de sesgos y falacias del Pilar 4
(`docs/SESGOS-Y-FALACIAS.md`): falsa dicotomia, equivoco/falsa precision,
premisas ocultas y afirmaciones absolutas.

Uso:
    python3 scripts/adr_validator.py            # errores -> exit 1
    python3 scripts/adr_validator.py --strict   # tambien las alertas -> exit 1
    python3 scripts/adr_validator.py --dir <ruta>

Sin dependencias externas (solo stdlib). La auditoria es heuristica: asiste la
revision humana, no la sustituye (P1.15).
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "docs" / "decisions"
ALLOWED_ESTADOS = {"Propuesto", "Aceptado", "Rechazado", "Reemplazado", "Deprecado"}
REQUIRED_FIELDS = {"id", "titulo", "estado", "fecha"}
REQUIRED_SECTIONS = ("contexto", "alternativas consideradas", "decision", "consecuencias")
RECOMMENDED_SECTIONS = ("supuestos", "metricas de exito")
# Seccion obligatoria para ADRs en estado Propuesto/Aceptado (Fase 3 Pilar 4)
PREMORTEM_SECTION = "pre-mortem (analisis prospectivo de fallos)"
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)
H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
ITEM_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+\S", re.M)

# Senales de sesgo/falacia (Pilar 4). Listas en minusculas y sin acentos.
AMBIGUOUS_WORDS = (
    "escalable", "robusto", "mantenible", "eficiente", "optimo", "rapido",
    "flexible", "limpio", "moderno", "seguro", "mejor",
)
ABSOLUTE_WORDS = ("siempre", "nunca", "obviamente", "claramente", "evidentemente", "indiscutible")


def _norm(text: str) -> str:
    """Minusculas sin acentos, para comparar terminos de forma robusta."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    meta: dict[str, str] = {}
    for line in match.group(1).strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def _sections(text: str) -> dict[str, str]:
    """Devuelve {titulo normalizado: cuerpo} de las secciones H2."""
    matches = list(H2_RE.finditer(text))
    sections: dict[str, str] = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[_norm(match.group(1))] = text[match.end():end]
    return sections


def _count_items(body: str) -> int:
    return len(ITEM_RE.findall(body))


def validate(directory: Path = ADR_DIR) -> tuple[list[str], list[str]]:
    """Valida los ADR de `directory` y devuelve (errores, alertas de sesgo)."""
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: dict[str, str] = {}
    paths = sorted(Path(directory).glob("ADR-*.md"))
    for path in paths:
        rel = path.name
        text = path.read_text(encoding="utf-8")
        meta = _parse_frontmatter(text)
        if meta is None:
            errors.append(f"{rel}: sin frontmatter YAML")
            continue
        missing = REQUIRED_FIELDS - set(meta)
        if missing:
            errors.append(f"{rel}: faltan campos frontmatter {sorted(missing)}")
        adr_id = meta.get("id", "")
        if not re.fullmatch(r"ADR-\d{3}", adr_id):
            errors.append(f"{rel}: 'id' invalido o ausente ('{adr_id}')")
        elif adr_id != "-".join(path.stem.split("-")[:2]):
            errors.append(f"{rel}: 'id' '{adr_id}' no coincide con el nombre del archivo")
        if adr_id in seen_ids:
            errors.append(f"{rel}: 'id' duplicado '{adr_id}' (ya en {seen_ids[adr_id]})")
        seen_ids[adr_id] = rel
        if meta.get("estado") not in ALLOWED_ESTADOS:
            errors.append(f"{rel}: estado '{meta.get('estado')}' no valido ({sorted(ALLOWED_ESTADOS)})")
        fecha = meta.get("fecha", "")
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
                raise ValueError
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            errors.append(f"{rel}: fecha '{fecha}' no valida (AAAA-MM-DD)")

        sections = _sections(text)
        for section in REQUIRED_SECTIONS:
            if section not in sections:
                errors.append(f"{rel}: falta la seccion obligatoria '## {section.title()}'")
        for section in RECOMMENDED_SECTIONS:
            if section not in sections:
                warnings.append(f"{rel}: falta la seccion recomendada '## {section.title()}' (premisas/metricas)")
        # Validar pre-mortem para ADRs en estado Propuesto o Aceptado
        estado = meta.get("estado", "")
        if estado in ("Propuesto", "Aceptado"):
            if PREMORTEM_SECTION not in sections:
                errors.append(f"{rel}: falta la seccion obligatoria '## Pre-mortem (Análisis Prospectivo de Fallos)' para estado {estado}")
            else:
                premortem_body = sections[PREMORTEM_SECTION]
                # Debe tener al menos 2 escenarios de fallo (items de lista)
                if _count_items(premortem_body) < 2:
                    errors.append(f"{rel}: pre-mortem debe detallar al menos 2 escenarios hipoteticos de fallo con sus mitigaciones")
        alternativas = sections.get("alternativas consideradas", "")
        if alternativas and _count_items(alternativas) < 2:
            warnings.append(
                f"{rel}: menos de dos alternativas (posible falsa dicotomia, Pilar 4)"
            )
        for section, body in sections.items():
            normalizado = _norm(body)
            hit = next((w for w in AMBIGUOUS_WORDS if w in normalizado), None)
            if hit and not re.search(r"\d", body):
                warnings.append(
                    f"{rel}: '{hit}' sin metrica en '## {section}' (equivoco/falsa precision, Pilar 4)"
                )
        normalizado_total = _norm(text)
        for word in ABSOLUTE_WORDS:
            if word in normalizado_total:
                warnings.append(
                    f"{rel}: afirmacion absoluta '{word}' (exceso de confianza, Pilar 4)"
                )
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Valida ADR y audita sesgos (REQ-013)")
    parser.add_argument("--dir", default=str(ADR_DIR), help="Directorio de ADR")
    parser.add_argument("--strict", action="store_true", help="Las alertas de sesgo tambien fallan")
    args = parser.parse_args(argv)

    directory = Path(args.dir)
    if not directory.exists():
        print(f"Error: no existe el directorio de ADR {directory}", file=sys.stderr)
        return 1
    errors, warnings = validate(directory)
    for e in errors:
        print(f"[ERROR] {e}")
    for w in warnings:
        print(f"[ALERTA] {w}")
    print(f"ADR validados: {len(list(directory.glob('ADR-*.md')))} | errores: {len(errors)} | alertas: {len(warnings)}")
    if errors or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
