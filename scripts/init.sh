#!/usr/bin/env bash
# better-project init — Inicializa el framework en un proyecto existente.
# Uso: bash scripts/init.sh [--yes] [--root <dir>]
# Idempotente: se puede ejecutar multiples veces sin efectos adversos.

set -euo pipefail

# Configuracion
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_ROOT="${REPO_ROOT}"
AUTO_YES=false

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --yes) AUTO_YES=true ;;
        --root) TARGET_ROOT="$2"; shift ;;
        *) echo "Uso: $0 [--yes] [--root <dir>]"; exit 1 ;;
    esac
    shift
done

cd "$TARGET_ROOT" || { echo "Error: no existe $TARGET_ROOT"; exit 1; }

confirm() {
    local msg="$1"
    if [ "$AUTO_YES" = true ]; then
        return 0
    fi
    read -rp "$msg [s/N] " resp
    [[ "$resp" =~ ^[Ss]$ ]]
}

# Detectar stack del proyecto
detect_stack() {
    local stacks=()
    [ -f "pyproject.toml" ] || [ -f "requirements.txt" ] || [ -f "setup.py" ] && stacks+=("python")
    [ -f "package.json" ] && stacks+=("javascript")
    [ -f "go.mod" ] && stacks+=("go")
    [ -f "Cargo.toml" ] && stacks+=("rust")
    [ -f "pom.xml" ] || [ -f "build.gradle" ] && stacks+=("java")
    [ -f "composer.json" ] && stacks+=("php")
    [ -f "mix.exs" ] && stacks+=("elixir")
    echo "${stacks[*]}"
}

