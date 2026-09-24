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

En Windows sin `windows-curses` instalado, la UI curses no esta disponible
y el script cae automaticamente a modo `--report` con una advertencia.

Teclas en la UI: y=OK  n=corregir (1..K elige opcion)  s=saltar  q=salir.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

try:
    import curses
    HAS_CURSES = True
except ImportError:
    HAS_CURSES = False

import jev_pillars as jp
import lessons_extractor as le
from jev_llama import JevLlama


def _curses_works() -> bool:
    """Verifica si curses funciona realmente (no solo importable).
    En Windows sin windows-curses, curses se importa pero falla al inicializar.
    """
    if not HAS_CURSES:
        return False
    try:
        # Test rápido: curses.wrapper con función vacía
        def _test(stdscr):
            pass
        curses.wrapper(_test)
        return True
    except Exception:
        return False


CURSES_AVAILABLE = _curses_works()

ROOT = Path(__file__).resolve().parent.parent
REQ_DIR = ROOT / ".docs" / "requirements"
LESSONS_DIR = ROOT / ".docs" / "lessons"
DEFAULT_REPORT = ROOT / ".docs" / ".storage" / "jev_review.json"
DEFAULT_CACHE = ROOT / ".docs" / ".storage" / "jev_review_cache.json"
CANDIDATES = ROOT / ".docs" / "knowledge" / "ai" / "jev_calibration_candidates.json"
UMBRAL = 0.5


def _opciones_caso(caso: dict[str, Any]) -> list[str]:
    tipo = caso["tipo"]
    if tipo == "noul":
        return ["yes", "no"]
    if tipo == "choice":
        return list(caso["criterios"].keys())
    return [str(i) for i in range(len(caso["niveles"]))]


def _items_calibracion(path: Path = CANDIDATES, limit: int | None = None) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = [
        {"pilar": "calibracion", "id": caso["id"], "texto": caso["estado"], "caso": caso}
        for caso in data.get("casos", [])
    ]
    return items[:limit] if limit else items


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


def construir_items(
    pilares: list[str], limit: int | None = None, calibracion: bool = False
) -> list[dict[str, Any]]:
    """Devuelve items de revision segun los pilares pedidos (o candidatos)."""
    if calibracion:
        return _items_calibracion(limit=limit)
    items: list[dict[str, Any]] = []
    if "requisitos" in pilares:
        for path in sorted(REQ_DIR.glob("REQ-*.md")):
            items.append(
                {"pilar": "requisitos", "id": path.stem,
                 "texto": _cuerpo_sin_frontmatter(path.read_text(encoding="utf-8"))}
            )
    if "lecciones" in pilares:
        lessons, _ = le.validate()
        for lesson in sorted(lessons, key=lambda item: str(item.get("id", ""))):
            texto = f"Problema: {lesson.get('problema', '')}\nRecomendacion: {lesson.get('recomendacion', '')}"
            items.append({"pilar": "lecciones", "id": str(lesson.get("id")), "texto": texto})
    if "conocimiento" in pilares:
        for path in sorted((ROOT / ".docs" / "knowledge").rglob("*.md")):
            items.append(
                {"pilar": "conocimiento", "id": path.name,
                 "texto": path.read_text(encoding="utf-8")}
            )
    return items[:limit] if limit else items


def _clave(item: dict[str, Any]) -> str:
    digest = hashlib.sha1(item["texto"].encode("utf-8")).hexdigest()[:12]
    return f"{item['pilar']}|{item['id']}|{digest}"


def _ruta_cache(path: str | None = None) -> Path:
    return Path(path or os.getenv("JEV_REVIEW_CACHE", str(DEFAULT_CACHE)))


