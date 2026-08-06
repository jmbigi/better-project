#!/usr/bin/env bash
# Verificación de coherencia del proyecto better-ai (lección: revisión cruzada
# como paso previo a cada commit). Uso: bash scripts/verificar-proyecto.sh
set -u
cd "$(dirname "$0")/.." || exit 1

PASS=0
FAIL=0

check() {
    local desc="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        echo "  [OK] $desc"
        PASS=$((PASS + 1))
    else
        echo "  [FALLO] $desc"
        FAIL=$((FAIL + 1))
    fi
}

echo "== 1. Reglas =="
check "12 reglas P0 definidas en AGENTS.md" bash -c "test \$(grep -cE '^### P0' AGENTS.md) -eq 12"
check "18 reglas P1 definidas en AGENTS.md" bash -c "test \$(grep -cE '^### P1' AGENTS.md) -eq 18"
check "IDs identicos en REGLAS-COMPLETAS" bash -c "diff <(grep -oE '^### P[0-2]\\.[0-9]+' AGENTS.md | sort -V) <(grep -oE '^### P[0-2]\\.[0-9]+' docs/REGLAS-COMPLETAS.md | sort -V)"
check "titulos de reglas identicos en REGLAS-COMPLETAS" bash -c "diff <(grep -E '^### P0|^### P1' AGENTS.md) <(grep -E '^### P0|^### P1' docs/REGLAS-COMPLETAS.md)"
check "referencias a rutas docs/ y scripts/ existen" python3 -c "
import re, os
files = ['AGENTS.md', 'README.md', 'CHECKLIST.md', 'docs/REGLAS-COMPLETAS.md', 'docs/PRUEBAS.md']
rutas = set()
for f in files:
    for m in re.findall(r'(?:docs/|scripts/)[A-Za-z0-9_./-]+\.(?:md|sh)', open(f).read()):
        rutas.add(m)
faltan = [r for r in sorted(rutas) if not os.path.exists(r)]
assert not faltan, 'referencias rotas: ' + str(faltan)
"
check "ningun .env versionado en git" bash -c "test -z \"\$(git ls-files | grep -E '\\.env(\$|\\.)' | grep -v '\\.env\\.example')\""
check "32 limitaciones en REGLAS-COMPLETAS" bash -c "test \$(grep -cE '^\\| \\*\\*' docs/REGLAS-COMPLETAS.md) -eq 32"
check "3 pilares documentados en README" bash -c "test \"\$(grep -cE '^## Pilar' README.md)\" -eq 3"
check "IDs citados en CHECKLIST existen en AGENTS.md" bash -c "test -z \"\$(comm -23 <(grep -oE 'P[0-2]\\.[0-9]+' CHECKLIST.md | sort -u) <(grep -oE 'P[0-2]\\.[0-9]+' AGENTS.md | sort -u))\""
check "IDs citados en README existen en AGENTS.md" bash -c "test -z \"\$(comm -23 <(grep -oE 'P[0-2]\\.[0-9]+' README.md | sort -u) <(grep -oE 'P[0-2]\\.[0-9]+' AGENTS.md | sort -u))\""
check "numeracion secuencial de pruebas en PRUEBAS" python3 -c "
import re
nums = [int(m) for m in re.findall(r'^\\| (\\d+) \\|', open('docs/PRUEBAS.md').read(), re.M)]
assert nums == list(range(1, len(nums) + 1)), 'pruebas no secuenciales'
"
check "pruebas citadas en LECCIONES existen en PRUEBAS" python3 -c "
import re
citadas = set(int(m) for m in re.findall(r'pruebas? (\\d+)', open('docs/LECCIONES-APRENDIDAS.md').read()))
existentes = set(int(m) for m in re.findall(r'^\\| (\\d+) \\|', open('docs/PRUEBAS.md').read(), re.M))
assert citadas <= existentes, 'lecciones citan pruebas inexistentes: ' + str(citadas - existentes)
"

echo "== 2. Config =="
check "opencode.json es JSON valido" python3 -c "import json; json.load(open('opencode.json'))"
check "245 patrones de permisos bash" python3 -c "
import json
b = json.load(open('opencode.json'))['permission']['bash']
assert len(b) == 245, len(b)
assert sum(1 for v in b.values() if v == 'deny') == 159
assert sum(1 for v in b.values() if v == 'ask') == 85
"
check "edit/read bloquean claves y credenciales" python3 -c "
import json
p = json.load(open('opencode.json'))['permission']
# deny: patrones de claves y credenciales (listados para el scan de seguridad)
for sec in ('edit', 'read'):
    for pat in ('~/.ssh/*', '*.ssh/*', '~/.aws/*', '*.aws/*', '*.pem', '*id_rsa*', '*id_ed25519*', '*credentials*'):  # deny: patrones
        assert p[sec].get(pat) == 'deny', (sec, pat)
