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
    python3 scripts/strictdoc_export.py --repro        # 2 exports + comparacion bit a bit

Salida: 0 = ok; 1 = error (version != pin, export fallido); 2 = capa no
instalada. El HTML queda en `<output-dir>/html/index.html`.

Determinismo: strictdoc genera UUIDs aleatorios por nodo (data-nodeid,
turbo-frame, _LINK) y un timestamp de indice de busqueda; la export se hace a
un temporal, se normaliza (mapeo determinista de UUIDs por orden de aparicion y
timestamp fijo) y se publica SOLO el arbol `html/` (el `_cache/` interno, con
rutas absolutas, no forma parte del artefacto). Dos exports del mismo `.sdoc`
producen arboles identicos byte a byte (comprobable con `--repro`).
"""

import argparse
import hashlib
import json
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


_UUID_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-f]{32}(?![0-9a-fA-F])")
_TS_RE = re.compile(r'(<meta name="strictdoc-search-index-timestamp" content=")[^"]*(")')
_TEXT_EXTS = {".html", ".js", ".json", ".css", ".txt"}


def _normalizar_search_index(texto: str) -> str:
    """El indice de busqueda de strictdoc varia entre runs: el dict de claves
    (palabras) se inserta en orden no determinista y las listas de ids de
    documento pueden venir en distinto orden. Se re-serializa con claves
    ordenadas y valores ordenados para que dos exports coincidan byte a byte."""
    prefijo = "window.StrictDoc.search.index = "
    inicio = texto.find(prefijo)
    if inicio < 0:
        return texto
    cabecera = texto[:inicio + len(prefijo)]
    resto = texto[inicio + len(prefijo):].lstrip()
    try:
        datos, fin = json.JSONDecoder().raw_decode(resto)
    except json.JSONDecodeError:
        return texto
    datos = {clave: sorted(valor) if isinstance(valor, list) else valor
             for clave, valor in datos.items()}
    return cabecera + json.dumps(datos, sort_keys=True, separators=(",", ":")) + resto[fin:]


def normalizar_arbol(raiz: Path) -> int:
    """Hace determinista el arbol HTML: cada UUID distinto se sustituye por un
    valor derivado de su orden de aparicion (consistente entre archivos, asi
    los enlaces internos siguen resolviendo), el timestamp del indice de
    busqueda pasa a 0 y el indice se re-serializa con claves ordenadas.
    Devuelve el numero de UUIDs distintos vistos."""
    mapeo: dict[str, str] = {}

    def _sub(m: re.Match) -> str:
        valor = m.group(0)
        if valor not in mapeo:
            mapeo[valor] = f"{len(mapeo):032x}"
        return mapeo[valor]

    for ruta in sorted(p for p in raiz.rglob("*") if p.is_file() and p.suffix in _TEXT_EXTS):
        texto = ruta.read_text(encoding="utf-8", errors="replace")
        nuevo = _TS_RE.sub(r"\g<1>0\g<2>", _UUID_RE.sub(_sub, texto))
        if ruta.name == "static_html_search_index.js":
            nuevo = _normalizar_search_index(nuevo)
        if nuevo != texto:
            ruta.write_text(nuevo, encoding="utf-8")
    return len(mapeo)


def _hash_arbol(raiz: Path) -> list[tuple[str, str]]:
    return [
        (str(p.relative_to(raiz)), hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted(raiz.rglob("*")) if p.is_file()
    ]


def _exportar_y_comprobar(binario: Path, inputs: list[Path], work: Path) -> bool:
    try:
        proc = exportar(binario, inputs, work)
    except (subprocess.SubprocessError, OSError) as exc:
        print(f"error: export fallo: {exc}", file=sys.stderr)
        return False
    if proc.returncode != 0 or not _verificar_html(work):
        print("error: el export no genero HTML", file=sys.stderr)
        print((proc.stdout or "") + (proc.stderr or ""), file=sys.stderr)
        return False
    return True


def _exportar_normalizado(binario: Path, inputs: list[Path], destino_html: Path) -> bool:
    """Exporta a un temporal, normaliza y publica SOLO el arbol html/."""
    with tempfile.TemporaryDirectory(prefix="strictdoc_work_") as work:
        if not _exportar_y_comprobar(binario, inputs, Path(work)):
            return False
        html = Path(work) / "html"
        normalizar_arbol(html)
        shutil.copytree(html, destino_html, dirs_exist_ok=True)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT),
                        help="directorio de salida (defecto: .docs/.storage/strictdoc-html)")
    parser.add_argument("--inputs", nargs="*", help="rutas .sdoc (defecto: las del repo)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="presencia + version == pin")
    group.add_argument("--smoke", action="store_true", help="export E2E a un temporal")
    group.add_argument("--repro", action="store_true",
                       help="dos exports + comparacion bit a bit del arbol normalizado")
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
            if not _exportar_y_comprobar(binario, inputs, Path(tmp)):
                return 1
            normalizar_arbol(Path(tmp) / "html")
        print(f"strictdoc_export: smoke OK ({len(inputs)} .sdoc, version {version})")
        return 0

    if args.repro:
        huellas: list[list[tuple[str, str]]] = []
        for intento in (1, 2):
            with tempfile.TemporaryDirectory(prefix=f"strictdoc_repro_{intento}_") as tmp:
                if not _exportar_y_comprobar(binario, inputs, Path(tmp)):
                    return 1
                html = Path(tmp) / "html"
                normalizar_arbol(html)
                huellas.append(_hash_arbol(html))
        if huellas[0] != huellas[1]:
            distintas = sum(1 for a, b in zip(huellas[0], huellas[1]) if a != b)
            print(f"error: export NO reproducible ({distintas} diferencias)", file=sys.stderr)
            return 1
        print(f"strictdoc_export: reproducible OK ({len(huellas[0])} archivos, "
              f"sha256 identico en 2 exports)")
        return 0

    destino = Path(args.output_dir)
    if not _exportar_normalizado(binario, inputs, destino / "html"):
        return 1
    print(f"strictdoc_export: OK ({len(inputs)} .sdoc) -> {destino / 'html' / 'index.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
