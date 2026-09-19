#!/usr/bin/env python3
"""Hook PreToolUse para Kimi Code CLI: envuelve scripts/analyze_shell.py.

Kimi Code pasa el evento como JSON por stdin (doc oficial de hooks):

    {"hook_event_name": "PreToolUse",
     "tool_input": {"command": "rm -rf /tmp/x"}, ...}

El hook bloquea con exit code 2 (stderr = razon) si analyze_shell.py detecta
patrones peligrosos (P0.8: pipes curl|bash, sh -c con subcomandos
destructivos, rutas absolutas, etc.). REQ-005.

Decision de seguridad: cualquier fallo del analizador (tokenizacion
imposible, timeout, salida no cero sin hallazgos parseables) se trata como
BLOQUEO, no como allow, porque los hooks de Kimi Code son fail-open por
disenio: si el propio script del hook se cuelga o el runtime lo ignora, el
comando se permitiria. Asi la unica via de "permitir" es un analisis
completo y limpio.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ANALYZER = Path(__file__).resolve().parent.parent.parent / "scripts" / "analyze_shell.py"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"Hook REQ-005: JSON de entrada invalido: {exc}\n")
        return 2

    if not isinstance(payload, dict):
        sys.stderr.write("Hook REQ-005: payload del hook no es un objeto JSON\n")
        return 2

    command = payload.get("tool_input", {}).get("command", "")
    if not isinstance(command, str) or not command.strip():
        return 0

    try:
        proc = subprocess.run(
            [sys.executable, str(ANALYZER), command],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write("Hook REQ-005: timeout analizando el comando\n")
        return 2

    if proc.returncode != 0:
        detail = (proc.stdout + proc.stderr).strip()
        sys.stderr.write(
            f"Hook REQ-005: comando bloqueado por analyze_shell.py\n{detail}\n"
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