"
check "enabled_providers restringe a opencode y opencode-go" python3 -c "
import json
c = json.load(open('opencode.json'))
assert c.get('enabled_providers') == ['opencode', 'opencode-go'], c.get('enabled_providers')
"
check "conteos de patrones en README coherentes con la config" python3 -c "
import json, re
b = json.load(open('opencode.json'))['permission']['bash']
r = open('README.md').read()
total, deny, ask = len(b), sum(1 for v in b.values() if v == 'deny'), sum(1 for v in b.values() if v == 'ask')
assert f'{total} patrones' in r, 'README sin el total de patrones'
assert f'{deny} \`deny\`' in r, 'README sin el conteo de deny'
assert f'{ask} \`ask\`' in r, 'README sin el conteo de ask'
"
check "edit/read bloquean .env y permiten .env.example" python3 -c "
import json
p = json.load(open('opencode.json'))['permission']
assert p['edit'].get('*.env') == 'deny'
assert p['edit'].get('*.env.*') == 'deny'
assert p['edit'].get('*.env.example') == 'allow'
assert p['read'].get('*.env') == 'deny'
assert p['read'].get('*.env.*') == 'deny'
assert p['read'].get('*.env.example') == 'allow'
"
check "deny despues de ask en familias criticas" python3 -c "
import json
k = list(json.load(open('opencode.json'))['permission']['bash'])
pares = [
    ('rm *', 'rm -rf *'), ('rm *', 'rm -r *'), ('rm *', 'rm -f *'),
    ('git reset *', 'git reset --hard*'),
    ('git push *', 'git push --force*'),
    ('mv *', 'mv --force*'), ('mv *', 'mv -f *'),
    ('rsync *', 'rsync --delete*'),
    ('docker compose down*', 'docker compose down -v*'),
    ('pip install *', 'pip install --user *'),
    ('psql -c *', 'psql * *DROP*'), ('psql -c *', 'psql * *TRUNCATE*'),
    ('psql -c *', 'psql * *DELETE*'), ('psql -c *', 'psql * *ALTER*'),
    ('mysql -e *', 'mysql * *DROP*'), ('mysql -e *', 'mysql * *TRUNCATE*'),
    ('mysql -e *', 'mysql * *DELETE*'), ('mysql -e *', 'mysql * *ALTER*'),
    ('sqlite3 *', 'sqlite3 * *DROP*'), ('sqlite3 *', 'sqlite3 * *TRUNCATE*'),
    ('sqlite3 *', 'sqlite3 * *DELETE*'), ('sqlite3 *', 'sqlite3 * *ALTER*'),
    ('redis-cli *', 'redis-cli FLUSHALL*'),
    ('redis-cli *', 'redis-cli * FLUSHALL*'),
    ('redis-cli *', 'redis-cli * *DEL*'),
]
for ask, deny in pares:
    assert ask in k, 'falta ask: ' + ask
    assert deny in k, 'falta deny: ' + deny
    assert k.index(ask) < k.index(deny), 'deny antes que ask: ' + ask + ' / ' + deny
"

echo "== 3. Seguridad (P0.9/P0.10) =="
check "sin IPs, claves o rutas .ssh en archivos" bash -c "! grep -rnE --exclude-dir=node_modules '(id_rsa|id_ed25519|\\.ssh/|known_hosts|([0-9]{1,3}\\.){3}[0-9]{1,3})' --include='*.md' --include='*.json' --include='*.sh' . | grep -v '\\.git/' | grep -qvE '(deny|patrones|claves SSH|no leas|comitees|dummy|BLOQUEADO)'"
check "sin emails personales en archivos" bash -c "! grep -rnE --exclude-dir=node_modules '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}' --include='*.md' --include='*.json' --include='*.sh' . | grep -v '\\.git/' | grep -qvE '(youremail@example|creativecommons)'"
check "sin formatos de claves API en archivos" bash -c "! grep -rnE --exclude-dir=node_modules '(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|xox[baprs]-[0-9A-Za-z-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)' --include='*.md' --include='*.json' --include='*.sh' . | grep -v '\\.git/'"
check "sin eval/exec en scripts" bash -c "! grep -rnE '\\b(eval|exec)\\b' scripts/ | grep -v 'check \"'"
check "agentes de solo lectura con edit deny" bash -c "for a in security-auditor code-reviewer; do grep -q 'edit: deny' .opencode/agents/\$a.md && grep -q 'mode: subagent' .opencode/agents/\$a.md || exit 1; done"

echo "== 4. Repositorio =="
check "hook pre-commit instalado identico al script" bash -c "cmp -s scripts/hooks/pre-commit .git/hooks/pre-commit"
check "sin objetos huerfanos en git (fsck)" bash -c "test -z \"\$(git fsck --unreachable 2>&1 | grep -v 'unborn branch')\""
if [ "${1:-}" = "--pre-commit" ]; then
    echo "  [SKIP] comprobaciones de repositorio (modo pre-commit: los archivos staged son el cambio)"
else
    check "arbol de trabajo limpio" bash -c "test -z \"\$(git status --porcelain)\""
    check "rama main sincronizada con origin" bash -c "test -z \"\$(git status --porcelain --branch | grep -E 'adelant|ahead|behind|adelanta')\""
    check "HEAD remoto apunta a main" bash -c "test \"\$(git ls-remote origin HEAD | cut -f1)\" = \"\$(git ls-remote origin refs/heads/main | cut -f1)\""
fi

echo "== 5. Ecosistema (.docs + scripts) =="
check "sintaxis python de los scripts" bash -c "python3 -m py_compile scripts/doc_validator.py scripts/index_knowledge.py scripts/lessons_extractor.py scripts/mcp_server.py scripts/tui.py"
check "trazabilidad REQ valida (doc_validator --strict)" bash -c "python3 scripts/doc_validator.py --strict"
check "lecciones validas (lessons_extractor --check)" bash -c "python3 scripts/lessons_extractor.py --check"
check "indice de conocimiento generable" bash -c "python3 scripts/index_knowledge.py && python3 scripts/index_knowledge.py --check"
check "suite de tests del ecosistema" bash -c "python3 -m unittest discover -s tests -q"
check "demo valida con --root" bash -c "python3 scripts/doc_validator.py --root demo"

echo
echo "Resultado: $PASS OK, $FAIL FALLOS"
[ "$FAIL" -eq 0 ] || exit 1
