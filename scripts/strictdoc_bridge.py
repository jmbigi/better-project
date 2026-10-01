#!/usr/bin/env python3
r"""Puente StrictDoc ↔ trazabilidad de código (REQ-032; implementa SDOC-001/SDOC-002).

Valida los documentos `.sdoc` del proyecto SIN instalar strictdoc (stdlib):
estructura mínima (nodos `[TAG]`, campos, multilínea `>>> … <<<` cerrada),
UIDs únicos, campos obligatorios de `[REQUIREMENT]` (`UID` y `TITLE` o
`STATEMENT`) y trazabilidad: toda referencia `SDOC-XXX` en código existe como
`UID` en algún `.sdoc`. Los UIDs usan el esquema `SDOC-\d{3}` para no colisionar
con `CODE_RE` de `doc_validator.py` (`\bREQ-(\d{3})\b`, ADR-011).

La exportación HTML es capa opcional aparte (`requirements-strictdoc.txt`).

Uso: `python3 scripts/strictdoc_bridge.py [--root <proyecto>] [--json]`
Salida: 0 = válido (o sin .sdoc), 1 = errores de estructura/trazabilidad.
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

NODE_RE = re.compile(r"^\[([A-Z_]+)\]$")
COMPOSITE_RE = re.compile(r"^\[\[/?[A-Z_]+\]\]$")
FIELD_RE = re.compile(r"^([A-Z_]+):( |$)")
UID_VAL_RE = re.compile(r"^UID: (\S+)$")
CODE_RE = re.compile(r"\b(?://\s*|#\s*|/\*\s*)?SDOC-(\d{3})\b")
CODE_EXTS = {
    ".py", ".sh", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".c", ".h", ".cpp", ".go", ".rs",
}
# tests/ y demo/ se excluyen: los tests contienen referencias SDOC sintéticas
# y la demo se valida aparte con --root (mismo criterio que doc_validator).
EXCLUDE_DIRS = {".git", ".storage", "node_modules", "__pycache__", "tests", "demo", ".venv", "venv"}
CAMPOS_REQUERIDOS = ("TITLE", "STATEMENT")


class SDocError(Exception):
    """Error de estructura en un documento .sdoc."""


def parse_sdoc(path: Path) -> list[dict]:
    """Parser tolerante de campos mínimos (no depende de la gramática textX).

    Devuelve nodos {tipo, linea, uid, campos}. Lanza SDocError si una
    multilínea `>>>` queda sin cerrar con `<<<`.
    """
    nodos: list[dict] = []
    nodo: dict | None = None
    en_multilinea = False
    for num, linea in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if en_multilinea:
            if linea.strip() == "<<<":
                en_multilinea = False
            continue
        if COMPOSITE_RE.match(linea):
            continue
        m = NODE_RE.match(linea)
        if m:
            nodo = {"tipo": m.group(1), "linea": num, "uid": None, "campos": set()}
            nodos.append(nodo)
            continue
        if nodo is None:
            continue
        fm = FIELD_RE.match(linea)
        if fm:
            campo = fm.group(1)
            nodo["campos"].add(campo)
            if campo == "UID":
                um = UID_VAL_RE.match(linea)
                if um:
                    nodo["uid"] = um.group(1)
            if linea.rstrip().endswith(">>>"):
                en_multilinea = True
    if en_multilinea:
        raise SDocError(f"{path}: multilínea '>>>' sin cerrar con '<<<'")
    return nodos


def _referencias_codigo(root: Path) -> list[tuple[Path, str]]:
    """Referencias SDOC-XXX en archivos de código (sin tests/ ni demo/)."""
    refs: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in CODE_EXTS:
            continue
        if EXCLUDE_DIRS & set(path.relative_to(root).parts):
            continue
        for m in CODE_RE.finditer(path.read_text(encoding="utf-8", errors="replace")):
            refs.append((path, f"SDOC-{m.group(1)}"))
    return refs


def _sdoc_files(root: Path) -> list[Path]:
    base = root / ".docs" / "requirements"
    if base.is_dir():
        return sorted(base.rglob("*.sdoc"))
    return sorted(p for p in root.rglob("*.sdoc") if not EXCLUDE_DIRS & set(p.relative_to(root).parts))


def validar(root: Path) -> tuple[list[str], int, int]:
    """(errores, n_uids, n_referencias). Lista de errores vacía = válido."""
    errores: list[str] = []
    archivos = _sdoc_files(root)
    uids: dict[str, Path] = {}
    for path in archivos:
        try:
            nodos = parse_sdoc(path)
        except SDocError as e:
            errores.append(str(e))
            continue
        for nodo in nodos:
            if nodo["tipo"] != "REQUIREMENT":
                continue
            if not nodo["uid"]:
                errores.append(f"{path}:{nodo['linea']}: [REQUIREMENT] sin UID válido")
            if not any(c in nodo["campos"] for c in CAMPOS_REQUERIDOS):
                errores.append(
                    f"{path}:{nodo['linea']}: [REQUIREMENT] sin TITLE ni STATEMENT"
                )
            if nodo["uid"]:
                if nodo["uid"] in uids:
                    errores.append(f"{path}:{nodo['linea']}: UID duplicado {nodo['uid']} (también en {uids[nodo['uid']]})")
                else:
                    uids[nodo["uid"]] = path
    referencias = _referencias_codigo(root)
    for path, ref in referencias:
        if ref not in uids:
            errores.append(f"{path}: referencia {ref} sin UID en ningún .sdoc")
    return errores, len(uids), len(referencias)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=str(ROOT), help="proyecto a validar (defecto: este repo)")
    parser.add_argument("--json", action="store_true", help="salida máquina-legible")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    archivos = _sdoc_files(root)
    errores, n_uids, n_refs = validar(root)
    if args.json:
        print(json.dumps({
            "sdoc": len(archivos), "uids": n_uids, "referencias": n_refs,
            "errores": errores, "ok": not errores,
        }, ensure_ascii=False))
    elif not archivos:
        print(f"strictdoc_bridge: sin .sdoc en {root} (nada que validar)")
    else:
        for e in errores:
            print(f"[ERROR] {e}")
        print(f"strictdoc_bridge: {len(archivos)} .sdoc, {n_uids} UIDs, {n_refs} referencias en código")
        print(f"Resultado: {'OK' if not errores else f'{len(errores)} ERRORES'}")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
