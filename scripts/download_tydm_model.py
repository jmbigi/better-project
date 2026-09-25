#!/usr/bin/env python3
"""download_tydm_model.py — Descarga idempotente del modelo GGUF para tydm_llama.py.

Uso:
    python3 scripts/download_tydm_model.py [--yes]

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
DEFAULT_DEST = Path.home() / ".cache" / "better-project" / "tydm" / DEFAULT_FILE
EXPECTED_BYTES = 2_900_000_000  # ~3.0 GB reales; minimo para detectar descargas truncadas
CHUNK_SIZE = 8192


def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _download(url: str, dest: Path, yes: bool) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    existing = dest.stat().st_size if dest.exists() else 0

    headers = {"User-Agent": "better-project/tydm-llama"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    req = urllib.request.Request(url, headers=headers)

    print(f"Origen:  {url}")
    print(f"Destino: {dest}")

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            # Si el servidor ignora Range responde 200 y hay que reiniciar.
            if existing and getattr(response, "status", 200) != 206:
                existing = 0
            remaining = int(response.headers.get("Content-Length", 0))
            total = existing + remaining
            if total:
                print(f"Tamano:  {_human(total)}")
            if not yes:
                answer = input("Descargar? [s/N]: ")
                if answer.lower() not in {"s", "si", "yes", "y"}:
                    print("Descarga cancelada.")
                    return
            print("Reanudando..." if existing else "Descargando...")
            downloaded = existing
            with open(dest, "ab" if existing else "wb") as f:
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

    final_size = dest.stat().st_size
    if final_size < EXPECTED_BYTES:
        raise RuntimeError(
            f"El archivo descargado es demasiado pequeno ({_human(final_size)}). "
            "Es posible que la URL haya cambiado o la descarga haya fallado."
        )
    print(f"OK: {_human(final_size)} descargado en {dest}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga el modelo GGUF para tydm_llama.py")
    parser.add_argument("--yes", action="store_true", help="No pedir confirmacion")
    parser.add_argument("--url", default=os.getenv("TYDM_DOWNLOAD_URL", DEFAULT_URL), help="URL del modelo")
    parser.add_argument("--dest", default=os.getenv("TYDM_MODEL_PATH", str(DEFAULT_DEST)), help="Ruta de destino")
    args = parser.parse_args()

    dest = Path(args.dest)
    if dest.exists() and dest.stat().st_size >= EXPECTED_BYTES:
        print(f"El modelo ya existe: {dest} ({_human(dest.stat().st_size)})")
        return 0
    if dest.exists():
        print(
            f"Descarga incompleta detectada: {dest} "
            f"({_human(dest.stat().st_size)} de ~{_human(EXPECTED_BYTES)}). Se reanudara."
        )

    try:
        _download(args.url, dest, args.yes)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
