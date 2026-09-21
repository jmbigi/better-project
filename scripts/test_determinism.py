#!/usr/bin/env python3
"""Test empírico de determinismo: mide la varianza real de los perfiles.

REQ-022. Verificado contra https://opencode.ai/config.json (2026-09-21):
`steps` es el campo soportado para limitar iteraciones; `maxSteps` está
@deprecated; `seed` no es una opción nativa de AgentConfig (no aparece en el
esquema oficial). opencode reenviaría opciones desconocidas al proveedor como
model option, pero sin garantía de que las respete, por lo que NO se adopta
(ver docs/ARQUITECTURA-DETERMINISMO.md y docs/decisions/ADR-009.md).

Este script valida la CONFIGURACIÓN (steps presente, sin seed/maxSteps) y mide
empíricamente el determinismo con temperature=0.0 (nunca asume reproducción
bit a bit: la reporta).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def run_opencode_task(task: str, profile: str = "audit") -> str:
    """Ejecuta opencode con un perfil y tarea específicos, retorna stdout."""
    env = {**os.environ}
    result = subprocess.run(
        ["opencode", "run", "--agent", profile, task],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
        env=env,
    )
    # Extraer solo la respuesta del modelo (después del header del agente)
    stdout = result.stdout.strip()
    # El formato es: "> audit · model\n\nrespuesta"
    lines = stdout.split('\n')
    if len(lines) >= 2 and lines[0].startswith('>'):
        return '\n'.join(lines[2:]).strip()
    return stdout

def test_temperature_consistency():
    """Mide si temperature=0.0 produce la misma salida en múltiples runs.

    No hay seed soportado por opencode: se reporta la varianza real, no se
    asume determinismo (P0.1).
    """
    task = "Responde solo con un número entero entre 1 y 100, sin explicación."

    outputs = []
    for i in range(5):
        out = run_opencode_task(task, "audit")
        outputs.append(out)
        print(f"  Run {i+1}: {out}")

    # Se reporta la varianza real; con temperature=0.0 se espera baja, pero no
    # se garantiza reproducibilidad bit a bit (limitacion declarada).
    unique = set(outputs)
    print(f"  Salidas únicas: {len(unique)} / {len(outputs)}")
    print(f"  Valores: {unique}")

    if len(unique) == 1:
        print("  ✅ Determinismo observado: todas las salidas idénticas")
        return True
    else:
        print("  ⚠️  Variabilidad detectada (no se garantiza reproducibilidad bit a bit)")
        return False

def test_steps_limit():
    """Verifica que `steps` limita el número de iteraciones del agente."""
    # Tarea que podría generar muchos pasos si no hay límite
    task = "Cuenta del 1 al 1000, un número por línea, sin parar hasta llegar a 1000."

    out = run_opencode_task(task, "audit")
    lines = [line for line in out.split('\n') if line.strip().isdigit()]
    print(f"  Líneas numéricas generadas: {len(lines)}")

    # Con steps=20, no debería llegar a 1000
    if len(lines) <= 25:  # margen para pasos de control
        print("  ✅ steps parece limitar la ejecución")
        return True
    else:
        print("  ⚠️  steps no parece estar limitando (o el modelo ignoró la instrucción)")
        return False

def main():
    print("=== Test de determinismo (temperature/steps) ===\n")

    # Verificar que opencode.json tiene los campos (verificado contra el $schema
    # oficial el 2026-09-21: steps soportado, maxSteps @deprecated, seed no nativo)
    with open(ROOT / "opencode.json") as f:
        config = json.load(f)

    agent = config.get("agent", {})
    for profile in ("build", "plan", "audit"):
        p = agent.get(profile, {})
        print(f"Perfil {profile}: temperature={p.get('temperature')}, top_p={p.get('top_p')}, steps={p.get('steps')}")
        assert p.get("steps") is not None, f"{profile}: steps requerido"
        assert "seed" not in p, f"{profile}: seed no es opcion nativa de opencode"
        assert "maxSteps" not in p, f"{profile}: maxSteps deprecado; usar steps"

    print("\n--- Test 1: Consistencia con temperature=0.0 ---")
    test_temperature_consistency()

    print("\n--- Test 2: Límite steps ---")
    test_steps_limit()

    print("\n=== Fin ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())

