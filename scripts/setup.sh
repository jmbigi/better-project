#!/usr/bin/env bash
# REQ-008: onboarding del proyecto better-project.
# De la clonacion a la primera validacion exitosa. Uso:
#   bash scripts/setup.sh [--yes]
# --yes: modo no interactivo (responde "no" a las dependencias opcionales).
# Nunca instala nada global ni sin confirmacion (P0.5, P1.23).
set -u
cd "$(dirname "$0")/.." || exit 1

YES=0
[ "${1:-}" = "--yes" ] && YES=1

fail() {
    echo "[ERROR] $1" >&2
    exit 1
}

echo "== 1. Entorno =="
command -v bash >/dev/null 2>&1 || fail "bash no disponible"
command -v git >/dev/null 2>&1 || fail "git no disponible; instalalo con tu gestor de paquetes"
command -v python3 >/dev/null 2>&1 || fail "python3 no disponible; instalalo con tu gestor de paquetes"
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" \
    || fail "se requiere python3 >= 3.10 (tienes $(python3 --version 2>&1))"
echo "  [OK] bash, git y python3 >= 3.10"

echo "== 2. Hook de pre-commit =="
HOOK=.git/hooks/pre-commit
if [ ! -d .git ]; then
    fail "no es un repositorio git (ejecuta desde la raiz del clon)"
fi
if cmp -s scripts/hooks/pre-commit "$HOOK" 2>/dev/null; then
    echo "  [OK] hook ya instalado e identico (idempotente: sin cambios)"
else
    cp scripts/hooks/pre-commit "$HOOK" || fail "no se pudo instalar el hook"
    echo "  [OK] hook instalado en $HOOK"
fi

echo "== 3. Dependencias opcionales (busqueda vectorial) =="
echo "  Sin ellas el ecosistema funciona con stdlib (indice JSON TF-IDF)."
echo "  Con ellas (chromadb + sentence-transformers) la busqueda es semantica."
echo "  AVISO (P0.18, auditoria pip-audit del 2026-09-04, docs/SBOM-2026-09-04.spdx.json):"
echo "  chromadb 1.5.9 tiene 4 advisories ABIERTOS sin version de parche"
echo "  (inyeccion de codigo y autorizacion en su modo SERVIDOR). El uso local"
echo "  embebido (PersistentClient, sin servidor ni red) no expone esa superficie,"
echo "  pero la instalacion implica aceptar el riesgo por escrito."
if [ "$YES" = "1" ]; then
    RESPUESTA="n"
else
    printf "  ¿Instalar en .venv del proyecto aceptando ese riesgo? [s/N] "
    read -r RESPUESTA
fi
case "$RESPUESTA" in
    s|S|si|SI|y|Y)
        printf "  Escribe 'acepto el riesgo' para confirmar: "
        read -r CONFIRMA
        [ "$CONFIRMA" = "acepto el riesgo" ] || { echo "  [SKIP] sin confirmacion de riesgo"; RESPUESTA="n"; }
        ;;
esac
case "$RESPUESTA" in
    s|S|si|SI|y|Y)
        python3 -m venv .venv || fail "no se pudo crear .venv"
        .venv/bin/pip install --quiet -r requirements-optional.txt \
            || fail "fallo pip install; revisa la salida"
        echo "  [OK] dependencias opcionales en .venv"
        echo "  NOTA (P0.18): regenera el SBOM tras instalar y adjuntalo en docs/"
        ;;
    *)
        echo "  [SKIP] backend stdlib (TF-IDF JSON); puedes instalarlas despues"
        ;;
esac

echo "== 4. Indice de conocimiento =="
python3 scripts/index_knowledge.py || fail "fallo la indexacion"

echo "== 5. Primera validacion =="
bash scripts/verificar-proyecto.sh --pre-commit || fail "la verificacion encontro problemas; revisa los [FALLO]"

echo
echo "Setup completado. Siguiente paso sugerido: python3 scripts/tui.py"
