#!/usr/bin/env python3
"""portable_verifier.py — Verificador portable para proyectos adoptados (REQ-028).

A diferencia de verificar-proyecto.sh (especifico de better-project), solo
comprueba lo generico del framework: trazabilidad REQ, validez de lecciones,
indice de conocimiento (si hay documentos) e higiene. Sin dependencias
externas (stdlib).

Uso (en el proyecto adoptado):
    python3 scripts/tools/portable_verifier.py [--lite] [--pre-commit] [--strict] [--json]

Los modulos que reutiliza (doc_validator, lessons_extractor, index_knowledge)
se copian junto a este archivo en scripts/; el tooling queda excluido del
escaneo de trazabilidad con la lista IGNORED_PATHS (doc_validator --ignore).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
TIMEOUT_SECONDS = 300
IGNORED_PATHS = (
    "scripts/hooks",
    "scripts/doc_validator.py",
    "scripts/lessons_extractor.py",
    "scripts/index_knowledge.py",
    "scripts/portable_verifier.py",
)


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"no se pudo ejecutar {cmd[1]}: {exc}"
    salida = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, salida.strip()


def _tools(name: str) -> str:
    return str(TOOLS_DIR / name)


def check_traceability(root: Path, strict: bool) -> dict:
    cmd = [sys.executable, _tools("doc_validator.py"), "--root", str(root)]
    for item in IGNORED_PATHS:
        cmd += ["--ignore", item]
    if strict:
        cmd.append("--strict")
    code, salida = _run(cmd, root)
    return {"check": "trazabilidad REQ", "estado": "OK" if code == 0 else "FALLO", "detalle": salida}


def check_lessons(root: Path) -> dict:
    code, salida = _run([sys.executable, _tools("lessons_extractor.py"), "--check"], root)
    return {"check": "lecciones", "estado": "OK" if code == 0 else "FALLO", "detalle": salida}


def check_knowledge(root: Path, lite: bool) -> dict:
    docs = sorted((root / ".docs" / "knowledge").rglob("*.md"))
    if not docs:
        return {
            "check": "indice de conocimiento",
            "estado": "SKIP",
            "detalle": "sin documentos en .docs/knowledge/",
        }
    if lite:
        return {"check": "indice de conocimiento", "estado": "SKIP", "detalle": "--lite"}
    code, salida = _run([sys.executable, _tools("index_knowledge.py")], root)
    if code != 0:
        return {"check": "indice de conocimiento", "estado": "FALLO", "detalle": salida}
    code, salida = _run([sys.executable, _tools("index_knowledge.py"), "--check"], root)
    return {
        "check": "indice de conocimiento",
        "estado": "OK" if code == 0 else "FALLO",
        "detalle": salida,
    }


def check_hygiene(root: Path) -> list[dict]:
    resultados = []
    readme = root / "README.md"
    resultados.append(
        {
            "check": "README.md presente",
            "estado": "OK" if readme.exists() else "WARN",
            "detalle": "" if readme.exists() else "falta README.md en la raiz",
        }
    )
    reqs = sorted((root / ".docs" / "requirements").glob("REQ-*.md"))
    resultados.append(
        {
            "check": "requisitos en .docs/requirements/",
            "estado": "OK" if reqs else "FALLO",
            "detalle": f"{len(reqs)} REQ" if reqs else "no hay REQ-*.md; ejecuta init.sh o anade requisitos",
        }
    )
    hook_repo = root / "scripts" / "hooks" / "pre-commit"
    hook_git = root / ".git" / "hooks" / "pre-commit"
    if hook_repo.exists() and hook_git.exists():
        iguales = hook_repo.read_bytes() == hook_git.read_bytes()
        resultados.append(
            {
                "check": "hooks sincronizados",
                "estado": "OK" if iguales else "WARN",
                "detalle": "" if iguales else "scripts/hooks/pre-commit difiere de .git/hooks/pre-commit",
            }
        )
    return resultados


def check_pre_commit(root: Path) -> dict | None:
    if not (root / ".git").is_dir():
        return None
    code, salida = _run(["git", "status", "--porcelain"], root)
    if code != 0:
        return None
    sin_stage = [line for line in salida.splitlines() if len(line) > 1 and line[0] == " " and line[1] != " "]
    return {
        "check": "sin cambios sin stagear (pre-commit)",
        "estado": "FALLO" if sin_stage else "OK",
        "detalle": "; ".join(sin_stage[:5]),
    }


def verificar(root: Path, lite: bool = False, pre_commit: bool = False, strict: bool = False) -> list[dict]:
    resultados = [check_traceability(root, strict), check_lessons(root), check_knowledge(root, lite)]
    resultados.extend(check_hygiene(root))
    if pre_commit:
        extra = check_pre_commit(root)
        if extra is not None:
            resultados.append(extra)
    return resultados


def render(resultados: list[dict]) -> str:
    lineas = ["== Verificacion portable (REQ-028) =="]
    for resultado in resultados:
        detalle = f" ({resultado['detalle']})" if resultado.get("detalle") else ""
        lineas.append(f"  [{resultado['estado']}] {resultado['check']}{detalle}")
    ok = sum(1 for r in resultados if r["estado"] == "OK")
    fallos = sum(1 for r in resultados if r["estado"] == "FALLO")
    saltos = sum(1 for r in resultados if r["estado"] == "SKIP")
    lineas.append(f"Resultado portable: {ok} OK, {fallos} FALLOS, {saltos} SKIP")
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verificador portable (REQ-028)")
    parser.add_argument("--root", default=".", help="raiz del proyecto a verificar")
    parser.add_argument("--lite", action="store_true", help="omite el indice de conocimiento")
    parser.add_argument("--pre-commit", action="store_true", help="exige sin cambios sin stagear")
    parser.add_argument("--strict", action="store_true", help="doc_validator: advertencias -> fallo")
    parser.add_argument("--json", action="store_true", help="salida JSON")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    resultados = verificar(root, lite=args.lite, pre_commit=args.pre_commit, strict=args.strict)
    if args.json:
        print(json.dumps(resultados, ensure_ascii=False, indent=2))
    else:
        print(render(resultados))
    return 1 if any(r["estado"] == "FALLO" for r in resultados) else 0


if __name__ == "__main__":
    raise SystemExit(main())
