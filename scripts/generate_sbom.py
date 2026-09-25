#!/usr/bin/env python3
"""generate_sbom.py — Genera SBOM con Syft (REQ-020, P0.18).

Genera SBOM en formato CycloneDX JSON y SPDX JSON.
Uso:
    python3 scripts/generate_sbom.py                    # genera en sbom/
    python3 scripts/generate_sbom.py --format spdx      # solo SPDX
    python3 scripts/generate_sbom.py --format cyclonedx # solo CycloneDX
    python3 scripts/generate_sbom.py --check            # valida sbom/ o regenera en temp con syft
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SBOM_DIR = ROOT / "sbom"
DEFAULT_FORMATS = ["cyclonedx-json", "spdx-json"]


def check_syft() -> str | None:
    """Devuelve la ruta a syft si está disponible."""
    # Check PATH first
    path = shutil.which("syft")
    if path:
        return path
    # Check local bin
    local_bin = ROOT / ".local" / "bin" / "syft"
    if local_bin.exists():
        return str(local_bin)
    local_bin_exe = ROOT / ".local" / "bin" / "syft.exe"
    if local_bin_exe.exists():
        return str(local_bin_exe)
    return None


def generate_sbom(formats: list[str], output_dir: Path) -> bool:
    """Genera SBOM en los formatos especificados."""
    syft_path = check_syft()
    if not syft_path:
        print(
            "Error: syft no esta instalado. Descarga el release oficial de "
            "https://github.com/anchore/syft/releases (verifica su checksums.txt) "
            "y coloca el binario en PATH o en .local/bin/syft",
            file=sys.stderr,
        )
        return False

    output_dir.mkdir(parents=True, exist_ok=True)

    for fmt in formats:
        output_file = output_dir / f"sbom.{fmt.replace('-', '.')}"
        cmd = [syft_path, "dir:.", "-o", f"{fmt}={output_file}"]
        print(f"Generando {output_file}...")
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error generando {fmt}: {result.stderr}", file=sys.stderr)
            return False
        print(f"  OK: {output_file}")

    return True


def check_sbom(output_dir: Path) -> bool:
    """Verifica el SBOM: JSON validos en output_dir o regeneracion real en temp.

    'Regenerable' significa que si los artefactos no estan presentes (p.ej. en
    un clon limpio, sbom/ no se versiona), syft pueda generarlos en un
    directorio temporal.
    """
    if output_dir.exists():
        files = list(output_dir.glob("sbom.*"))
        if files:
            for f in files:
                try:
                    json.loads(f.read_text())
                    print(f"  OK: {f.name} (JSON válido)")
                except json.JSONDecodeError:
                    print(f"Error: {f.name} no es JSON válido", file=sys.stderr)
                    return False
            return True
    if not check_syft():
        print(
            f"Error: no hay SBOM en {output_dir} y syft no esta disponible para regenerarlo",
            file=sys.stderr,
        )
        return False
    with tempfile.TemporaryDirectory(prefix="sbom_check_") as tmp:
        print(f"  Sin artefactos en {output_dir}: regenerando en {tmp} para verificar")
        return generate_sbom(DEFAULT_FORMATS, Path(tmp))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera SBOM con Syft (P0.18)")
    parser.add_argument("--format", action="append", choices=DEFAULT_FORMATS,
                        help="Formato de salida (repetible; default: ambos)")
    parser.add_argument("--output-dir", default=str(SBOM_DIR), help="Directorio de salida")
    parser.add_argument("--check", action="store_true",
                        help="Valida sbom/ o verifica regeneracion en temp con syft")
    args = parser.parse_args(argv)

    if args.check:
        return 0 if check_sbom(Path(args.output_dir)) else 1

    formats = args.format or DEFAULT_FORMATS
    return 0 if generate_sbom(formats, Path(args.output_dir)) else 1


if __name__ == "__main__":
    sys.exit(main())
