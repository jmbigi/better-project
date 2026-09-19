#!/usr/bin/env python3
"""auto_audit.py — Auto-auditoria del proyecto (REQ-014).

# REQ-014

Auditorias heuristicas sobre el propio repositorio (sin dependencias):

    python3 scripts/auto_audit.py sesgos       # afirmaciones/sesgos en docs
    python3 scripts/auto_audit.py evidencias   # frescura del SBOM (P0.18)
    python3 scripts/auto_audit.py decisiones   # REQ/ADR/lecciones pendientes
    python3 scripts/auto_audit.py tests        # tests falsos y except: pass (P1.1/P1.26)
    python3 scripts/auto_audit.py ia           # trailer Assisted-by en commits (P1.14)
    python3 scripts/auto_audit.py vulns        # re-escaneo de dependencias (P0.18, usa red)
    python3 scripts/auto_audit.py all [--json] [--strict] [--max-dias N]

La auditoria asiste la revision humana, no la sustituye (P1.15).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
REQ_DIR = ROOT / ".docs" / "requirements"
ADR_DIR = ROOT / "docs" / "decisions"
SCRIPTS_DIR = ROOT / "scripts"
TEST_FILE = ROOT / "tests" / "test_ecosistema.py"

DOCS_SESGOS = (
    ROOT / "README.md",
    DOCS_DIR / "AGENT-ARCHITECTURE.md",
    DOCS_DIR / "ESTADO-JEV-LLAMA.md",
    DOCS_DIR / "REVISION-SET-CALIBRACION.md",
    DOCS_DIR / "SESGOS-Y-FALACIAS.md",
)
KNOWLEDGE_DIR = ROOT / ".docs" / "knowledge"
SESGOS_WHITELIST = {"docs/SESGOS-Y-FALACIAS.md"}
SESGOS_PATRONES = (
    (re.compile(r"garantiz\w+", re.I), "garantia absoluta (exceso de confianza)"),
    (re.compile(r"100\s*%"), "porcentaje absoluto sin matiz"),
    (re.compile(r"nunca falla", re.I), "garantia absoluta"),
    (re.compile(r"\bsin errores\b", re.I), "garantia absoluta"),
    (re.compile(r"\bobviamente\b", re.I), "realismo naif"),
    (re.compile(r"\bevidentemente\b", re.I), "realismo naif"),
    (re.compile(r"\btodo el mundo\b", re.I), "ad populum"),
    (re.compile(r"\blo usan todas?\b", re.I), "ad populum"),
    (re.compile(r"\bla mejor\b", re.I), "superlativo sin metrica"),
)
SBOM_RE = re.compile(r"SBOM-(\d{4}-\d{2}-\d{2})\.(?:spdx|cdx)\.json$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.S)
ASSERT_METODOS = ("assert", "fail")


def _linea_ignorada(line: str) -> bool:
    """Ignora reglas, listas/checklists, tablas y bloques de codigo."""
    s = line.strip()
    if not s or s.startswith(("```", "<!--", "|")):
        return True
    if re.search(r"\bP[0-2]\.\d+", line) or "REQ-" in line:
        return True
    return bool(re.match(r"^(\d+\.|[-*])\s", s))


def _frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    meta: dict[str, str] = {}
    for line in match.group(1).strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta


def auditar_sesgos(paths=None) -> list[str]:
    hallazgos: list[str] = []
    if paths is None:
        paths = list(DOCS_SESGOS) + sorted(KNOWLEDGE_DIR.rglob("*.md")) + sorted(
            (DOCS_DIR / "decisions").glob("ADR-*.md")
        )
    for path in paths:
        path = Path(path)
        if not path.exists():
            continue
        rel = path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name
        if rel in SESGOS_WHITELIST:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _linea_ignorada(line):
                continue
            for patron, motivo in SESGOS_PATRONES:
                if patron.search(line):
                    hallazgos.append(f"{rel}:{i}: {motivo} -> {line.strip()[:80]}")
    return hallazgos


def auditar_evidencias(docs_dir: Path = DOCS_DIR, max_dias: int = 90) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    sboms = sorted(Path(docs_dir).glob("SBOM-*.spdx.json")) + sorted(
        Path(docs_dir).glob("SBOM-*.cdx.json")
    )
    if not sboms:
        errors.append("no hay SBOM en docs/ (P0.18)")
    for sbom in sboms:
        match = SBOM_RE.search(sbom.name)
        if not match:
            warnings.append(f"{sbom.name}: no se pudo leer la fecha del SBOM")
            continue
        fecha = datetime.strptime(match.group(1), "%Y-%m-%d").date()
        edad = (date.today() - fecha).days
        if edad > max_dias:
            warnings.append(f"{sbom.name}: SBOM de {edad} dias (> {max_dias}); re-escanear (P0.18)")
    return errors, warnings


def _scanner_disponible():
    """Devuelve (nombre, constructor de comando) del primer escaner disponible."""
    if shutil.which("pip-audit"):
        return "pip-audit", lambda req: [
            "pip-audit", "-r", str(req), "-f", "json",
            "--progress-spinner", "off", "--timeout", "15",
        ]
    if shutil.which("osv-scanner"):
        return "osv-scanner", lambda req: ["osv-scanner", "--format", "json", "--lockfile", str(req)]
    return None, None


def _parse_pip_audit(payload: dict) -> list[dict]:
    hallazgos: list[dict] = []
    for dep in payload.get("dependencies", []):
        for vuln in dep.get("vulns", []) or []:
            hallazgos.append(
                {
                    "name": dep.get("name"),
                    "version": dep.get("version"),
                    "id": vuln.get("id"),
                    "fix_versions": vuln.get("fix_versions", []) or [],
                }
            )
    return hallazgos


def _runner_pip_audit(cmd: list[str]):
    def run() -> list[dict]:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        # pip-audit devuelve 1 cuando encuentra vulnerabilidades (no es un fallo).
        if proc.returncode not in (0, 1):
            raise RuntimeError(proc.stderr.strip()[:200] or f"exit {proc.returncode}")
        return _parse_pip_audit(json.loads(proc.stdout or "{}"))

    return run


def auditar_vulns(requirements=None, ejecutar=None) -> tuple[list[str], list[str]]:
    """Re-escanea vulnerabilidades (P0.18). Requiere pip-audit/osv-scanner.

    No silencia la ausencia de escaner: devuelve una alerta explicita (P1.19).
    Se ejecuta a demanda (usa red); no forma parte de `all` ni del pre-commit.
    """
    requirements = Path(requirements or (ROOT / "requirements-optional.txt"))
    if not requirements.exists():
        return [f"no existe el archivo de dependencias {requirements}"], []
    if ejecutar is None:
        nombre, builder = _scanner_disponible()
        if builder is None:
            return [], [
                "sin escaner de vulnerabilidades disponible (pip-audit/osv-scanner); "
                "adoptar bajo ADR y P0.18"
            ]
        ejecutar = _runner_pip_audit(builder(requirements))
    try:
        hallazgos = ejecutar()
    except (RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired, OSError) as exc:
        return [f"fallo el escaneo de vulnerabilidades: {exc}"], []
    warnings: list[str] = []
    vistos: set[tuple] = set()
    for h in hallazgos:
        clave = (h.get("name"), h.get("version"), h.get("id"))
        if clave in vistos:
            continue
        vistos.add(clave)
        fix = ",".join(h.get("fix_versions", [])) or "sin parche"
        warnings.append(f"{h.get('name')} {h.get('version')}: {h.get('id')} (fix: {fix})")
    return [], warnings


def auditar_decisiones(
    req_dir: Path = REQ_DIR, adr_dir: Path = ADR_DIR, max_dias: int = 180
) -> list[str]:
    warnings: list[str] = []
    for path in sorted(Path(req_dir).glob("REQ-*.md")):
        estado = _frontmatter(path.read_text(encoding="utf-8")).get("estado", "")
        if estado in {"Draft", "Aprobado"}:
            warnings.append(f"{path.name}: REQ en estado {estado} (implementar o deprecar)")
    for path in sorted(Path(adr_dir).glob("ADR-*.md")):
        meta = _frontmatter(path.read_text(encoding="utf-8"))
        if meta.get("estado") == "Propuesto":
            warnings.append(f"{path.name}: ADR Propuesto sin resolver")
    try:
        import lessons_extractor as le

        lessons, _ = le.validate()
        for lesson in lessons:
            if lesson.get("estado") == "Abierta":
                warnings.append(f"{lesson.get('id')}: leccion Abierta (revisar y cerrar)")
    except Exception as exc:  # noqa: BLE001 - reportar y seguir
        warnings.append(f"no se pudieron validar las lecciones: {exc}")
    try:
        import index_knowledge as ik

        if not ik.check_fresh():
            warnings.append("indice de conocimiento desactualizado (ejecutar index_knowledge.py)")
    except Exception as exc:  # noqa: BLE001 - reportar y seguir
        warnings.append(f"no se pudo comprobar el indice de conocimiento: {exc}")
    return warnings


def _es_asercion(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and any(
            func.attr.startswith(p) for p in ASSERT_METODOS
        ):
            return True
        if isinstance(func, ast.Name) and any(func.id.startswith(p) for p in ASSERT_METODOS):
            return True
    return False


def _tautologia(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return None
    attr = node.func.attr
    args = node.args
    if attr in {"assertTrue", "assertIs"} and args and isinstance(args[0], ast.Constant):
        if args[0].value in {True, 1} or args[0].value is None:
            return f"{attr}({args[0].value!r})"
    if attr == "assertEqual" and len(args) >= 2 and ast.dump(args[0]) == ast.dump(args[1]):
        return "assertEqual(x, x)"
    return None


def auditar_tests(test_file: Path = TEST_FILE, scripts_dir: Path = SCRIPTS_DIR) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    tree = ast.parse(Path(test_file).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        aserciones = [n for n in ast.walk(node) if _es_asercion(n)]
        if not aserciones:
            warnings.append(f"{node.name}: test sin asercion (P1.1)")
        for n in aserciones:
            taut = _tautologia(n)
            if taut:
                errors.append(f"{node.name}: asercion tautologica {taut} (P1.1)")
    for script in sorted(Path(scripts_dir).glob("*.py")):
        stree = ast.parse(script.read_text(encoding="utf-8"))
        for handler in [n for n in ast.walk(stree) if isinstance(n, ast.ExceptHandler)]:
            if all(isinstance(b, ast.Pass) for b in handler.body):
                errors.append(f"{script.name}:{handler.lineno}: except con 'pass' (P1.26)")
    return errors, warnings


def _tiene_trailer(mensaje: str) -> bool:
    bajo = mensaje.lower()
    return "assisted-by:" in bajo or "generated-by:" in bajo


def auditar_ia(n: int = 50) -> tuple[list[str], list[str]]:
    try:
        proc = subprocess.run(
            ["git", "log", f"-n{n}", "--pretty=format:%H%x1f%s%x1f%b%x1e", "--",
             "docs", "scripts", ".docs", "AGENTS.md", "README.md"],
            cwd=ROOT, capture_output=True, text=True,
        )
    except OSError as exc:
        return [f"no se pudo ejecutar git: {exc}"], []
    if proc.returncode != 0:
        return [f"git log fallo: {proc.stderr.strip()}"], []
    sin_trailer: list[str] = []
    total = 0
    for record in proc.stdout.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        total += 1
        partes = record.split("\x1f")
        if len(partes) < 3:
            continue
        sha, asunto, cuerpo = partes[0], partes[1], partes[2]
        if not _tiene_trailer(f"{asunto}\n{cuerpo}"):
            sin_trailer.append(f"{sha[:8]} {asunto[:70]}")
    return sin_trailer, [f"commits revisados (ultimos {n}): {total}"]


def _ejecutar(args: argparse.Namespace) -> dict[str, Any]:
    resultado: dict[str, Any] = {"errores": [], "alertas": [], "info": []}
    if args.subcomando in {"sesgos", "all"}:
        resultado["alertas"].extend(auditar_sesgos())
    if args.subcomando in {"evidencias", "all"}:
        err, warn = auditar_evidencias(max_dias=args.max_dias)
        resultado["errores"].extend(err)
        resultado["alertas"].extend(warn)
    if args.subcomando in {"decisiones", "all"}:
        resultado["alertas"].extend(auditar_decisiones())
    if args.subcomando in {"tests", "all"}:
        err, warn = auditar_tests()
        resultado["errores"].extend(err)
        resultado["alertas"].extend(warn)
    if args.subcomando in {"ia", "all"}:
        warn, info = auditar_ia()
        resultado["alertas"].extend(warn)
        resultado["info"].extend(info)
    if args.subcomando == "vulns":
        err, warn = auditar_vulns()
        resultado["errores"].extend(err)
        resultado["alertas"].extend(warn)
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Auto-auditoria del proyecto (REQ-014)")
    parser.add_argument(
        "subcomando", choices=["sesgos", "evidencias", "decisiones", "tests", "ia", "vulns", "all"]
    )
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    parser.add_argument("--strict", action="store_true", help="Las alertas tambien fallan")
    parser.add_argument("--max-dias", type=int, default=90, help="Antiguedad maxima del SBOM")
    args = parser.parse_args(argv)

    resultado = _ejecutar(args)
    if args.json:
        print(json.dumps(resultado, indent=2, ensure_ascii=False))
    else:
        for e in resultado["errores"]:
            print(f"[ERROR] {e}")
        for w in resultado["alertas"]:
            print(f"[ALERTA] {w}")
        for i in resultado["info"]:
            print(f"[INFO] {i}")
        print(
            f"auto_audit {args.subcomando}: "
            f"{len(resultado['errores'])} errores, {len(resultado['alertas'])} alertas"
        )
    if resultado["errores"] or (args.strict and resultado["alertas"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