# Generar patrones bash segun stack
generate_bash_patterns() {
    local stacks="$1"
    cat <<'EOF'
  "permission": {
    "bash": {
      "*": "allow",
      "rm *": "ask",
      "sudo *": "ask",
      "apt *": "ask",
      "apt-get *": "ask",
      "dnf *": "ask",
      "yum *": "ask",
      "pacman *": "ask",
      "snap *": "ask",
      "flatpak *": "ask",
      "npm uninstall *": "ask",
      "npm update *": "ask",
      "npm -g *": "ask",
      "npx * -g *": "ask",
      "yarn global *": "ask",
      "pip install *": "ask",
      "pip uninstall *": "ask",
      "pipx *": "ask",
      "gem install *": "ask",
      "cargo install *": "ask",
      "go install *": "ask",
      "brew install *": "ask",
      "docker compose down*": "ask",
      "docker rm -f*": "ask",
      "docker rmi *": "ask",
      "docker volume rm *": "ask",
      "docker system prune*": "ask",
      "docker stop*": "ask",
      "docker exec*": "ask",
      "kubectl delete*": "ask",
      "kubectl cordon*": "ask",
      "kubectl rollout undo*": "ask",
      "kubectl scale*": "ask",
      "helm uninstall*": "ask",
      "helm delete*": "ask",
      "terraform apply*": "ask",
      "terraform force-unlock*": "ask",
      "ansible-playbook *": "ask",
      "git commit *": "ask",
      "git push *": "ask",
      "git merge *": "ask",
      "git reset --soft*": "ask",
      "git reset --mixed*": "ask",
      "git reset *": "ask",
      "git stash drop*": "ask",
      "git rebase *": "ask",
      "git revert *": "ask",
      "git gc *": "ask",
      "git -C * rebase *": "ask",
      "git -C * gc *": "ask",
      "createdb *": "ask",
      "psql -c *": "ask",
      "mysql -e *": "ask",
      "sqlite3 *": "ask",
      "mongosh *": "ask",
      "redis-cli *": "ask",
      "prisma migrate dev*": "ask",
      "prisma db push*": "ask",
      "npx prisma migrate dev*": "ask",
      "npx prisma db push*": "ask",
      "alembic downgrade base*": "ask",
      "chmod -R *": "ask",
      "chown -R *": "ask",
      "pkill *": "ask",
      "kill -9 *": "ask",
      "killall *": "ask",
      "iptables *": "ask",
      "ufw *": "ask",
      "crontab *": "ask",
      "ssh-copy-id *": "ask",
      "mv *": "ask",
      "rsync *": "ask",
      "unzip *": "ask",
      "tar -x*": "ask",
      "tar x*": "ask",
      "pnpm uninstall *": "ask",
      "pnpm update *": "ask",
      "pnpm -g *": "ask",
      "bun uninstall *": "ask",
      "bun update *": "ask",
      "bun add -g *": "ask",
      "uv pip install *": "ask",
      "uv pip uninstall *": "ask",
      "uv tool install *": "ask",
      "conda install *": "ask",
      "conda remove *": "ask",
      "rm -rf *": "deny",
      "rm -r *": "deny",
      "rm -f *": "deny",
      "*/rm -rf *": "deny",
      "*/rm -r *": "deny",
      "*/rm -f *": "deny",
      "sh -c 'rm -rf *'": "deny",
      "sh -c \"rm -rf *\"": "deny",
      "sh -c 'rm -r *'": "deny",
      "sh -c \"rm -r *\"": "deny",
      "sh -c 'rm -f *'": "deny",
      "sh -c \"rm -f *\"": "deny",
      "bash -c 'rm -rf *'": "deny",
      "bash -c \"rm -rf *\"": "deny",
      "bash -c 'rm -r *'": "deny",
      "bash -c \"rm -r *\"": "deny",
      "bash -c 'rm -f *'": "deny",
      "bash -c \"rm -f *\"": "deny",
      "pip install --user *": "deny",
      "*/pip install --user *": "deny",
      "docker compose down -v*": "deny",
      "*/docker compose down -v*": "deny",
      "docker kill*": "deny",
      "*/docker kill*": "deny",
      "kubectl drain*": "deny",
      "terraform destroy*": "deny",
      "terraform state rm*": "deny",
      "git reset --hard*": "deny",
      "git clean *": "deny",
      "git checkout -- *": "deny",
      "git checkout .*": "deny",
      "git stash clear*": "deny",
      "git branch -D *": "deny",
      "git push --force*": "deny",
      "*/git reset --hard*": "deny",
      "*/git push --force*": "deny",
      "sh -c 'git reset --hard*'": "deny",
      "sh -c \"git reset --hard*\"": "deny",
      "sh -c 'git push --force*'": "deny",
      "sh -c \"git push --force*\"": "deny",
      "bash -c 'git reset --hard*'": "deny",
      "bash -c \"git reset --hard*\"": "deny",
      "bash -c 'git push --force*'": "deny",
      "bash -c \"git push --force*\"": "deny",
      "sh -c 'docker compose down -v'": "deny",
      "sh -c \"docker compose down -v\"": "deny",
      "bash -c 'docker compose down -v'": "deny",
      "bash -c \"docker compose down -v\"": "deny",
      "sh -c 'redis-cli FLUSHALL'": "deny",
      "sh -c \"redis-cli FLUSHALL\"": "deny",
      "bash -c 'redis-cli FLUSHALL'": "deny",
      "bash -c \"redis-cli FLUSHALL\"": "deny",
      "sh -c 'redis-cli FLUSHDB'": "deny",
      "sh -c \"redis-cli FLUSHDB\"": "deny",
      "bash -c 'redis-cli FLUSHDB'": "deny",
      "bash -c \"redis-cli FLUSHDB\"": "deny",
      "sh -c 'eval $(curl*'": "deny",
      "sh -c \"eval $(curl*'": "deny",
      "bash -c 'eval $(curl*'": "deny",
      "bash -c \"eval $(curl*'": "deny",
      "git filter-branch*": "deny",
      "git -C * filter-branch*": "deny",
      "git -C * reset --hard*": "deny",
      "git -C * clean *": "deny",
      "git -C * checkout -- *": "deny",
      "git -C * push --force*": "deny",
      "git -C * branch -D *": "deny",
      "git --git-dir * filter-branch*": "deny",
      "dropdb *": "deny",
      "psql * *DROP*": "deny",
      "psql * *TRUNCATE*": "deny",
      "psql * *DELETE*": "deny",
      "psql * *ALTER*": "deny",
      "*/psql *DROP*": "deny",
      "*/psql *TRUNCATE*": "deny",
      "*/psql *DELETE*": "deny",
      "*/psql *ALTER*": "deny",
      "mysql * *DROP*": "deny",
      "mysql * *TRUNCATE*": "deny",
      "mysql * *DELETE*": "deny",
      "mysql * *ALTER*": "deny",
      "*/mysql *DROP*": "deny",
      "*/mysql *TRUNCATE*": "deny",
      "*/mysql *DELETE*": "deny",
      "*/mysql *ALTER*": "deny",
      "sqlite3 * *DROP*": "deny",
      "sqlite3 * *TRUNCATE*": "deny",
      "sqlite3 * *DELETE*": "deny",
      "sqlite3 * *ALTER*": "deny",
      "*/sqlite3 *DROP*": "deny",
      "*/sqlite3 *TRUNCATE*": "deny",
      "*/sqlite3 *DELETE*": "deny",
      "*/sqlite3 *ALTER*": "deny",
      "migrate reset*": "deny",
      "prisma migrate reset*": "deny",
      "npx prisma migrate reset*": "deny",
      "rails db:reset*": "deny",
      "rails db:drop*": "deny",
      "rails db:migrate:reset*": "deny",
      "systemctl *": "deny",
      "service *": "deny",
      "initctl *": "deny",
      "reboot*": "deny",
      "shutdown*": "deny",
      "poweroff*": "deny",
      "mkfs*": "deny",
      "fdisk*": "deny",
      "parted*": "deny",
      "sfdisk*": "deny",
      "mkswap*": "deny",
      "wipefs*": "deny",
      "shred *": "deny",
      "truncate -s 0*": "deny",
      "dd *": "deny",
      "chmod 777*": "deny",
      "chmod 666*": "deny",
      "mv --force*": "deny",
      "mv -f *": "deny",
      "cp -f *": "deny",
      "cp --force*": "deny",
      "rsync --delete*": "deny",
      "curl * | bash*": "deny",
      "curl * | sh*": "deny",
      "wget * | bash*": "deny",
      "wget * | sh*": "deny",
      "eval *": "deny",
      "*/eval $(curl*"": "deny",
      "redis-cli * FLUSHALL*": "deny",
      "redis-cli * FLUSHDB*": "deny",
      "redis-cli FLUSHALL*": "deny",
      "redis-cli FLUSHDB*": "deny",
      "redis-cli * *DEL*": "deny",
      "redis-cli *DEL*": "deny",
      "*/redis-cli FLUSHALL*": "deny",
      "*/redis-cli FLUSHDB*": "deny",
      "cat *.env*": "deny",
      "cat * *.env*": "deny",
      "less *.env*": "deny",
      "less * *.env*": "deny",
      "more *.env*": "deny",
      "more * *.env*": "deny",
      "head *.env*": "deny",
      "head * *.env*": "deny",
      "tail *.env*": "deny",
      "tail * *.env*": "deny",
      "grep * *.env*": "deny",
      "* * > *.env*": "deny",
      "* * >> *.env*": "deny",
      "cat *.ssh*": "deny",
      "cat * *.ssh*": "deny",
      "less *.ssh*": "deny",
      "less * *.ssh*": "deny",
      "more *.ssh*": "deny",
      "more * *.ssh*": "deny",
      "head *.ssh*": "deny",
      "head * *.ssh*": "deny",
      "tail *.ssh*": "deny",
      "tail * *.ssh*": "deny",
      "grep * *.ssh*": "deny",
      "cat *.aws*": "deny",
      "cat * *.aws*": "deny",
      "less *.aws*": "deny",
      "less * *.aws*": "deny",
      "more *.aws*": "deny",
      "more * *.aws*": "deny",
      "head *.aws*": "deny",
      "head * *.aws*": "deny",
      "tail *.aws*": "deny",
      "tail * *.aws*": "deny",
      "grep * *.aws*": "deny",
      "cat *id_rsa*": "deny",
      "cat * *id_rsa*": "deny",
      "less *id_rsa*": "deny",
      "less * *id_rsa*": "deny",
      "more *id_rsa*": "deny",
      "more * *id_rsa*": "deny",
      "head *id_rsa*": "deny",
      "head * *id_rsa*": "deny",
      "tail *id_rsa*": "deny",
      "tail * *id_rsa*": "deny",
      "grep * *id_rsa*": "deny",
      "cat *id_ed25519*": "deny",
      "cat * *id_ed25519*": "deny",
      "less *id_ed25519*": "deny",
      "less * *id_ed25519*": "deny",
      "more *id_ed25519*": "deny",
      "more * *id_ed25519*": "deny",
      "head *id_ed25519*": "deny",
      "head * *id_ed25519*": "deny",
      "tail *id_ed25519*": "deny",
      "tail * *id_ed25519*": "deny",
      "grep * *id_ed25519*": "deny",
      "cat *id_ecdsa*": "deny",
      "cat * *id_ecdsa*": "deny",
      "less *id_ecdsa*": "deny",
      "less * *id_ecdsa*": "deny",
      "more *id_ecdsa*": "deny",
      "more * *id_ecdsa*": "deny",
      "head *id_ecdsa*": "deny",
      "head * *id_ecdsa*": "deny",
      "tail *id_ecdsa*": "deny",
      "tail * *id_ecdsa*": "deny",
      "grep * *id_ecdsa*": "deny",
      "cat *id_dsa*": "deny",
      "cat * *id_dsa*": "deny",
      "less *id_dsa*": "deny",
      "less * *id_dsa*": "deny",
      "more *id_dsa*": "deny",
      "more * *id_dsa*": "deny",
      "head *id_dsa*": "deny",
      "head * *id_dsa*": "deny",
      "tail *id_dsa*": "deny",
      "tail * *id_dsa*": "deny",
      "grep * *id_dsa*": "deny",
      "* * > *.ssh*": "deny",
      "* * >> *.ssh*": "deny",
      "* * > *.aws*": "deny",
      "* * >> *.aws*": "deny"
EOF

    # Stack-specific patterns
    if [[ "$stacks" == *"python"* ]]; then
        cat <<'EOF'
      "pip install *": "ask",
      "pip uninstall *": "ask",
      "pipx *": "ask",
      "uv pip install *": "ask",
      "uv pip uninstall *": "ask",
      "uv tool install *": "ask",
      "conda install *": "ask",
      "conda remove *": "ask",
EOF
    fi
    if [[ "$stacks" == *"javascript"* ]]; then
        cat <<'EOF'
      "npm install *": "ask",
      "npm uninstall *": "ask",
      "npm update *": "ask",
      "npm -g *": "ask",
      "npx *": "ask",
      "yarn *": "ask",
      "pnpm *": "ask",
      "bun *": "ask",
EOF
    fi
    if [[ "$stacks" == *"go"* ]]; then
        cat <<'EOF'
      "go install *": "ask",
      "go get *": "ask",
      "go mod *": "ask",
EOF
    fi
    if [[ "$stacks" == *"rust"* ]]; then
        cat <<'EOF'
      "cargo install *": "ask",
      "cargo update *": "ask",
      "cargo add *": "ask",
EOF
    fi
    if [[ "$stacks" == *"java"* ]]; then
        cat <<'EOF'
      "mvn *": "ask",
      "gradle *": "ask",
EOF
    fi

    cat <<'EOF'
    },
    "edit": {
      "*": "allow",
      "*.env": "deny",
      "*.env.*": "deny",
      "*.env.example": "allow",
      "~/.ssh/*": "deny",
      "*.ssh/*": "deny",
      "~/.aws/*": "deny",
      "*.aws/*": "deny",
      "*.pem": "deny",
      "*id_rsa*": "deny",
      "*id_ed25519*": "deny",
      "*id_ecdsa*": "deny",
      "*id_dsa*": "deny",
      "*credentials*": "deny"
    },
    "read": {
      "*": "allow",
      "*.env": "deny",
      "*.env.*": "deny",
      "*.env.example": "allow",
      "~/.ssh/*": "deny",
      "*.ssh/*": "deny",
      "~/.aws/*": "deny",
      "*.aws/*": "deny",
      "*.pem": "deny",
      "*id_rsa*": "deny",
      "*id_ed25519*": "deny",
      "*id_ecdsa*": "deny",
      "*id_dsa*": "deny",
      "*credentials*": "deny"
    },
    "webfetch": "allow"
  }
EOF
}

