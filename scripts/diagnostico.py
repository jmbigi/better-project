#!/usr/bin/env python3
"""diagnostico.py — Diagnostico de los cuatro pilares en proyectos externos (REQ-017).

# REQ-017

Evalua un proyecto (`--root <carpeta>`) sobre los cuatro pilares y la higiene
general, con puntuacion por pilar y sugerencias accionables. Es de SOLO LECTURA:
nunca escribe en el proyecto evaluado (P0.3/P1.17).

Uso:
    python3 scripts/diagnostico.py --root <carpeta>
    python3 scripts/diagnostico.py --root <carpeta> --json
    python3 scripts/diagnostico.py --root <carpeta> --min-score 60   # exit 1 si <
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import adr_validator as av
import doc_validator as dv
import lessons_extractor as le

NIVELES = ((80, "solido"), (55, "parcial"), (25, "inicial"), (0, "ausente"))
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _nivel(score: int) -> str:
    for umbral, nombre in NIVELES:
        if score >= umbral:
            return nombre
    return "ausente"


def _pilar(nombre: str, score: int, hallazgos: list[str], sugerencias: list[str]) -> dict[str, Any]:
    return {
        "pilar": nombre,
        "score": max(0, min(100, score)),
        "nivel": _nivel(max(0, min(100, score))),
        "hallazgos": hallazgos,
        "sugerencias": sugerencias,
    }


def _evaluar_requisitos(root: Path) -> dict[str, Any]:
    req_dir = root / ".docs" / "requirements"
    reqs = sorted(req_dir.glob("REQ-*.md"))
    if not reqs:
        return _pilar(
            "requisitos", 0,
            ["no existe .docs/requirements/REQ-*.md"],
            ["crear requisitos con frontmatter (id, titulo, estado, prioridad, version, fecha_creacion) en .docs/requirements/"],
        )
    old_root, old_req = dv.ROOT, dv.REQ_DIR
    dv.ROOT, dv.REQ_DIR = root, req_dir
    try:
        reqs_meta = dv.collect_req_files()
        refs = dv.collect_code_refs()
        dv.analizar(reqs_meta, refs)
        errores, avisos = list(dv.errors), list(dv.warnings)
    finally:
        dv.ROOT, dv.REQ_DIR = old_root, old_req
    estados: dict[str, int] = {}
    for info in reqs_meta.values():
        estados[info["meta"].get("estado", "?")] = estados.get(info["meta"].get("estado", "?"), 0) + 1
    score = 100 - 15 * len(errores) - 5 * len(avisos)
    sugerencias = []
    if errores or avisos:
        sugerencias.append("adoptar scripts/doc_validator.py en el hook pre-commit para la trazabilidad REQ")
    return _pilar(
        "requisitos", score,
        [f"{len(reqs_meta)} REQ ({estados})", f"{sum(len(v) for v in refs.values())} referencias REQ en codigo",
         f"{len(errores)} errores, {len(avisos)} avisos"] + errores[:5] + avisos[:5],
        sugerencias,
    )


def _evaluar_conocimiento(root: Path) -> dict[str, Any]:
    kdir = root / ".docs" / "knowledge"
    archivos = sorted(kdir.rglob("*.md")) if kdir.exists() else []
    indice = (root / ".docs" / ".storage" / "index.json").exists()
    secciones = 0
    for path in archivos:
        secciones += len(re.findall(r"^##\s+", path.read_text(encoding="utf-8", errors="ignore"), re.M))
    if not archivos:
        sugerencias = ["crear .docs/knowledge/ con Markdown estructurado (una idea por seccion H2)"]
    elif not indice:
        sugerencias = ["indexar el conocimiento (en better-project: scripts/index_knowledge.py)"]
    else:
        sugerencias = []
    score = 100 if (archivos and indice) else (60 if archivos else 0)
    return _pilar(
        "conocimiento", score,
        [f"{len(archivos)} documentos, {secciones} secciones H2", f"indice: {'presente' if indice else 'ausente'}"],
        sugerencias,
    )


def _evaluar_lecciones(root: Path) -> dict[str, Any]:
    ldir = root / ".docs" / "lessons"
    yamls = sorted(ldir.glob("*.yaml")) if ldir.exists() else []
    if not yamls:
        return _pilar(
            "lecciones", 0,
            ["no existe .docs/lessons/*.yaml"],
            ["registrar lecciones con campos (id, proyecto, fase, categoria, problema, recomendacion, estado, fecha)"],
        )
    total, problemas, abiertas = 0, [], 0
    for path in yamls:
        for lesson in le._parse_yaml(path.read_text(encoding="utf-8")):
            if not isinstance(lesson, dict):
                problemas.append(f"{path.name}: entrada no valida")
                continue
            total += 1
            faltan = le.REQUIRED_FIELDS - set(lesson)
            if faltan:
                problemas.append(f"{lesson.get('id', '?')}: faltan {sorted(faltan)}")
            if lesson.get("estado") not in le.ALLOWED_STATES:
                problemas.append(f"{lesson.get('id', '?')}: estado invalido")
            if lesson.get("estado") == "Abierta":
                abiertas += 1
    score = 100 - 12 * len(problemas)
    sugerencias = []
    if problemas:
        sugerencias.append("validar las lecciones con scripts/lessons_extractor.py --check")
    if abiertas:
        sugerencias.append(f"cerrar {abiertas} lecciones abiertas")
    return _pilar(
        "lecciones", score,
        [f"{total} lecciones en {len(yamls)} archivo(s)", f"{len(problemas)} problemas", f"{abiertas} abiertas"],
        sugerencias,
    )


def _evaluar_pilar4(root: Path) -> dict[str, Any]:
    adr_dir = root / "docs" / "decisions"
    adrs = sorted(adr_dir.glob("ADR-*.md")) if adr_dir.exists() else []
    sesgos = (root / "docs" / "SESGOS-Y-FALACIAS.md").exists()
    agents = (root / "AGENTS.md").exists()
    errores, avisos = av.validate(adr_dir) if adr_dir.exists() else ([], [])
    score = 20 * (1 if agents else 0) + 30 * (1 if sesgos else 0) + 50 * (1 if adrs else 0)
    score -= 15 * len(errores)
    sugerencias = []
    if not adrs:
        sugerencias.append("registrar decisiones de arquitectura en docs/decisions/ (plantilla + scripts/adr_validator.py)")
    if not sesgos:
        sugerencias.append("adoptar docs/SESGOS-Y-FALACIAS.md (Pilar 4: control de sesgos y falacias)")
    if not agents:
        sugerencias.append("adoptar AGENTS.md con reglas P0/P1 (evita los 50 errores de LLM)")
    return _pilar(
        "pilar4", score,
        [f"{len(adrs)} ADR, {len(errores)} errores, {len(avisos)} alertas de sesgo",
         f"SESGOS-Y-FALACIAS: {'si' if sesgos else 'no'}", f"AGENTS.md: {'si' if agents else 'no'}"],
        sugerencias,
    )


def _evaluar_higiene(root: Path) -> dict[str, Any]:
    scripts_dir = root / "scripts"
    verificacion = (scripts_dir / "verificar-proyecto.sh").exists() or (
        scripts_dir.is_dir() and any(scripts_dir.glob("*verific*"))
    )
    checks = {
        "README.md": (root / "README.md").exists(),
        "tests/": (root / "tests").is_dir(),
        "verificacion": verificacion,
        "manifiesto de dependencias": any(
            (root / f).exists()
            for f in (
                "requirements.txt", "requirements-optional.txt", "requirements-dev.txt",
                "package.json", "Cargo.toml", "go.mod", "pyproject.toml",
            )
        ),
        "licencia": any((root / f).exists() for f in ("LICENSE", "LICENSE.md", "LICENSE.txt")),
    }
    presentes = sum(1 for v in checks.values() if v)
    score = round(100 * presentes / len(checks))
    faltan = [k for k, v in checks.items() if not v]
    sugerencias = [f"anadir {k}" for k in faltan]
    return _pilar(
        "higiene", score,
        [f"{presentes}/{len(checks)} presentes", "faltan: " + ", ".join(faltan) if faltan else "completo"],
        sugerencias,
    )


def evaluar(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"no existe el directorio {root}")
    pilares = [
        _evaluar_requisitos(root),
        _evaluar_conocimiento(root),
        _evaluar_lecciones(root),
        _evaluar_pilar4(root),
        _evaluar_higiene(root),
    ]
    global_score = round(sum(p["score"] for p in pilares) / len(pilares))
    sugerencias = [s for p in pilares for s in p["sugerencias"]]
    return {
        "root": str(root),
        "fecha": datetime.now().date().isoformat(),
        "puntuacion_global": global_score,
        "nivel_global": _nivel(global_score),
        "pilares": pilares,
        "sugerencias": sugerencias,
    }


def imprimir(reporte: dict[str, Any]) -> None:
    print(f"Diagnostico de {reporte['root']}  ({reporte['fecha']})")
    print(f"Puntuacion global: {reporte['puntuacion_global']}/100 ({reporte['nivel_global']})")
    print()
    for p in reporte["pilares"]:
        print(f"[{p['pilar']:<12}] {p['score']:>3}/100  {p['nivel']}")
        for h in p["hallazgos"]:
            print(f"    - {h}")
        for s in p["sugerencias"]:
            print(f"    > {s}")
    if reporte["sugerencias"]:
        print("\nSugerencias priorizadas:")
        for s in reporte["sugerencias"]:
            print(f"  * {s}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnostico de los cuatro pilares (REQ-017)")
    parser.add_argument("--root", default=".", help="Proyecto a evaluar")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--min-score", type=int, default=None,
                        help="Exit 1 si la puntuacion global es menor")
    args = parser.parse_args(argv)
    try:
        reporte = evaluar(Path(args.root))
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(reporte, indent=2, ensure_ascii=False))
    else:
        imprimir(reporte)
    if args.min_score is not None and reporte["puntuacion_global"] < args.min_score:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
