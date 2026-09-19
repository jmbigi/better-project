#!/usr/bin/env python3
"""jev_calibration_merge.py — Fusiona candidatos aprobados en el set (REQ-018).

# REQ-018

Fusiona de forma idempotente un fichero de candidatos de calibracion APROBADOS
por el programador dentro del set validado (REQ-011). Por defecto es dry-run
(no escribe); con --aplicar modifica el set.

Uso:
    python3 scripts/jev_calibration_merge.py                 # dry-run
    python3 scripts/jev_calibration_merge.py --aplicar
    python3 scripts/jev_calibration_merge.py --candidatos F --set S --aplicar
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SET = ROOT / ".docs" / "knowledge" / "ai" / "jev_calibration_set.json"
DEFAULT_CANDIDATOS = ROOT / ".docs" / "knowledge" / "ai" / "jev_calibration_candidates.json"
ESTADOS_APROBADOS = {"aprobado", "aprobado_por_programador"}
TIPOS = {"noul", "choice", "score"}


def _leer(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def validar_caso(caso: dict[str, Any]) -> list[str]:
    """Valida el esquema minimo de un caso de calibracion."""
    problemas: list[str] = []
    if not str(caso.get("id", "")).strip():
        problemas.append("sin id")
    tipo = caso.get("tipo")
    if tipo not in TIPOS:
        problemas.append(f"tipo invalido: {tipo!r}")
    for campo in ("estado", "instrucciones", "esperado"):
        if campo not in caso:
            problemas.append(f"falta '{campo}'")
    esperado = str(caso.get("esperado"))
    if tipo == "noul" and esperado not in {"yes", "no"}:
        problemas.append(f"esperado invalido para noul: {esperado!r}")
    elif tipo == "choice":
        criterios = caso.get("criterios")
        if not isinstance(criterios, dict) or not criterios:
            problemas.append("choice sin 'criterios'")
        elif esperado not in criterios:
            problemas.append(f"esperado '{esperado}' no esta en criterios")
    elif tipo == "score":
        niveles = caso.get("niveles")
        if not isinstance(niveles, list) or not niveles:
            problemas.append("score sin 'niveles'")
        elif esperado not in [str(i) for i in range(len(niveles))]:
            problemas.append(f"esperado '{esperado}' fuera de niveles")
    return problemas


def fusionar(
    set_data: dict[str, Any], cand_data: dict[str, Any], forzar: bool = False, aplicar: bool = False
) -> dict[str, Any]:
    """Valida y (si aplicar) fusiona. Devuelve {nuevos, errores}."""
    errores: list[str] = []
    if not forzar and cand_data.get("estado") not in ESTADOS_APROBADOS:
        errores.append(
            f"los candidatos no estan aprobados (estado='{cand_data.get('estado')}'); "
            f"revisar con jev_review --calibracion o usar --forzar"
        )
    ids_set = {str(c.get("id")) for c in set_data.get("casos", [])}
    vistos: set[str] = set()
    nuevos: list[dict[str, Any]] = []
    for caso in cand_data.get("casos", []):
        cid = str(caso.get("id"))
        problemas = validar_caso(caso)
        if problemas:
            errores.append(f"{cid}: " + "; ".join(problemas))
            continue
        if cid in ids_set:
            errores.append(f"id duplicado en el set: {cid}")
        elif cid in vistos:
            errores.append(f"id duplicado en candidatos: {cid}")
        else:
            vistos.add(cid)
            nuevos.append(caso)
    if errores or not aplicar:
        return {"nuevos": nuevos, "errores": errores}
    set_data.setdefault("casos", []).extend(nuevos)
    set_data["version"] = int(set_data.get("version", 1)) + 1
    revision = set_data.setdefault("revision_humana", {})
    revision["fecha_ultima_fusion"] = date.today().isoformat()
    revision.setdefault("lotes_fusionados", []).append(
        {"fecha": date.today().isoformat(), "casos": [str(c.get("id")) for c in nuevos]}
    )
    set_data["descripcion"] = (
        str(set_data.get("descripcion", "")).rstrip()
        + f" Fusion (REQ-018, {date.today().isoformat()}): +{len(nuevos)} casos aprobados."
    )
    return {"nuevos": nuevos, "errores": errores}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fusiona candidatos aprobados (REQ-018)")
    parser.add_argument("--set", default=str(DEFAULT_SET))
    parser.add_argument("--candidatos", default=str(DEFAULT_CANDIDATOS))
    parser.add_argument("--aplicar", action="store_true", help="Escribe el set fusionado")
    parser.add_argument("--forzar", action="store_true", help="Fusionar aunque no este aprobado")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    set_path, cand_path = Path(args.set), Path(args.candidatos)
    for path in (set_path, cand_path):
        if not path.exists():
            print(f"Error: no existe {path}", file=sys.stderr)
            return 1
    set_data, cand_data = _leer(set_path), _leer(cand_path)
    resultado = fusionar(set_data, cand_data, forzar=args.forzar, aplicar=args.aplicar)

    if args.json:
        print(json.dumps({"nuevos": [c.get("id") for c in resultado["nuevos"]],
                          "errores": resultado["errores"]}, indent=2, ensure_ascii=False))
    else:
        for e in resultado["errores"]:
            print(f"[ERROR] {e}")
        print(f"Candidatos: {len(cand_data.get('casos', []))}  nuevos a fusionar: {len(resultado['nuevos'])}")
        for c in resultado["nuevos"]:
            print(f"  + {c.get('id')} ({c.get('tipo')})")
        print("Modo: " + ("APLICAR (escrito)" if args.aplicar and not resultado["errores"] else "dry-run"))
    if resultado["errores"]:
        return 1
    if args.aplicar:
        set_path.write_text(json.dumps(set_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