# Main
echo "=== better-project init ==="
echo "Directorio objetivo: $TARGET_ROOT"

STACKS=$(detect_stack)
if [ -z "$STACKS" ]; then
    STACKS="generic"
    echo "Stack detectado: (ninguno especifico, usando generico)"
else
    echo "Stacks detectados: $STACKS"
fi

if ! confirm "Instalar framework better-project aqui?"; then
    echo "Cancelado."
    exit 0
fi

# 1. Copiar AGENTS.md
if [ -f "$REPO_ROOT/AGENTS.md" ]; then
    cp "$REPO_ROOT/AGENTS.md" "$TARGET_ROOT/AGENTS.md"
    echo "[OK] AGENTS.md copiado"
else
    echo "[WARN] AGENTS.md no encontrado en $REPO_ROOT"
fi

# 2. Generar opencode.json adaptado
cat > "$TARGET_ROOT/opencode.json" <<EOF
{
  "\$schema": "https://opencode.ai/config.json",
  "experimental": {
    "policies": [
      { "effect": "deny", "action": "provider.use", "resource": "*" },
      { "effect": "allow", "action": "provider.use", "resource": "opencode" },
      { "effect": "allow", "action": "provider.use", "resource": "opencode-go" },
      { "effect": "allow", "action": "provider.use", "resource": "kilo" },
      { "effect": "allow", "action": "provider.use", "resource": "deepseek" }
    ]
  },
  "mcp": {
    "context7": {
      "type": "remote",
      "url": "https://mcp.context7.com/mcp",
      "enabled": true
    },
    "gh_grep": {
      "type": "remote",
      "url": "https://mcp.grep.app",
      "enabled": true
    },
    "sentry": {
      "type": "remote",
      "url": "https://mcp.sentry.dev/mcp",
      "enabled": true,
      "oauth": {}
    },
    "better-project": {
      "type": "local",
      "command": ["python3", "scripts/mcp_server.py"],
      "enabled": false
    }
  },
  "agent": {
    "build": {
      "mode": "primary",
      "temperature": 0.3,
      "top_p": 1.0,
      "steps": 50
    },
    "plan": {
      "mode": "primary",
      "temperature": 0.1,
      "top_p": 1.0,
      "steps": 30
    },
    "audit": {
      "mode": "primary",
      "temperature": 0.0,
      "top_p": 1.0,
      "steps": 20
    }
  },
$(generate_bash_patterns "$STACKS")
}
EOF
echo "[OK] opencode.json generado (adaptado a: $STACKS)"

