#!/usr/bin/env python3
"""jev_review.py — Revision humana asistida de clasificaciones Jev (REQ-016).

# REQ-016

Muestra las clasificaciones propuestas por `scripts/jev_pillars.py` (REQ-012)
en una interfaz de terminal (curses) y pide confirmacion al programador
(P1.15/P1.22). NO aplica cambios a los documentos: guarda la revision en un
JSON generado (`.docs/.storage/jev_review.json`).

Uso:
    python3 scripts/jev_review.py                 # UI curses (modelo real)
    python3 scripts/jev_review.py --report        # tabla por consola + JSON
    python3 scripts/jev_review.py --fake --limit 5  # sin modelo (demo/tests)

Teclas en la UI: y=OK  n=corregir (1..K elige opcion)  s=saltar  q=salir.
"""

from __future__ import annotations

import argparse
import curses
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import jev_pillars as jp
import lessons_extractor as le
from jev_llama import JevLlama

ROOT = Path(__file__).resolve().parent.parent
REQ_DIR = ROOT / ".docs" / "requirements"
LESSONS_DIR = ROOT / ".docs" / "lessons"
DEFAULT_REPORT = ROOT / ".docs" / ".storage" / "jev_review.json"
UMBRAL = 0.5


class _ClienteFalso:
    """Cliente determinista para demo/tests sin cargar el modelo."""

    def decide(self, state, questions):
        respuestas = {}
        for campo, q in questions.items():
            opciones = list(q["criteria"]) if isinstance(q["criteria"], dict) else q["criteria"]
            ganador = opciones[0] if isinstance(opciones[0], str) else str(opciones[0])
            n = len(opciones)
            probs = {str(o): (0.6 if i == 0 else 0.4 / max(1, n - 1)) for i, o in enumerate(opciones)}
            if q["type"] == "score":
                respuestas[campo] = {
                    "type": "score", "score": 0.0, "probabilities": probs, "confidence": 0.5,
                }
            else:
                respuestas[campo] = {
                    "type": "choice", "choice": ganador, "probabilities": probs, "confidence": 0.5,
                }
        return respuestas


def _cuerpo_sin_frontmatter(text: str) -> str:
    if text.startswith("---"):
        partes = text.split("---", 2)
        if len(partes) >= 3:
            return partes[2].strip()
    return text.strip()


def construir_items(pilares: list[str], limit: int | None = None) -> list[dict[str, Any]]:
    """Devuelve [(pilar, id, texto)] segun los pilares pedidos."""
    items: list[dict[str, Any]] = []
    if "requisitos" in pilares:
        for path in sorted(REQ_DIR.glob("REQ-*.md")):
            items.append(
                {"pilar": "requisitos", "id": path.stem,
                 "texto": _cuerpo_sin_frontmatter(path.read_text(encoding="utf-8"))}
            )
    if "lecciones" in pilares:
        lessons, _ = le.validate()
        for lesson in sorted(lessons, key=lambda l: str(l.get("id", ""))):
            texto = f"Problema: {lesson.get('problema', '')}\nRecomendacion: {lesson.get('recomendacion', '')}"
            items.append({"pilar": "lecciones", "id": str(lesson.get("id")), "texto": texto})
    if "conocimiento" in pilares:
        for path in sorted((ROOT / ".docs" / "knowledge").rglob("*.md")):
            items.append(
                {"pilar": "conocimiento", "id": path.name,
                 "texto": path.read_text(encoding="utf-8")}
            )
    return items[:limit] if limit else items


def filas_de_item(item: dict[str, Any], client: Any, accuracy: dict[str, float]) -> list[dict[str, Any]]:
    """Clasifica UN item y devuelve sus filas de revision (una por decision)."""
    salida = jp.ejecutar(item["pilar"], item["id"], item["texto"], client, UMBRAL, accuracy)
    return [
        {
            "item": item["id"],
            "pilar": item["pilar"],
            "campo": decision["campo"],
            "tipo": decision["tipo"],
            "opciones": list(decision["probabilities"].keys()),
            "propuesta": decision["propuesta"],
            "confianza": decision["confidence"],
            "revision_humana": decision["revision_humana"],
            "estado": "pendiente",
            "decision_final": None,
        }
        for decision in salida["decisiones"]
    ]


def clasificar(items: list[dict[str, Any]], client: Any, accuracy: dict[str, float]) -> list[dict[str, Any]]:
    """Convierte items en filas de revision (una por decision)."""
    filas: list[dict[str, Any]] = []
    for item in items:
        filas.extend(filas_de_item(item, client, accuracy))
    return filas


def aplicar_decision(fila: dict[str, Any], tecla: str, opcion: str | None = None) -> None:
    """Aplica la revision del programador a una fila."""
    if tecla == "y":
        fila["estado"] = "ok"
        fila["decision_final"] = fila["propuesta"]
    elif tecla == "n":
        fila["estado"] = "corregir"
        fila["decision_final"] = opcion
    elif tecla == "s":
        fila["estado"] = "saltar"
        fila["decision_final"] = None


