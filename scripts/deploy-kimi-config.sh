#!/usr/bin/env bash
# deploy-kimi-config.sh — Deploy del adaptador Kimi Code CLI al config global
#
# Problema (leccion 2026-09-07): kimi auto-instala actualizaciones
# (tui.toml [upgrade].auto_install = true) y el refresh managed de
# ~/.kimi-code/config.toml BORRA las [[permission.rules]] y [[hooks]]
# aplicadas en la ronda 59. Este script hace el deploy repetible e
# idempotente: reconstruye el bloque gestionado entre marcadores.
#
# Que despliega (fuente de verdad en el repo):
#   1. Provider + modelos locales Ollama (matriz de pruebas P0/P1, nunca
#      modelo principal — excepcion aprobada en AGENTS.md).
#   2. Las 333 [[permission.rules]] + [[hooks]] de .kimi-code/local.toml.
#
# Uso: bash scripts/deploy-kimi-config.sh [--dry-run]
# Idempotente: re-ejecutar es seguro. Backup con timestamp antes de escribir.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

KIMI_HOME="${KIMI_CODE_HOME:-${HOME}/.kimi-code}"
KIMI_CONFIG="${KIMI_HOME}/config.toml"
ADAPTER="${PROJECT_ROOT}/.kimi-code/local.toml"
EXPECTED_RULES=333

MARK_BEGIN="# >>> better-ai deploy (no editar a mano) >>>"
MARK_END="# <<< better-ai deploy <<<"

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

fail() { echo "ERROR: $1" >&2; exit 1; }

[[ -f "${KIMI_CONFIG}" ]] || fail "No existe ${KIMI_CONFIG} (¿kimi instalado?)"
[[ -f "${ADAPTER}" ]] || fail "No existe ${ADAPTER} (fuente de verdad del adaptador)"

# Extrae del adaptador las reglas + hooks (desde el marcador de excepciones
# allow hasta EOF). Es la seccion [[permission.rules]]...[[hooks]] completa.
RULES_BLOCK="$(awk '/^# --- Excepciones allow/{flag=1} flag' "${ADAPTER}")"
[[ -n "${RULES_BLOCK}" ]] || fail "No se encontro el bloque de reglas en ${ADAPTER}"

N_RULES="$(printf '%s\n' "${RULES_BLOCK}" | grep -c '^\[\[permission.rules\]\]')"
[[ "${N_RULES}" -eq "${EXPECTED_RULES}" ]] || \
    fail "Se esperaban ${EXPECTED_RULES} reglas, se encontraron ${N_RULES} (¿drift en ${ADAPTER}?)"

N_HOOKS="$(printf '%s\n' "${RULES_BLOCK}" | grep -c '^\[\[hooks\]\]')"
[[ "${N_HOOKS}" -ge 1 ]] || fail "No se encontro [[hooks]] en el bloque extraido"

# Bloque gestionado: provider/modelos locales + ruleset
MANAGED_BLOCK="$(cat <<EOF
${MARK_BEGIN}
# =============================================================================
# Modelos locales Ollama (localhost) — EXCEPCION APROBADA: matriz de pruebas
# P0/P1 unicamente; NUNCA modelo principal de desarrollo (AGENTS.md).
# =============================================================================

[providers."local:ollama"]
type = "openai"
name = "Ollama (local)"
base_url = "http://localhost:11434/v1"
api_key = "ollama"

[models."local/qwen2.5-coder-1.5b"]
provider = "local:ollama"
model = "qwen2.5-coder:1.5b"
max_context_size = 32768
capabilities = [ "tool_use" ]
display_name = "Qwen2.5 Coder 1.5B local (liviano, matriz pruebas)"

[models."local/deepseek-coder-1.3b"]
provider = "local:ollama"
model = "deepseek-coder:1.3b"
max_context_size = 16384
capabilities = [ "tool_use" ]
display_name = "DeepSeek Coder 1.3B local (liviano, matriz pruebas)"