# 3. Copiar scripts de verificacion
mkdir -p "$TARGET_ROOT/scripts"
cp "$REPO_ROOT/scripts/verificar-proyecto.sh" "$TARGET_ROOT/scripts/verificar-proyecto.sh"
chmod +x "$TARGET_ROOT/scripts/verificar-proyecto.sh"
echo "[OK] verificar-proyecto.sh copiado"

# 4. Instalar hooks git
mkdir -p "$TARGET_ROOT/.git/hooks"
if [ -f "$REPO_ROOT/scripts/hooks/pre-commit" ]; then
    cp "$REPO_ROOT/scripts/hooks/pre-commit" "$TARGET_ROOT/.git/hooks/pre-commit"
    chmod +x "$TARGET_ROOT/.git/hooks/pre-commit"
    echo "[OK] Hook pre-commit instalado"
fi
if [ -f "$REPO_ROOT/scripts/hooks/commit-msg" ]; then
    cp "$REPO_ROOT/scripts/hooks/commit-msg" "$TARGET_ROOT/.git/hooks/commit-msg"
    chmod +x "$TARGET_ROOT/.git/hooks/commit-msg"
    echo "[OK] Hook commit-msg instalado"
fi

# 5. Crear estructura .docs/
mkdir -p "$TARGET_ROOT/.docs/requirements"
mkdir -p "$TARGET_ROOT/.docs/knowledge"
mkdir -p "$TARGET_ROOT/.docs/lessons"