def guardar_revision(filas: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    resumen = {
        "fecha": date.today().isoformat(),
        "total": len(filas),
        "ok": sum(1 for f in filas if f["estado"] == "ok"),
        "corregir": sum(1 for f in filas if f["estado"] == "corregir"),
        "saltar": sum(1 for f in filas if f["estado"] == "saltar"),
        "pendiente": sum(1 for f in filas if f["estado"] == "pendiente"),
        "filas": filas,
    }
    path.write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")


def imprimir_tabla(filas: list[dict[str, Any]]) -> None:
    print(f"{'item':<14}{'pilar':<14}{'campo':<13}{'propuesta':<18}{'conf':>6}  estado")
    for f in filas:
        print(
            f"{f['item']:<14}{f['pilar']:<14}{f['campo']:<13}{str(f['propuesta']):<18}"
            f"{f['confianza']:>6.2f}  {f['estado']}"
        )


def _dibujar(stdscr, fila: dict[str, Any], cabecera: str, mensaje: str) -> None:
    stdscr.clear()
    alto, ancho = stdscr.getmaxyx()
    stdscr.addnstr(0, 0, f"REVISION JEV (REQ-016)  {cabecera}", ancho - 1, curses.A_BOLD)
    stdscr.addnstr(1, 0, f"{fila['item']}  [{fila['pilar']}/{fila['campo']}]  tipo={fila['tipo']}", ancho - 1)
    texto = f"Propuesta: {fila['propuesta']}   confianza={fila['confianza']:.2f}"
    stdscr.addnstr(2, 0, texto, ancho - 1)
    stdscr.addnstr(4, 0, "Opciones:", ancho - 1)
    for i, op in enumerate(fila["opciones"], 1):
        stdscr.addnstr(5 + i, 2, f"{i}) {op}", ancho - 3)
    stdscr.addnstr(alto - 2, 0, mensaje, ancho - 1)
    stdscr.addnstr(alto - 1, 0, "y=OK  n=corregir (elige 1..K)  s=saltar  q=salir", ancho - 1)
    stdscr.refresh()


def repl_curses(items: list[dict[str, Any]], client: Any, accuracy: dict[str, float]) -> list[dict[str, Any]]:
    """UI incremental: clasifica cada item y pregunta su confirmacion al momento."""
    filas: list[dict[str, Any]] = []

    def _run(stdscr):
        for n_item, item in enumerate(items, 1):
            nuevas = filas_de_item(item, client, accuracy)
            filas.extend(nuevas)
            for fila in nuevas:
                cabecera = f"item {n_item}/{len(items)}  fila {len(filas)}"
                mensaje = "y=aceptar  n=corregir  s=saltar"
                while True:
                    _dibujar(stdscr, fila, cabecera, mensaje)
                    tecla = stdscr.getkey()
                    if tecla == "q":
                        return
                    if tecla in ("y", "s"):
                        aplicar_decision(fila, tecla)
                        break
                    if tecla == "n":
                        _dibujar(stdscr, fila, cabecera, "Pulsa el numero de la opcion correcta")
                        num = stdscr.getkey()
                        if num.isdigit() and 1 <= int(num) <= len(fila["opciones"]):
                            aplicar_decision(fila, "n", fila["opciones"][int(num) - 1])
                            break
                        mensaje = "Opcion no valida"
                    else:
                        mensaje = f"Tecla no valida: {tecla!r}"

    curses.wrapper(_run)
    return filas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Revision humana de clasificaciones Jev (REQ-016)")
    parser.add_argument("--pilar", action="append", choices=["requisitos", "lecciones", "conocimiento"],
                        help="Pilar a revisar (repetible; default: requisitos y lecciones)")
    parser.add_argument("--limit", type=int, default=None, help="Maximo de items")
    parser.add_argument("--report", action="store_true", help="Tabla por consola (sin UI)")
    parser.add_argument("--fake", action="store_true", help="Cliente simulado (sin modelo)")
    parser.add_argument("--out", default=None, help="Ruta del JSON de revision")
    parser.add_argument("--model", default=None, help="Ruta al GGUF (modelo real)")
    args = parser.parse_args(argv)

    pilares = args.pilar or ["requisitos", "lecciones"]
    items = construir_items(pilares, args.limit)
    if not items:
        print("No hay items para revisar.", file=sys.stderr)
        return 1
    if args.fake:
        client: Any = _ClienteFalso()
    else:
        client = JevLlama(model_path=args.model)
    accuracy = jp.accuracy_por_tipo(
        Path(os.getenv("JEV_CALIBRATION_REPORT", str(jp.DEFAULT_CALIBRATION_REPORT)))
    )
    filas: list[dict[str, Any]] = []
    if args.report or not sys.stdout.isatty():
        print(f"{'item':<14}{'pilar':<14}{'campo':<13}{'propuesta':<18}{'conf':>6}")
        for item in items:
            nuevas = filas_de_item(item, client, accuracy)
            filas.extend(nuevas)
            for f in nuevas:
                print(
                    f"{f['item']:<14}{f['pilar']:<14}{f['campo']:<13}"
                    f"{str(f['propuesta']):<18}{f['confianza']:>6.2f}   {f['estado']}"
                )
            sys.stdout.flush()
    else:
        filas = repl_curses(items, client, accuracy)

    out = Path(args.out or os.getenv("JEV_REVIEW_REPORT", str(DEFAULT_REPORT)))
    guardar_revision(filas, out)
    print(f"\nRevision guardada en {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
