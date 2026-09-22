#!/usr/bin/env python3
"""generate_sbom.py — Genera SBOM con Syft (REQ-020, P0.18).

Genera SBOM en formato CycloneDX JSON y SPDX JSON.
Uso:
    python3 scripts/generate_sbom.py                    # genera en sbom/
    python3 scripts/generate_sbom.py --format spdx      # solo SPDX
    python3 scripts/generate_sbom.py --format cyclonedx # solo CycloneDX
    python3 scripts/generate_sbom.py --check            # verifica que sbom/ existe y no está vacío
"""

import argparse
import json
import shutil
import subprocess
import sys
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
        print("Error: syft no está instalado. Instala con: curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin", file=sys.stderr)
        return False

    output_dir.mkdir(parents=True, exist_ok=True)

    for fmt in formats:
        ext = "json"
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
    """Verifica que el directorio SBOM existe y tiene archivos."""
    if not output_dir.exists():
        print(f"Error: {output_dir} no existe", file=sys.stderr)
        return False
    files = list(output_dir.glob("sbom.*"))
    if not files:
        print(f"Error: no hay archivos SBOM en {output_dir}", file=sys.stderr)
        return False
    for f in files:
        try:
            json.loads(f.read_text())
            print(f"  OK: {f.name} (JSON válido)")
        except json.JSONDecodeError:
            print(f"Error: {f.name} no es JSON válido", file=sys.stderr)
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera SBOM con Syft (P0.18)")
    parser.add_argument("--format", action="append", choices=DEFAULT_FORMATS,
                        help="Formato de salida (repetible; default: ambos)")
    parser.add_argument("--output-dir", default=str(SBOM_DIR), help="Directorio de salida")
    parser.add_argument("--check", action="store_true", help="Solo verifica SBOM existente")
    args = parser.parse_args(argv)

    if args.check:
        return 0 if check_sbom(Path(args.output_dir)) else 1

    formats = args.format or DEFAULT_FORMATS
    return 0 if generate_sbom(formats, Path(args.output_dir)) else 1


if __name__ == "__main__":
    sys.exit(main())