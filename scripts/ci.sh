#!/usr/bin/env bash
# REQ-009: pipeline de verificacion local, sin proveedores (ni GitHub ni
# GitLab): exporta HEAD a un directorio limpio y verifica alli, como haria
# un CI remoto con un clon fresco. Uso: bash scripts/ci.sh
set -u
cd "$(dirname "$0")/.." || exit 1

fail() {
    echo "[CI ERROR] $1" >&2
    exit 1
}

command -v git >/dev/null 2>&1 || fail "git no disponible"
command -v python3 >/dev/null 2>&1 || fail "python3 no disponible"

PENDIENTES="$(git status --porcelain)"
if [ -n "$PENDIENTES" ]; then
    echo "[CI] AVISO: hay cambios sin commitear; la copia limpia sale de HEAD y NO los incluye:"
    echo "$PENDIENTES" | sed 's/^/       /'
fi

EXPORT_DIR="$(mktemp -d /tmp/better-project-ci-XXXXXX)" || fail "no se pudo crear directorio temporal"
echo "== CI local: exportando HEAD a $EXPORT_DIR =="
git archive HEAD | tar -x -C "$EXPORT_DIR" || fail "git archive fallo"

cd "$EXPORT_DIR" || fail "no se pudo entrar en la copia"
git init -q || fail "git init fallo"
git config user.email dummy@example.com
git config user.name "ci local"
git add -A || fail "git add fallo"
git commit -qm "ci export" --no-verify || fail "commit bootstrap fallo"
cp scripts/hooks/pre-commit .git/hooks/pre-commit || fail "no se pudo instalar el hook"

echo "== CI local: sintaxis python =="
python3 -m py_compile scripts/doc_validator.py scripts/index_knowledge.py \
    scripts/lessons_extractor.py scripts/mcp_server.py scripts/tui.py \
    || fail "py_compile fallo"

echo "== CI local: sintaxis bash =="
for s in scripts/*.sh scripts/hooks/pre-commit; do
    bash -n "$s" || fail "sintaxis bash rota en $s"
done
echo "  [OK] bash -n en todos los scripts"

echo "== CI local: suite de tests =="
BETTER_TEST_INTEGRACION=1 python3 -m unittest discover -s tests -q || fail "suite de tests en rojo"

echo "== CI local: verificacion completa =="
BETTER_TEST_INTEGRACION=1 bash scripts/verificar-proyecto.sh --pre-commit \
    || fail "verificar-proyecto.sh en rojo"

echo
echo "CI local VERDE. Copia limpia conservada en: $EXPORT_DIR"
echo "(borrala manualmente cuando quieras; no se auto-elimina, P0.3)"
