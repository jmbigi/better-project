#!/usr/bin/env python3
"""generate_sbom.py — Genera SBOM con Syft (REQ-020, P0.18).

Genera SBOM en formato CycloneDX JSON y SPDX JSON.
Uso:
    python3 scripts/generate_sbom.py                    # genera en sbom/
    python3 scripts/generate_sbom.py --format spdx      # solo SPDX
    python3 scripts/generate_sbom.py --format cyclonedx # solo CycloneDX
    python3 scripts/generate_sbom.py --check            # valida sbom/ o regenera en temp con syft
    python3 scripts/generate_sbom.py --repro            # 2 generaciones + sha256 normalizado

Reproducibilidad: syft inserta metadatos volatiles por corrida (timestamp,
serialNumber/documentNamespace); `--repro` normaliza esos campos y exige que
dos generaciones produzcan el mismo sha256 (comparacion canonica por formato).
"""

import argparse
import hashlib
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
        # Se excluyen artefactos locales (herramientas en .local/, SBOM previos,
        # venvs): el SBOM describe las dependencias del proyecto, no el tooling
        # de la maquina de desarrollo (evita ruido de vulnerabilidades del
        # propio escaner).
        cmd = [
            syft_path, "dir:.",
            "--exclude", "./sbom/**",
            "--exclude", "./.local/**",
            "--exclude", "./.venv/**",
            "--exclude", "./.venv-audit/**",
            "-o", f"{fmt}={output_file}",
        ]
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


_SERIAL_NEUTRO = "urn:uuid:00000000-0000-0000-0000-000000000000"
_NS_NEUTRO = "https://spdx.org/spdxdocs/normalizado"
_FECHA_NEUTRA = "1970-01-01T00:00:00Z"
FORMATOS_SBOM = {"sbom.cyclonedx.json": "cyclonedx", "sbom.spdx.json": "spdx"}


def normalizar_sbom(datos: dict, formato: str) -> dict:
    """Neutraliza los metadatos volatiles por corrida (LSN-061 aplicada al SBOM)."""
    if formato == "cyclonedx":
        datos["serialNumber"] = _SERIAL_NEUTRO
        datos.setdefault("metadata", {})["timestamp"] = _FECHA_NEUTRA
    elif formato == "spdx":
        datos["documentNamespace"] = _NS_NEUTRO
        datos.setdefault("creationInfo", {})["created"] = _FECHA_NEUTRA
    return datos


def hash_normalizado(ruta: Path, formato: str) -> str:
    """sha256 del JSON canonico (claves ordenadas, volatiles neutralizados)."""
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    canonico = json.dumps(normalizar_sbom(datos, formato), sort_keys=True,
                          separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def check_reproducible() -> bool:
    """Genera el SBOM dos veces en temporales y exige sha256 identico por
    formato tras normalizar los volatiles (reproducibilidad bit a bit)."""
    if not check_syft():
        print("Error: syft no esta instalado; no se puede verificar la "
              "reproducibilidad del SBOM", file=sys.stderr)
        return False
    huellas: dict[str, list[str]] = {nombre: [] for nombre in FORMATOS_SBOM}
    for _ in range(2):
        with tempfile.TemporaryDirectory(prefix="sbom_repro_") as tmp:
            if not generate_sbom(DEFAULT_FORMATS, Path(tmp)):
                return False
            for nombre, formato in FORMATOS_SBOM.items():
                huellas[nombre].append(hash_normalizado(Path(tmp) / nombre, formato))
    distintos = [nombre for nombre, hs in huellas.items() if hs[0] != hs[1]]
    if distintos:
        print(f"Error: SBOM NO reproducible: {distintos}", file=sys.stderr)
        return False
    for nombre, hs in huellas.items():
        print(f"  OK: {nombre} sha256 reproducible ({hs[0][:16]}...)")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera SBOM con Syft (P0.18)")
    parser.add_argument("--format", action="append", choices=DEFAULT_FORMATS,
                        help="Formato de salida (repetible; default: ambos)")
    parser.add_argument("--output-dir", default=str(SBOM_DIR), help="Directorio de salida")
    parser.add_argument("--check", action="store_true",
                        help="Valida sbom/ o verifica regeneracion en temp con syft")
    parser.add_argument("--repro", action="store_true",
                        help="Genera dos veces y exige sha256 identico (volatiles normalizados)")
    args = parser.parse_args(argv)

    if args.check:
        return 0 if check_sbom(Path(args.output_dir)) else 1

    if args.repro:
        return 0 if check_reproducible() else 1

    formats = args.format or DEFAULT_FORMATS
    return 0 if generate_sbom(formats, Path(args.output_dir)) else 1


if __name__ == "__main__":
    sys.exit(main())