def cargar_cache(path: str | None = None) -> dict[str, Any]:
    ruta = _ruta_cache(path)
    if ruta.exists():
        try:
            return json.loads(ruta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def guardar_cache(cache: dict[str, Any], path: str | None = None) -> None:
    ruta = _ruta_cache(path)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def filas_de_item(
    item: dict[str, Any], client: Any, accuracy: dict[str, float], cache: dict | None = None
) -> list[dict[str, Any]]:
    """Clasifica UN item (o reutiliza la cache) y devuelve sus filas."""
    if "caso" in item:
        caso = item["caso"]
        return [
            {
                "item": caso["id"],
                "pilar": "calibracion",
                "campo": caso["tipo"],
                "tipo": caso["tipo"],
                "opciones": _opciones_caso(caso),
                "propuesta": str(caso["esperado"]),
                "confianza": None,
                "revision_humana": False,
                "estado": "pendiente",
                "decision_final": None,
            }
        ]
    clave = _clave(item)
    if cache is not None and clave in cache:
        decisiones = cache[clave]
    else:
        decisiones = jp.ejecutar(item["pilar"], item["id"], item["texto"], client, UMBRAL, accuracy)["decisiones"]
        if cache is not None:
            cache[clave] = decisiones
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
        for decision in decisiones
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


def _conf_txt(conf: float | None) -> str:
    return "   n/a" if conf is None else f"{conf:>6.2f}"


def imprimir_tabla(filas: list[dict[str, Any]]) -> None:
    print(f"{'item':<14}{'pilar':<14}{'campo':<13}{'propuesta':<18}{'conf':>6}  estado")
    for f in filas:
        print(
            f"{f['item']:<14}{f['pilar']:<14}{f['campo']:<13}{str(f['propuesta']):<18}"
            f"{_conf_txt(f['confianza'])}  {f['estado']}"
        )


def _dibujar(stdscr, fila: dict[str, Any], cabecera: str, mensaje: str) -> None:
    stdscr.clear()
    alto, ancho = stdscr.getmaxyx()
    stdscr.addnstr(0, 0, f"REVISION JEV (REQ-016)  {cabecera}", ancho - 1, curses.A_BOLD)
    stdscr.addnstr(1, 0, f"{fila['item']}  [{fila['pilar']}/{fila['campo']}]  tipo={fila['tipo']}", ancho - 1)
    texto = f"Propuesta: {fila['propuesta']}   confianza={_conf_txt(fila['confianza']).strip()}"
    stdscr.addnstr(2, 0, texto, ancho - 1)
    stdscr.addnstr(4, 0, "Opciones:", ancho - 1)
    for i, op in enumerate(fila["opciones"], 1):
        stdscr.addnstr(5 + i, 2, f"{i}) {op}", ancho - 3)
    stdscr.addnstr(alto - 2, 0, mensaje, ancho - 1)
    stdscr.addnstr(alto - 1, 0, "y=OK  n=corregir (elige 1..K)  s=saltar  q=salir", ancho - 1)
    stdscr.refresh()


def repl_curses(
    items: list[dict[str, Any]], client: Any, accuracy: dict[str, float],
    cache: dict | None = None, out: Path | None = None,
) -> list[dict[str, Any]]:
    """UI incremental: clasifica cada item y pregunta su confirmacion al momento."""
    if not CURSES_AVAILABLE:
        raise RuntimeError("curses no disponible (Windows sin windows-curses o error de inicialización). Use --report.")
    import curses
    filas: list[dict[str, Any]] = []

    def _guardar():
        if cache is not None:
            guardar_cache(cache)
        if out is not None:
            guardar_revision(filas, out)

    def _run(stdscr):
        for n_item, item in enumerate(items, 1):
            nuevas = filas_de_item(item, client, accuracy, cache)
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
            _guardar()

    curses.wrapper(_run)
    return filas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Revision humana de clasificaciones Jev (REQ-016)")
    parser.add_argument("--pilar", action="append", choices=["requisitos", "lecciones", "conocimiento"],
                        help="Pilar a revisar (repetible; default: requisitos y lecciones)")
    parser.add_argument("--limit", type=int, default=None, help="Maximo de items")
    parser.add_argument("--report", action="store_true", help="Tabla por consola (sin UI)")
    parser.add_argument("--fake", action="store_true", help="Cliente simulado (sin modelo)")
    parser.add_argument("--calibracion", action="store_true",
                        help="Revisar etiquetas candidatas de calibracion (sin modelo)")
    parser.add_argument("--out", default=None, help="Ruta del JSON de revision")
    parser.add_argument("--model", default=None, help="Ruta al GGUF (modelo real)")
    args = parser.parse_args(argv)

    if args.calibracion:
        items = construir_items(["calibracion"], args.limit, calibracion=True)
        client: Any = None
        accuracy: dict[str, float] = {}
    else:
        pilares = args.pilar or ["requisitos", "lecciones"]
        items = construir_items(pilares, args.limit)
        if args.fake:
            client = _ClienteFalso()
        else:
            client = JevLlama(model_path=args.model)
        accuracy = jp.accuracy_por_tipo(
            Path(os.getenv("JEV_CALIBRATION_REPORT", str(jp.DEFAULT_CALIBRATION_REPORT)))
        )
    if not items:
        print("No hay items para revisar.", file=sys.stderr)
        return 1
    out = Path(args.out or os.getenv("JEV_REVIEW_REPORT", str(DEFAULT_REPORT)))
    cache = cargar_cache()
    filas: list[dict[str, Any]] = []
    if args.report or not sys.stdout.isatty() or not CURSES_AVAILABLE:
        if not CURSES_AVAILABLE and not args.report:
            print("[WARN] curses no disponible (Windows sin windows-curses o error de inicialización). Usando modo --report.", file=sys.stderr)
        print(f"{'item':<14}{'pilar':<14}{'campo':<13}{'propuesta':<18}{'conf':>6}")
        for item in items:
            nuevas = filas_de_item(item, client, accuracy, cache)
            filas.extend(nuevas)
            for f in nuevas:
                print(
                    f"{f['item']:<14}{f['pilar']:<14}{f['campo']:<13}"
                    f"{str(f['propuesta']):<18}{_conf_txt(f['confianza'])}   {f['estado']}"
                )
            sys.stdout.flush()
            guardar_cache(cache)
            guardar_revision(filas, out)  # progreso incremental (no se pierde por timeout)
    else:
        filas = repl_curses(items, client, accuracy, cache, out)

    guardar_cache(cache)
    guardar_revision(filas, out)
    print(f"\nRevision guardada en {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