# 6. Crear REQ-001 plantilla si no existe
REQ_FILE="$TARGET_ROOT/.docs/requirements/REQ-001.md"
if [ ! -f "$REQ_FILE" ]; then
    cat > "$REQ_FILE" <<'EOF'
---
id: REQ-001
titulo: Requisito principal del proyecto
estado: Draft
prioridad: Alta
version: 1.0
fecha_creacion: $(date +%Y-%m-%d)
---
# REQ-001: Requisito principal del proyecto

Descripcion del requisito principal. El codigo que lo implemente debe llevar
el comentario \`# REQ-001\` (o \`// REQ-001\`) en la funcion/clase principal.
EOF
    # Fix date
    sed -i "s/\$(date +%Y-%m-%d)/$(date +%Y-%m-%d)/" "$REQ_FILE"
    echo "[OK] REQ-001.md plantilla creado"
else
    echo "[SKIP] REQ-001.md ya existe"
fi

# 7. Crear CHECKLIST.md si no existe
if [ ! -f "$TARGET_ROOT/CHECKLIST.md" ] && [ -f "$REPO_ROOT/CHECKLIST.md" ]; then
    cp "$REPO_ROOT/CHECKLIST.md" "$TARGET_ROOT/CHECKLIST.md"
    echo "[OK] CHECKLIST.md copiado"
fi

# 8. Crear .gitignore entradas basicas
GITIGNORE="$TARGET_ROOT/.gitignore"
touch "$GITIGNORE"
for pattern in ".docs/.storage/" "lessons_context.txt" "*.pyc" "__pycache__/" ".venv/" "venv/" "node_modules/" ".env" "*.env.*" "!*.env.example"; do
    if ! grep -qxF "$pattern" "$GITIGNORE"; then
        echo "$pattern" >> "$GITIGNORE"
    fi
done
echo "[OK] .gitignore actualizado"

echo ""
echo "=== Inicializacion completada ==="
echo ""
echo "Proximos pasos:"
echo "  1. Revisa y adapta AGENTS.md y opencode.json a tu proyecto"
echo "  2. Ejecuta: python3 scripts/verificar-proyecto.sh --lite"
echo "  3. Anade requisitos en .docs/requirements/REQ-XXX.md"
echo "  4. Ejecuta: python3 scripts/index_knowledge.py"
echo "  5. Usa opencode con el framework activo"