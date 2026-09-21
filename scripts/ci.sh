#!/usr/bin/env bash
# REQ-009: pipeline de verificacion local, sin proveedores (ni GitHub ni
# GitLab): exporta HEAD a un directorio limpio y verifica alli, como haria
# un CI remoto con un clon fresco. Uso: bash scripts/ci.sh
# REQ-024: KPIs dashboard en CI
set -u
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)" || exit 1
cd "$REPO_ROOT" || exit 1

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
# Copiar mypy.ini para type checking
cp "$REPO_ROOT/mypy.ini" . 2>/dev/null || true
for hook in pre-commit commit-msg; do
    cp "scripts/hooks/$hook" ".git/hooks/$hook" || fail "no se pudo instalar el hook $hook"
    chmod +x ".git/hooks/$hook" || fail "no se pudo marcar ejecutable $hook"
done

echo "== CI local: sintaxis python =="
for f in scripts/*.py; do
    python3 -m py_compile "$f" || fail "py_compile fallo en $f"
done
echo "  [OK] py_compile en todos los scripts"

echo "== CI local: sintaxis bash =="
for s in scripts/*.sh scripts/hooks/pre-commit scripts/hooks/commit-msg; do
    bash -n "$s" || fail "sintaxis bash rota en $s"
done
echo "  [OK] bash -n en todos los scripts"

echo "== CI local: suite de tests =="
BETTER_TEST_INTEGRACION=1 python3 scripts/run_tests_isolated.py || fail "suite de tests en rojo"

echo "== CI local: verificacion completa =="
BETTER_TEST_INTEGRACION=1 bash scripts/verificar-proyecto.sh --pre-commit \
    || fail "verificar-proyecto.sh en rojo"

echo "== CI local: type checking (mypy strict on tests) =="
mypy --config-file mypy.ini tests/ || fail "mypy --strict en tests en rojo"

echo "== CI local: coverage gate 90% =="
python3 -m pytest --cov=scripts --cov-fail-under=90 -q || fail "coverage bajo 90%"

echo "== CI local: verificacion hooks git (hash parity) =="
for hook in pre-commit commit-msg; do
    diff -q "scripts/hooks/$hook" ".git/hooks/$hook" >/dev/null 2>&1 || fail "hook $hook desincronizado (hash mismatch)"
done
echo "  [OK] hooks sincronizados"

echo "== CI local: mutacion multi-modulo (REQ-015) =="
python3 scripts/mutation_check.py --batch --strict --umbral 0.8 \
    || fail "mutation_check --batch por debajo del umbral 0.8"

if [ "${AUDIT:-0}" = "1" ]; then
    echo "== CI local: advisories con severidad (AUDIT=1, REQ-020) =="
    python3 scripts/audit_advisories.py --requirements requirements-optional.lock \
        || echo "  [AVISO] auditoria no completada (pip-audit/red); no bloquea el CI"
fi

echo
echo "CI local VERDE. Copia limpia conservada en: $EXPORT_DIR"
echo "(borrala manualmente cuando quieras; no se auto-elimina, P0.3)"
