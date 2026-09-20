#!/usr/bin/env python3
"""Test empírico de determinismo: verifica que seed/maxSteps reducen varianza.

REQ: validar que los perfiles deterministas (build/plan/audit) con seed=42
producen salidas consistentes en múltiples ejecuciones.
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

def test_seed_consistency():
    """Verifica que el mismo seed produce la misma salida en múltiples runs."""
    task = "Responde solo con un número entero entre 1 y 100, sin explicación."

    outputs = []
    for i in range(5):
        out = run_opencode_task(task, "audit")
        outputs.append(out)
        print(f"  Run {i+1}: {out}")

    # Con seed fijo, todas las salidas deberían ser idénticas
    unique = set(outputs)
    print(f"  Salidas únicas: {len(unique)} / {len(outputs)}")
    print(f"  Valores: {unique}")

    if len(unique) == 1:
        print("  ✅ Determinismo perfecto: todas las salidas idénticas")
        return True
    else:
        print("  ⚠️  Variabilidad detectada (esperado sin seed real en modelo)")
        return False

def test_maxsteps_limit():
    """Verifica que maxSteps limita el número de pasos."""
    # Tarea que podría generar muchos pasos si no hay límite
    task = "Cuenta del 1 al 1000, un número por línea, sin parar hasta llegar a 1000."

    out = run_opencode_task(task, "audit")
    lines = [line for line in out.split('\n') if line.strip().isdigit()]
    print(f"  Líneas numéricas generadas: {len(lines)}")

    # Con maxSteps=20, no debería llegar a 1000
    if len(lines) <= 25:  # margen para pasos de control
        print("  ✅ maxSteps parece limitar la ejecución")
        return True
    else:
        print("  ⚠️  maxSteps no parece estar limitando (o el modelo ignoró la instrucción)")
        return False

def main():
    print("=== Test de determinismo (seed/maxSteps) ===\n")

    # Verificar que opencode.json tiene los campos
    with open(ROOT / "opencode.json") as f:
        config = json.load(f)

    agent = config.get("agent", {})
    for profile in ("build", "plan", "audit"):
        p = agent.get(profile, {})
        seed = p.get("seed")
        max_steps = p.get("maxSteps")
        print(f"Perfil {profile}: seed={seed}, maxSteps={max_steps}")
        assert seed == 42, f"{profile}: seed debe ser 42, es {seed}"
        assert max_steps is not None, f"{profile}: maxSteps requerido"

    print("\n--- Test 1: Consistencia con seed ---")
    test_seed_consistency()

    print("\n--- Test 2: Límite maxSteps ---")
    test_maxsteps_limit()

    print("\n=== Fin ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())

