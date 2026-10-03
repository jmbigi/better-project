#!/usr/bin/env bash
# REQ-032: capa opcional StrictDoc (export HTML de los .sdoc).
# Instala strictdoc 0.30.1 en un venv AISLADO (.local/strictdoc-venv,
# gitignored) desde requirements-strictdoc.lock (hashes, P0.18) y audita con
# pip-audit. El nucleo stdlib-first no se toca (ADR-011).
# Uso: bash scripts/setup_strictdoc.sh [--yes]
#   --yes: acepta el riesgo en modo no interactivo (imprime el aviso igual).
set -u
cd "$(dirname "$0")/.." || exit 1

YES=0
[ "${1:-}" = "--yes" ] && YES=1

fail() {
    echo "[ERROR] $1" >&2
    exit 1
}

VENV=".local/strictdoc-venv"
LOCK="requirements-strictdoc.lock"
REQ_PIN="requirements-strictdoc.txt"

command -v python3 >/dev/null 2>&1 || fail "python3 no disponible"
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" \
    || fail "se requiere python3 >= 3.10 (tienes $(python3 --version 2>&1))"
[ -f "$LOCK" ] || fail "falta $LOCK (genera con: uv pip compile --generate-hashes $REQ_PIN -o $LOCK)"
[ -f "$REQ_PIN" ] || fail "falta $REQ_PIN"
PIN="$(grep -oE 'strictdoc==[0-9][0-9.]*' "$REQ_PIN" | head -1 | cut -d= -f3)"
[ -n "$PIN" ] || fail "no se pudo leer el pin de strictdoc en $REQ_PIN"

echo "== Capa StrictDoc (REQ-032): strictdoc $PIN, instalacion aislada =="
echo "  Destino: $VENV (gitignored, P0.5). Requiere red y ~444 MB de disco."
echo "  AVISO (P0.18): auditoria pip-audit de la ronda 38 (01-10-2026): 0"
echo "  vulnerabilidades conocidas para este arbol de dependencias."
if [ "$YES" = "1" ]; then
    echo "  [--yes] riesgo aceptado en modo no interactivo"
else
    printf "  ¿Instalar la capa StrictDoc aceptando ese riesgo? [s/N] "
    read -r RESPUESTA
    case "$RESPUESTA" in
        s|S|si|SI|y|Y) ;;
        *) echo "  [SKIP] sin instalacion"; exit 0 ;;
    esac
    printf "  Escribe 'acepto el riesgo' para confirmar: "
    read -r CONFIRMA
    [ "$CONFIRMA" = "acepto el riesgo" ] || { echo "  [SKIP] sin confirmacion de riesgo"; exit 0; }
fi

STRICTDOC="$VENV/bin/strictdoc"
if [ ! -x "$STRICTDOC" ]; then
    echo "  Creando venv aislado..."
    python3 -m venv "$VENV" || fail "no se pudo crear $VENV"
fi

# P0.18: el bootstrap de `python3 -m venv` instala pip/setuptools del sistema
# (pip 24.0 y setuptools 65.5.0 en el primer intento, 2026-10-03: 10 advisories
# en pip-audit) y pip-audit los audita como parte del entorno. Se actualizan a
# versiones con parche antes de auditar (hallazgo LSN-059).
"$VENV/bin/python" -m pip install --upgrade --quiet pip setuptools \
    || fail "no se pudo actualizar pip/setuptools del venv"

INSTALADA=""
if [ -x "$STRICTDOC" ]; then
    INSTALADA="$("$STRICTDOC" --version 2>/dev/null | grep -oE '[0-9][0-9.]*' | head -1)"
fi
if [ "$INSTALADA" = "$PIN" ]; then
    echo "  [OK] strictdoc $PIN ya instalado (idempotente)"
else
    echo "  Instalando desde $LOCK con hashes (--require-hashes)..."
    "$VENV/bin/pip" install --quiet --require-hashes -r "$LOCK" \
        || fail "fallo pip install del lock; revisa la salida"
    INSTALADA="$("$STRICTDOC" --version 2>/dev/null | grep -oE '[0-9][0-9.]*' | head -1)"
    [ "$INSTALADA" = "$PIN" ] || fail "version instalada '$INSTALADA' != pin '$PIN'"
    echo "  [OK] strictdoc $PIN instalado en $VENV"
fi

if command -v pip-audit >/dev/null 2>&1; then
    SITE="$(find "$VENV/lib" -maxdepth 2 -type d -name site-packages | head -1)"
    [ -n "$SITE" ] || fail "no se pudo localizar site-packages en $VENV"
    echo "  Auditando con pip-audit (P0.18)..."
    pip-audit --path "$SITE" --progress-spinner off \
        || fail "pip-audit reporto vulnerabilidades o no pudo completar la auditoria (P0.18: bloquea sin excepcion documentada)"
    echo "  [OK] pip-audit sin vulnerabilidades conocidas"
else
    echo "  [AVISO] pip-audit no instalado; re-audita antes de usar la capa"
fi

echo
echo "Capa StrictDoc lista. Siguiente paso:"
echo "  python3 scripts/strictdoc_export.py            # exporta a .docs/.storage/strictdoc-html/"
