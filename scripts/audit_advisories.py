#!/usr/bin/env python3
"""audit_advisories.py — Auditoria de cadena de suministro con severidad (REQ-020).

# REQ-020

Ejecuta `pip-audit --no-deps` sobre un requirements/lock, enriquece cada
advisory con la severidad CVSS y los alias (CVE/GHSA) consultando la API de
OSV, y emite una tabla markdown (o JSON). Sin dependencias externas (urllib).

Falla explicito si `pip-audit` no esta instalado o la red falla (P1.19); con
`--offline` omite la consulta a OSV y lo indica en la salida.

Uso:
    python3 scripts/audit_advisories.py
    python3 scripts/audit_advisories.py --requirements requirements-optional.lock
    python3 scripts/audit_advisories.py --offline --json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REQ = ROOT / "requirements-optional.lock"
OSV_URL = "https://api.osv.dev/v1/vulns/"


def run_pip_audit(req_path: Path, runner=None) -> list[dict]:
    """Ejecuta pip-audit y devuelve una fila por advisory."""
    if runner is None:
        if shutil.which("pip-audit") is None:
            raise RuntimeError(
                "pip-audit no esta instalado (P0.18); instalalo en el usuario, no global"
            )

        def runner():
            return subprocess.run(
                ["pip-audit", "--no-deps", "-f", "json", "-r", str(req_path)],
                capture_output=True, text=True, timeout=300, check=False,
            )

    proc = runner()
    # pip-audit devuelve 1 cuando encuentra vulnerabilidades: no es un fallo del comando.
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"pip-audit fallo (exit {proc.returncode}): {(proc.stderr or '')[:300]}")
    data = json.loads(proc.stdout or "{}")
    filas: list[dict] = []
    vistos: set[tuple[str, str, str]] = set()
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            clave = (vuln.get("id", "?"), dep.get("name", "?"), dep.get("version", "?"))
            if clave in vistos:
                continue
            vistos.add(clave)
            filas.append(
                {
                    "advisory": clave[0],
                    "paquete": clave[1],
                    "version": clave[2],
                    "fix": ", ".join(vuln.get("fix_versions", [])) or "sin parche",
                    "aliases": list(vuln.get("aliases", [])),
                    "resumen": (vuln.get("description") or "").split(".")[0],
                }
            )
    return filas


def osv_detalle(vuln_id: str, opener=None) -> dict:
    """Consulta OSV y devuelve {cvss, aliases, resumen}. Falla explicito (P1.19)."""
    opener = opener or urllib.request.urlopen
    try:
        with opener(OSV_URL + vuln_id, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo consultar OSV para {vuln_id}: {exc}") from exc
    severidades = [str(s.get("score", "")) for s in data.get("severity", [])]
    return {
        "cvss": "; ".join(severidades),
        "aliases": list(data.get("aliases", [])),
        "resumen": data.get("summary", ""),
    }


def enriquecer(filas: list[dict], opener=None, offline: bool = False) -> list[dict]:
    """Anade columna CVSS (y alias/resumen) a cada fila."""
    for fila in filas:
        if offline:
            fila["cvss"] = "(offline)"
            continue
        detalle = osv_detalle(fila["advisory"], opener=opener)
        fila["cvss"] = detalle["cvss"] or "(sin CVSS)"
        fila["aliases"] = detalle["aliases"] or fila["aliases"]
        fila["resumen"] = detalle["resumen"] or fila["resumen"]
    return filas


def render_markdown(filas: list[dict]) -> str:
    lineas = [
        "| Advisory | Paquete | Version | Fix | CVSS | Alias | Resumen |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in filas:
        lineas.append(
            f"| {f['advisory']} | {f['paquete']} | {f['version']} | {f['fix']} | "
            f"{f['cvss']} | {', '.join(f['aliases'])} | {f['resumen']} |"
        )
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Advisories con severidad OSV (REQ-020)")
    parser.add_argument("--requirements", default=str(DEFAULT_REQ), help="requirements/lock a auditar")
    parser.add_argument("--offline", action="store_true", help="No consultar OSV (sin CVSS)")
    parser.add_argument("--json", action="store_true", help="Salida JSON")
    args = parser.parse_args(argv)

    try:
        filas = run_pip_audit(Path(args.requirements))
        filas = enriquecer(filas, offline=args.offline)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(filas, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(filas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
