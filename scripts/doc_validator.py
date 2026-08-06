#!/usr/bin/env python3
"""doc_validator.py — Valida la trazabilidad REQ: código <-> .docs/requirements/ (REQ-001).

REQ-001: los requisitos se documentan en .docs/requirements/ con frontmatter YAML
y el código que los implementa lleva una referencia `REQ-XXX` (o `// IMPLEMENTS: REQ-XXX`).

Uso:
    python scripts/doc_validator.py            # errores -> exit 1
    python scripts/doc_validator.py --strict   # errores Y advertencias -> exit 1
    python scripts/doc_validator.py --root demo  # valida otro proyecto (demo/)

Sin dependencias externas (solo stdlib).
"""

import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOT_BASE = ROOT
REQ_DIR = ROOT / ".docs" / "requirements"
EXCLUDE = {
    ".git",
    "docs",
    ".docs/.storage",
    "node_modules",
    "__pycache__",
    "tests",
    "demo",
}
CODE_RE = re.compile(r"\b(?://\s*|#\s*|/\*\s*)?(?:IMPLEMENTS:\s*)?REQ-(\d{3})\b")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)
ALLOWED_STATES = {"Draft", "Aprobado", "Implementado", "Deprecado"}
REQUIRED_FIELDS = {"id", "titulo", "estado", "prioridad", "version", "fecha_creacion"}
CODE_EXTENSIONS = {".py", ".js", ".ts", ".php", ".go", ".rs", ".java", ".sh", ".css"}

errors: list[str] = []
warnings: list[str] = []


def collect_req_files() -> dict[str, dict]:
    """Lee .docs/requirements/REQ-XXX.md y devuelve {id: {frontmatter, ruta}}.

    Idempotente: reinicia las listas de errores/advertencias para que
    multiples invocaciones (TUI, MCP, tests) no acumulen resultados viejos.
    """
    errors.clear()
    warnings.clear()
    found: dict[str, dict] = {}
    for path in sorted(REQ_DIR.glob("REQ-*.md")):
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        if not match:
            errors.append(f"[ERROR] {path.relative_to(ROOT)}: sin frontmatter YAML")
            continue
        meta: dict = {}
        for line in match.group(1).strip().splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip().strip('"').strip("'")
        req_id = meta.get("id", "")
        if not re.fullmatch(r"REQ-\d{3}", req_id):
            errors.append(
                f"[ERROR] {path.relative_to(ROOT)}: frontmatter 'id' invalido o ausente"
            )
            continue
        if path.stem != req_id:
            errors.append(
                f"[ERROR] {path.relative_to(ROOT)}: id '{req_id}' no coincide con el nombre del archivo"
            )
        missing = REQUIRED_FIELDS - set(meta)
        if missing:
            errors.append(
                f"[ERROR] {path.relative_to(ROOT)}: faltan campos frontmatter: {sorted(missing)}"
            )
        if meta.get("estado") not in ALLOWED_STATES:
            errors.append(
                f"[ERROR] {path.relative_to(ROOT)}: estado '{meta.get('estado')}' no valido ({sorted(ALLOWED_STATES)})"
            )
        if meta.get("prioridad") not in {"Alta", "Media", "Baja"}:
            errors.append(
                f"[ERROR] {path.relative_to(ROOT)}: prioridad '{meta.get('prioridad')}' no valida (Alta/Media/Baja)"
            )
        if not re.fullmatch(r"\d+(\.\d+)*", meta.get("version", "")):
            errors.append(
                f"[ERROR] {path.relative_to(ROOT)}: version '{meta.get('version')}' no valida (p.ej. 1.0)"
            )
        fecha = meta.get("fecha_creacion", "")
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
                raise ValueError
            datetime.strptime(fecha, "%Y-%m-%d")
        except ValueError:
            errors.append(
                f"[ERROR] {path.relative_to(ROOT)}: fecha_creacion '{fecha}' no valida (AAAA-MM-DD)"
            )
        found[req_id] = {"meta": meta, "path": path}
    return found


def collect_code_refs() -> dict[str, list[str]]:
    """Escanea el código fuente buscando referencias REQ-XXX."""
    refs: dict[str, list[str]] = {}
    for path in ROOT.rglob("*"):
        if path.is_dir() or path.suffix not in CODE_EXTENSIONS:
            continue
        if any(part in EXCLUDE for part in path.parts):
            continue
        if any(part.startswith(".") for part in path.parts[1:]):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in CODE_RE.finditer(text):
            refs.setdefault(f"REQ-{match.group(1)}", []).append(
                f"{path.relative_to(ROOT)}"
            )
    return refs


def analizar(reqs: dict, refs: dict) -> None:
    """Rellena errors/warnings a partir de requisitos y referencias de codigo."""
    for req_id, locations in sorted(refs.items()):
        if req_id not in reqs:
            errors.append(
                f"[ERROR] REQ-{req_id[4:]} referenciado en {locations} pero no existe archivo en .docs/requirements/"
            )
            continue
        estado = reqs[req_id]["meta"].get("estado")
        if estado == "Deprecado":
            errors.append(
                f"[ERROR] {req_id} está Deprecado pero se referencia en código: {locations}"
            )
        elif estado in ("Draft", "Aprobado"):
            warnings.append(
                f"[WARN] {req_id} ({estado}) referenciado en código sin estado Implementado: {locations}"
            )

    for req_id, entry in sorted(reqs.items()):
        meta = entry["meta"]
        estado = meta.get("estado")
        if estado == "Implementado" and req_id not in refs:
            warnings.append(
                f"[WARN] {req_id} marcado Implementado pero no tiene referencias en código"
            )
        if estado == "Aprobado" and req_id not in refs:
            warnings.append(
                f"[WARN] {req_id} marcado Aprobado pero no tiene ninguna referencia en código"
            )


def main() -> int:
    global ROOT, REQ_DIR
    args = [a for a in sys.argv if a != "--strict"]
    if "--root" in args:
        idx = args.index("--root")
        if idx + 1 >= len(args):
            print("doc_validator: --root requiere una ruta (p.ej. demo)")
            return 1
        ROOT = ROOT_BASE / args[idx + 1]
        REQ_DIR = ROOT / ".docs" / "requirements"
        EXCLUDE.discard("demo")
    reqs = collect_req_files()
    refs = collect_code_refs()
    analizar(reqs, refs)
    strict = "--strict" in sys.argv

    summary = f"{len(reqs)} REQs, {len(refs)} referencias en código"
    print(f"doc_validator: {summary}")
    for line in errors + warnings:
        print(line)

    if errors:
        print(f"Resultado: {len(errors)} ERRORES, {len(warnings)} ADVERTENCIAS")
        return 1
    if strict and warnings:
        print(f"Resultado (--strict): {len(warnings)} ADVERTENCIAS")
        return 1
    print("Resultado: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
