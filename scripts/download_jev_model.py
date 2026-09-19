#!/usr/bin/env python3
"""download_jev_model.py — Descarga idempotente del modelo GGUF para jev_llama.py.

Uso:
    python3 scripts/download_jev_model.py [--yes]

Descarga el modelo recomendado desde HuggingFace si no existe localmente.
Sin --yes, pide confirmacion antes de descargar.

REQ-011
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_REPO = "bartowski/Qwen_Qwen3.5-4B-GGUF"
DEFAULT_FILE = "Qwen_Qwen3.5-4B-Q4_K_M.gguf"
DEFAULT_URL = f"https://huggingface.co/{DEFAULT_REPO}/resolve/main/{DEFAULT_FILE}"
DEFAULT_DEST = Path.home() / ".cache" / "better-project" / "jev" / DEFAULT_FILE
EXPECTED_BYTES = 2_200_000_000  # ~2.2 GB; se verifica tamano minimo post-descarga
CHUNK_SIZE = 8192


def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _download(url: str, dest: Path, yes: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "better-project/jev-llama"})

    print(f"Origen:  {url}")
    print(f"Destino: {dest}")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            total = int(response.headers.get("Content-Length", 0))
            if total:
                print(f"Tamano:  {_human(total)}")
            if not yes:
                answer = input("Descargar? [s/N]: ")
                if answer.lower() not in {"s", "si", "yes", "y"}:
                    print("Descarga cancelada.")
                    return
            print("Descargando...")
            downloaded = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(f"\r  {pct}% ({_human(downloaded)} / {_human(total)})", end="", flush=True)
            print()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Error HTTP {exc.code} descargando {url}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Error de red descargando {url}: {exc.reason}") from exc

    if dest.stat().st_size < EXPECTED_BYTES:
        raise RuntimeError(
            f"El archivo descargado es demasiado pequeno ({_human(dest.stat().st_size)}). "
            "Es posible que la URL haya cambiado o la descarga haya fallado."
        )
    print(f"OK: {_human(dest.stat().st_size)} descargado en {dest}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga el modelo GGUF para jev_llama.py")
    parser.add_argument("--yes", action="store_true", help="No pedir confirmacion")
    parser.add_argument("--url", default=os.getenv("JEV_DOWNLOAD_URL", DEFAULT_URL), help="URL del modelo")
    parser.add_argument("--dest", default=os.getenv("JEV_MODEL_PATH", str(DEFAULT_DEST)), help="Ruta de destino")
    args = parser.parse_args()

    dest = Path(args.dest)
    if dest.exists():
        print(f"El modelo ya existe: {dest} ({_human(dest.stat().st_size)})")
        return 0

    try:
        _download(args.url, dest, args.yes)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
