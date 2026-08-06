#!/usr/bin/env python3
"""notas.py — Gestor de notas CLI de la demo (REQ-001).

Uso:
    python3 notas.py add "texto"
    python3 notas.py list
    python3 notas.py done <id>
"""

import argparse
import json
import os
import sys
import tempfile

ARCHIVO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notas.json")


def cargar_notas() -> list[dict]:
    # REQ-001: persistencia local en JSON
    if not os.path.exists(ARCHIVO):
        return []
    with open(ARCHIVO, encoding="utf-8") as fh:
        return json.load(fh)


def guardar_notas(notas: list[dict]) -> None:
    # REQ-001 + LSN-001: escritura atomica (temp + rename)
    fd, temporal = tempfile.mkstemp(
        dir=os.path.dirname(ARCHIVO), prefix="notas.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(notas, fh, ensure_ascii=False, indent=2)
        os.replace(temporal, ARCHIVO)
    except BaseException:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise


def cmd_add(texto: str) -> int:
    # REQ-001: anadir nota
    notas = cargar_notas()
    notas.append({"id": len(notas) + 1, "texto": texto, "hecha": False})
    guardar_notas(notas)
    print(f"anadida nota {len(notas)}")
    return 0


def cmd_list() -> int:
    # REQ-001: listar notas
    notas = cargar_notas()
    if not notas:
        print("sin notas")
        return 0
    for nota in notas:
        marca = "x" if nota["hecha"] else " "
        print(f"[{marca}] {nota['id']}: {nota['texto']}")
    return 0


def cmd_done(nid: int) -> int:
    # REQ-001: marcar nota como hecha
    notas = cargar_notas()
    for nota in notas:
        if nota["id"] == nid:
            nota["hecha"] = True
            guardar_notas(notas)
            print(f"nota {nid} hecha")
            return 0
    print(f"no existe la nota {nid}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="notas", description="Gestor de notas CLI")
    sub = parser.add_subparsers(dest="comando", required=True)
    p_add = sub.add_parser("add", help="anadir nota")
    p_add.add_argument("texto")
    p_list = sub.add_parser("list", help="listar notas")
    p_done = sub.add_parser("done", help="marcar nota como hecha")
    p_done.add_argument("id", type=int)
    args = parser.parse_args()

    if args.comando == "add":
        return cmd_add(args.texto)
    if args.comando == "list":
        return cmd_list()
    return cmd_done(args.id)


if __name__ == "__main__":
    sys.exit(main())
