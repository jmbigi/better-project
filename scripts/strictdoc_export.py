#!/usr/bin/env python3
# REQ-032: capa opcional StrictDoc — export HTML de los .sdoc (ADR-011).
r"""strictdoc_export.py — exporta los .sdoc a HTML con strictdoc (capa opcional).

La capa pesada vive aislada en `.local/strictdoc-venv` (gitignored, P0.5) y se
instala con `scripts/setup_strictdoc.sh` desde `requirements-strictdoc.lock`
(hashes, P0.18). El nucleo no depende de strictdoc (ADR-011): sin la capa este
script sale con codigo 2 y guia de instalacion; el verificador emite [SKIP].

Uso:
    python3 scripts/strictdoc_export.py                # exporta los .sdoc del repo
    python3 scripts/strictdoc_export.py --check        # presencia + version == pin
    python3 scripts/strictdoc_export.py --smoke        # export E2E a temporal

Salida: 0 = ok; 1 = error (version != pin, export fallido); 2 = capa no
instalada. El HTML queda en `<output-dir>/html/index.html`.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_BIN = ROOT / ".local" / "strictdoc-venv" / "bin" / "strictdoc"
PIN_FILE = ROOT / "requirements-strictdoc.txt"
PIN_RE = re.compile(r"strictdoc==(\d[\d.]*)")
SDOC_DIR = ROOT / ".docs" / "requirements"
DEFAULT_OUTPUT = ROOT / ".docs" / ".storage" / "strictdoc-html"
PROJECT_TITLE = "better-project (REQ-032)"
TIMEOUT_S = 300


def pin_esperado() -> str:
    m = PIN_RE.search(PIN_FILE.read_text(encoding="utf-8"))
    if not m:
        print(f"error: no se pudo leer el pin strictdoc== en {PIN_FILE}", file=sys.stderr)
        raise SystemExit(1)
    return m.group(1)


def localizar(root: Path = ROOT) -> Path | None:
    """Binario de la capa: $STRICTDOC_BIN -> venv aislado -> PATH."""
    override = os.environ.get("STRICTDOC_BIN")
    if override:
        p = Path(override)
        return p if p.exists() else None
    for cand in (root / ".local" / "strictdoc-venv" / "bin" / "strictdoc",
                 root / ".local" / "strictdoc-venv" / "bin" / "strictdoc.exe"):
        if cand.exists():
            return cand
    found = shutil.which("strictdoc")
    return Path(found) if found else None


def version_de(binario: Path) -> str:
    proc = subprocess.run([str(binario), "--version"], capture_output=True,
                          text=True, timeout=60)
    m = re.search(r"(\d[\d.]*)", proc.stdout or proc.stderr)
    return m.group(1) if m else "desconocida"


def sdoc_files(root: Path = ROOT) -> list[Path]:
    base = root / ".docs" / "requirements"
    if not base.is_dir():
        return []
    return sorted(base.rglob("*.sdoc"))


def exportar(binario: Path, inputs: list[Path], output_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(binario), "export", *(str(p) for p in inputs),
         "--output-dir", str(output_dir), "--project-title", PROJECT_TITLE],
        capture_output=True, text=True, timeout=TIMEOUT_S,
    )


def _sin_capa() -> int:
    print("strictdoc_export: capa StrictDoc no instalada.")
    print("  Instala (venv aislado, hashes P0.18): bash scripts/setup_strictdoc.sh")
    return 2


def _verificar_html(output_dir: Path) -> bool:
    return any(output_dir.rglob("*.html"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT),
                        help="directorio de salida (defecto: .docs/.storage/strictdoc-html)")
    parser.add_argument("--inputs", nargs="*", help="rutas .sdoc (defecto: las del repo)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="presencia + version == pin")
    group.add_argument("--smoke", action="store_true", help="export E2E a un temporal")
    args = parser.parse_args(argv)

    pin = pin_esperado()
    binario = localizar()
    if binario is None:
        return _sin_capa()

    try:
        version = version_de(binario)
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"error: no se pudo ejecutar {binario}: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if version == pin:
            print(f"strictdoc_export: OK ({binario}, version {version})")
            return 0
        print(f"error: version {version} != pin {pin} (usa scripts/setup_strictdoc.sh)",
              file=sys.stderr)
        return 1

    inputs = [Path(p) for p in args.inputs] if args.inputs else sdoc_files()
    if not inputs:
        print("strictdoc_export: sin .sdoc que exportar (nada que hacer)")
        return 0

    if args.smoke:
        with tempfile.TemporaryDirectory(prefix="strictdoc_smoke_") as tmp:
            try:
                proc = exportar(binario, inputs, Path(tmp))
            except (subprocess.SubprocessError, OSError) as exc:
                print(f"error: export fallo: {exc}", file=sys.stderr)
                return 1
            if proc.returncode != 0 or not _verificar_html(Path(tmp)):
                print("error: el export smoke no genero HTML", file=sys.stderr)
                print((proc.stdout or "") + (proc.stderr or ""), file=sys.stderr)
                return 1
        print(f"strictdoc_export: smoke OK ({len(inputs)} .sdoc, version {version})")
        return 0

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        proc = exportar(binario, inputs, output_dir)
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"error: export fallo: {exc}", file=sys.stderr)
        return 1
    if proc.returncode != 0 or not _verificar_html(output_dir):
        print("error: el export no genero HTML", file=sys.stderr)
        print((proc.stdout or "") + (proc.stderr or ""), file=sys.stderr)
        return 1
    print(f"strictdoc_export: OK ({len(inputs)} .sdoc) -> {output_dir / 'html' / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