[models."local/starcoder2-7b"]
provider = "local:ollama"
model = "starcoder2:7b"
max_context_size = 8192
capabilities = [ "tool_use" ]
display_name = "StarCoder2 7B local (programacion especializada, matriz pruebas)"

[models."local/qwen2.5-coder-3b"]
provider = "local:ollama"
model = "qwen2.5-coder:3b"
max_context_size = 32768
capabilities = [ "tool_use" ]
display_name = "Qwen2.5 Coder 3B local (liviano, matriz pruebas)"

[models."local/qwen2.5-coder-7b"]
provider = "local:ollama"
model = "qwen2.5-coder:7b"
max_context_size = 32768
capabilities = [ "tool_use" ]
display_name = "Qwen2.5 Coder 7B Q4_K_M local (base, matriz pruebas)"

[models."local/qwen2.5-coder-7b-q5"]
provider = "local:ollama"
model = "hf.co/bartowski/Qwen2.5-Coder-7B-Instruct-GGUF:Q5_K_M"
max_context_size = 32768
capabilities = [ "tool_use" ]
display_name = "Qwen2.5 Coder 7B Q5_K_M local (calidad, HF/bartowski, matriz pruebas)"

# =============================================================================
# Ruleset P0/P1 (333 reglas + hook) — fuente: .kimi-code/local.toml del repo.
# REAPLICAR tras cada actualizacion de kimi: bash scripts/deploy-kimi-config.sh
# =============================================================================
${RULES_BLOCK}
${MARK_END}
EOF
)"

if ${DRY_RUN}; then
    echo "[dry-run] Se desplegarian ${N_RULES} reglas + ${N_HOOKS} hook en ${KIMI_CONFIG}"
    exit 0
fi

BACKUP="${KIMI_CONFIG}.bak-$(date +%Y%m%d-%H%M%S)"
cp "${KIMI_CONFIG}" "${BACKUP}"
echo "Backup: ${BACKUP}"

# Reconstruye el config: quita bloque previo entre marcadores (si existe) y
# agrega el bloque gestionado al final. Idempotente.
TMP_FILE="$(mktemp)"
awk -v begin="${MARK_BEGIN}" -v end="${MARK_END}" '
    $0 == begin {inblock=1; next}
    $0 == end   {inblock=0; next}
    !inblock    {print}
' "${KIMI_CONFIG}" > "${TMP_FILE}"
# Normaliza: sin lineas en blanco colgando al final (restos de deploys previos)
while [[ -z "$(tail -n 1 "${TMP_FILE}")" ]]; do
    sed -i '' '$d' "${TMP_FILE}"
done
printf '%s\n' "${MANAGED_BLOCK}" >> "${TMP_FILE}"
cat "${TMP_FILE}" > "${KIMI_CONFIG}"
rm -f "${TMP_FILE}"

# Verificacion post-deploy: conteos y ausencia de marcadores duplicados
FINAL_RULES="$(grep -c '^\[\[permission.rules\]\]' "${KIMI_CONFIG}")"
FINAL_HOOKS="$(grep -c '^\[\[hooks\]\]' "${KIMI_CONFIG}")"
MARKERS="$(grep -cF "${MARK_BEGIN}" "${KIMI_CONFIG}")"
[[ "${FINAL_RULES}" -eq "${EXPECTED_RULES}" ]] || fail "Post-deploy: ${FINAL_RULES} reglas (esperado ${EXPECTED_RULES})"
[[ "${FINAL_HOOKS}" -eq 1 ]] || fail "Post-deploy: ${FINAL_HOOKS} hooks (esperado 1)"
[[ "${MARKERS}" -eq 1 ]] || fail "Post-deploy: ${MARKERS} marcadores de inicio (esperado 1)"

echo "OK: ${FINAL_RULES} reglas + ${FINAL_HOOKS} hook desplegados en ${KIMI_CONFIG}"
echo "Nota: la validacion de sintaxis TOML real ocurre al iniciar una sesion de kimi (falla en voz alta)."
