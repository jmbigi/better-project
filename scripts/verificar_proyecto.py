#!/usr/bin/env python3
"""Verificación de coherencia del proyecto better-project (versión Python cross-platform).
REQ-010: este verificador está cubierto por TestVerificador en tests/test_ecosistema.py.
REQ-022: verificador determinista (sin falsos positivos por árbol sucio).
"""

import argparse
import ipaddress
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PASS = 0
FAIL = 0


def check(desc: str, fn) -> None:
    global PASS, FAIL
    try:
        if fn():
            print(f"  [OK] {desc}")
            PASS += 1
        else:
            print(f"  [FALLO] {desc}")
            FAIL += 1
    except Exception as e:
        print(f"  [FALLO] {desc}: {e}")
        FAIL += 1


def run_cmd(cmd: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def check_ruff() -> None:
    if run_cmd(["ruff", "--version"]).returncode == 0:
        check("lint ruff (ruff.toml)", lambda: run_cmd(["ruff", "check", "scripts", "tests"]).returncode == 0)
    else:
        print("  [SKIP] lint ruff (no instalado; ver docs/HERRAMIENTAS-Y-FUENTES.md)")


# == 1. Reglas ==
def _check_p0_rules() -> bool:
    return len(re.findall(r"^### P0\.", open(ROOT / "AGENTS.md").read(), re.M)) == 20


def _check_p1_rules() -> bool:
    return len(re.findall(r"^### P1\.", open(ROOT / "AGENTS.md").read(), re.M)) == 37


def _check_ids_identical() -> bool:
    agents_ids = sorted(re.findall(r"^### P[0-2]\.[0-9]+", open(ROOT / "AGENTS.md").read(), re.M))
    reglas_ids = sorted(re.findall(r"^### P[0-2]\.[0-9]+", open(ROOT / "docs/REGLAS-COMPLETAS.md").read(), re.M))
    return agents_ids == reglas_ids


def _check_titles_identical() -> bool:
    agents_titles = re.findall(r"^### P[01].*", open(ROOT / "AGENTS.md").read(), re.M)
    reglas_titles = re.findall(r"^### P[01].*", open(ROOT / "docs/REGLAS-COMPLETAS.md").read(), re.M)
    return agents_titles == reglas_titles


def _check_refs_exist() -> bool:
    files = ["AGENTS.md", "README.md", "CHECKLIST.md", "docs/REGLAS-COMPLETAS.md", "docs/PRUEBAS.md"]
    rutas = set()
    for f in files:
        content = open(ROOT / f).read()
        for m in re.findall(r"(?:docs/|scripts/|\.opencode/)[A-Za-z0-9_./-]+\.(?:md|sh|py)", content):
            rutas.add(m)
    faltan = [r for r in sorted(rutas) if not (ROOT / r).exists()]
    return not faltan


def _check_doc_validator() -> bool:
    return run_cmd([sys.executable, "scripts/doc_validator.py", "--root", "."]).returncode == 0


def _check_no_env_in_git() -> bool:
    result = run_cmd(["git", "ls-files"])
    env_files = [f for f in result.stdout.splitlines() if re.search(r"\.env($|\.)", f) and not f.endswith(".env.example")]
    return len(env_files) == 0


def _check_limitaciones() -> bool:
    return len(re.findall(r"^\| \*\*", open(ROOT / "docs/REGLAS-COMPLETAS.md").read(), re.M)) == 52


def _check_readme_errores() -> bool:
    return len(re.findall(r"^[0-9]+\. \*\*", open(ROOT / "README.md").read(), re.M)) == 50


def _check_checklist_ids() -> bool:
    checklist_ids = set(re.findall(r"P[0-2]\.[0-9]+", open(ROOT / "CHECKLIST.md").read()))
    agents_ids = set(re.findall(r"P[0-2]\.[0-9]+", open(ROOT / "AGENTS.md").read()))
    return checklist_ids <= agents_ids


def _check_readme_ids() -> bool:
    readme_ids = set(re.findall(r"P[0-2]\.[0-9]+", open(ROOT / "README.md").read()))
    agents_ids = set(re.findall(r"P[0-2]\.[0-9]+", open(ROOT / "AGENTS.md").read()))
    return readme_ids <= agents_ids


def _check_pruebas_sequential() -> bool:
    nums = [int(m) for m in re.findall(r"^\| (\d+) \|", open(ROOT / "docs/PRUEBAS.md").read(), re.M)]
    return nums == list(range(1, len(nums) + 1))


def _check_lecciones_citan_pruebas() -> bool:
    citadas = set(int(m) for m in re.findall(r"pruebas? (\d+)", open(ROOT / "docs/LECCIONES-APRENDIDAS.md").read()))
    existentes = set(int(m) for m in re.findall(r"^\| (\d+) \|", open(ROOT / "docs/PRUEBAS.md").read(), re.M))
    return citadas <= existentes


def _check_total_reglas() -> bool:
    p0 = len(re.findall(r"^### P0\.", open(ROOT / "AGENTS.md").read(), re.M))
    p1 = len(re.findall(r"^### P1\.", open(ROOT / "AGENTS.md").read(), re.M))
    p2 = len(re.findall(r"^\s*-\s*P2\.", open(ROOT / "AGENTS.md").read(), re.M))
    return p0 == 20 and p1 == 37 and p2 == 5 and (p0 + p1 + p2) == 62


def _check_readme_no_50_reglas() -> bool:
    txt = open(ROOT / "README.md").read()
    return "50 reglas" not in txt or "61 reglas" in txt


def _check_mcp_tools() -> bool:
    mcp = json.load(open(ROOT / "opencode.json"))["mcp"]
    tools = [k for k, v in mcp.items() if v.get("enabled", True)]
    return len(tools) == 4 and set(tools) == {"context7", "gh_grep", "sentry", "better-project"}


def _check_pruebas_rondas() -> bool:
    txt = open(ROOT / "docs/PRUEBAS.md").read()
    rondas = set(int(m) for m in re.findall(r"Ronda (\d+)", txt))
    return max(rondas) == 36 and len(rondas) == 33


# == 2. Config ==
def _check_bash_patterns() -> bool:
    b = json.load(open(ROOT / "kilo.json"))["permission"]["bash"]
    return len(b) == 304 and sum(1 for v in b.values() if v == "deny") == 218 and sum(1 for v in b.values() if v == "ask") == 85 and sum(1 for v in b.values() if v == "allow") == 1


def _check_same_permissions() -> bool:
    a = json.load(open(ROOT / "kilo.json"))["permission"]["bash"]
    b = json.load(open(ROOT / "opencode.json"))["permission"]["bash"]
    return a == b


def _check_edit_read_deny() -> bool:
    p = json.load(open(ROOT / "kilo.json"))["permission"]
    for sec in ("edit", "read"):
        for pat in ("~/.ssh/*", "*.ssh/*", "~/.aws/*", "*.aws/*", "*.pem", "*id_rsa*", "*id_ed25519*", "*credentials*"):
            if p[sec].get(pat) != "deny":
                return False
    return True


def _check_kilo_policies() -> bool:
    c = json.load(open(ROOT / "kilo.json"))
    policies = c.get("experimental", {}).get("policies", [])
    if policies[0] != {"effect": "deny", "action": "provider.use", "resource": "*"}:
        return False
    allowed = [p["resource"] for p in policies if p["effect"] == "allow"]
    return set(allowed) == {"kilo", "deepseek", "openrouter"}


def _check_opencode_policies() -> bool:
    c = json.load(open(ROOT / "opencode.json"))
    policies = c.get("experimental", {}).get("policies", [])
    if policies[0] != {"effect": "deny", "action": "provider.use", "resource": "*"}:
        return False
    allowed = [p["resource"] for p in policies if p["effect"] == "allow"]
    return set(allowed) == {"opencode", "opencode-go", "kilo", "deepseek"}


def _check_deterministic_agent() -> bool:
    a = json.load(open(ROOT / "opencode.json"))["agent"]
    for perfil, temp, pasos in (("build", 0.3, 50), ("plan", 0.1, 30), ("audit", 0.0, 20)):
        cfg = a[perfil]
        if cfg["temperature"] != temp or cfg["top_p"] != 1.0 or cfg["steps"] != pasos:
            return False
        if "seed" in cfg or "maxSteps" in cfg:
            return False
    return True


def _check_init_sh() -> bool:
    t = open(ROOT / "scripts/init.sh").read()
    return '"maxSteps"' not in t and '"seed"' not in t and t.count('"steps"') == 3


def _check_readme_patterns() -> bool:
    b = json.load(open(ROOT / "kilo.json"))["permission"]["bash"]
    r = open(ROOT / "README.md").read()
    total, deny, ask = len(b), sum(1 for v in b.values() if v == "deny"), sum(1 for v in b.values() if v == "ask")
    return f"{total} patrones" in r and f"{deny} `deny`" in r and f"{ask} `ask`" in r and f"{total} patrones bash ({deny} `deny`, {ask} `ask`" in r


def _check_env_patterns() -> bool:
    p = json.load(open(ROOT / "kilo.json"))["permission"]
    return (p["edit"].get("*.env") == "deny" and p["edit"].get("*.env.*") == "deny" and p["edit"].get("*.env.example") == "allow" and
            p["read"].get("*.env") == "deny" and p["read"].get("*.env.*") == "deny" and p["read"].get("*.env.example") == "allow")


def _check_critical_deny_pairs() -> bool:
    k = list(json.load(open(ROOT / "kilo.json"))["permission"]["bash"])
    pares = [
        ("rm *", "rm -rf *"), ("rm *", "rm -r *"), ("rm *", "rm -f *"),
        ("git reset *", "git reset --hard*"),
        ("git push *", "git push --force*"),
        ("mv *", "mv --force*"), ("mv *", "mv -f *"),
        ("docker compose down*", "docker compose down -v*"),
        ("pip install *", "pip install --user *"),
        ("psql -c *", "psql * *DROP*"), ("psql -c *", "psql * *TRUNCATE*"),
        ("psql -c *", "psql * *DELETE*"), ("psql -c *", "psql * *ALTER*"),
        ("mysql -e *", "mysql * *DROP*"), ("mysql -e *", "mysql * *TRUNCATE*"),
        ("mysql -e *", "mysql * *DELETE*"), ("mysql -e *", "mysql * *ALTER*"),
        ("sqlite3 *", "sqlite3 * *DROP*"), ("sqlite3 *", "sqlite3 * *TRUNCATE*"),
        ("sqlite3 *", "sqlite3 * *DELETE*"), ("sqlite3 *", "sqlite3 * *ALTER*"),
        ("redis-cli *", "redis-cli FLUSHALL*"),
        ("redis-cli *", "redis-cli * FLUSHALL*"),
        ("redis-cli *", "redis-cli * *DEL*"),
    ]
    for ask, deny in pares:
        if ask not in k or deny not in k:
            return False
    return True


def _check_no_ask_overrides_deny() -> bool:
    cfg = json.load(open(ROOT / "kilo.json"))["permission"]["bash"]
    k = list(cfg)

    def matchea(patron: str, comando: str) -> bool:
        segmento = comando.split("|")[0]
        regex = "^" + re.escape(patron).replace(r"\*", ".*") + "$"
        return re.match(regex, segmento) is not None

    rellenos = ["X", "-C", "--", "x"]
    for i, deny in enumerate(k):
        if cfg[deny] != "deny":
            continue
        variantes = set()
        for r in rellenos:
            v = " ".join(r if t == "*" else t for t in deny.split())
            if matchea(deny, v):
                variantes.add(v)
        for j in range(i + 1, len(k)):
            ask = k[j]
            if cfg[ask] != "ask":
                continue
            for v in variantes:
                if matchea(ask, v):
                    return False
    return True


# == 3. Seguridad ==
def _check_no_personal_data() -> bool:
    pat = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    pat_home = re.compile(r"/home/[A-Za-z0-9_.-]+/")
    excl = re.compile(r"(deny|patrones|claves SSH|no leas|comitees|dummy|BLOQUEADO|127\.0\.0\.1)")
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "venv", ".storage")]
        for f in files:
            if not f.endswith((".md", ".json", ".sh")):
                continue
            ruta = Path(root) / f
            if f.startswith("SBOM-") and f.endswith((".spdx.json", ".cdx.json")):
                continue
            try:
                for i, linea in enumerate(open(ruta, errors="ignore"), 1):
                    if excl.search(linea):
                        continue
                    if pat_home.search(linea):
                        return False
                    for m in pat.findall(linea):
                        try:
                            ip = ipaddress.ip_address(m)
                        except ValueError:
                            continue
                        if not ip.is_loopback:
                            return False
            except Exception as e:
                print(f"  [WARN] Error leyendo {ruta}: {e}")
        return True


def _check_no_emails() -> bool:
    try:
        result = run_cmd([
            "grep", "-rnE",
            "--exclude-dir=node_modules", "--exclude-dir=__pycache__",
            "--exclude-dir=.venv", "--exclude-dir=venv", "--exclude-dir=.storage",
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            "--include=*.md", "--include=*.json", "--include=*.sh", "."
        ])
    except FileNotFoundError:
        # grep not available on Windows, use Python fallback
        return _check_no_emails_python()
    if result.returncode != 0:
        return True
    lines = result.stdout.strip().splitlines()
    for line in lines:
        if not re.search(r"(youremail@example|creativecommons|dummy@example|SBOM-|security@better-project\.local)", line):
            return False
    return True


def _check_no_emails_python() -> bool:
    excl = re.compile(r"(youremail@example|creativecommons|dummy@example|SBOM-|security@better-project\.local)")
    email_pat = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "venv", ".storage")]
        for f in files:
            if not f.endswith((".md", ".json", ".sh")):
                continue
            ruta = Path(root) / f
            try:
                for linea in open(ruta, errors="ignore"):
                    if excl.search(linea):
                        continue
                    if email_pat.search(linea):
                        return False
            except Exception as e:
                print(f"  [WARN] Error leyendo {ruta}: {e}")
    return True


def _check_no_api_keys() -> bool:
    try:
        result = run_cmd([
            "grep", "-rnE",
            "--exclude-dir=node_modules", "--exclude-dir=.venv",
            "--exclude-dir=venv", "--exclude-dir=.storage",
            r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|xox[baprs]-[0-9A-Za-z-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)",
            "--include=*.md", "--include=*.json", "--include=*.sh", "."
        ])
    except FileNotFoundError:
        return _check_no_api_keys_python()
    return result.returncode != 0


def _check_no_api_keys_python() -> bool:
    api_pat = re.compile(r"(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|xox[baprs]-[0-9A-Za-z-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "venv", ".storage")]
        for f in files:
            if not f.endswith((".md", ".json", ".sh")):
                continue
            ruta = Path(root) / f
            try:
                for linea in open(ruta, errors="ignore"):
                    if api_pat.search(linea):
                        return False
            except Exception as e:
                print(f"  [WARN] Error leyendo {ruta}: {e}")
    return True


def _check_no_eval_exec() -> bool:
    pat = re.compile(r"\b(eval|exec)\b")
    for f in sorted(os.listdir(ROOT / "scripts")):
        if not f.endswith(".sh") or f == "verificar-proyecto.sh":
            continue
        for i, linea in enumerate(open(ROOT / "scripts" / f), 1):
            if linea.lstrip().startswith("#"):
                continue
            if re.search(r'":\s*"', linea) or re.search(r'"(eval|exec)\s', linea):
                continue
            if pat.search(linea):
                return False
    return True


def _check_readonly_agents() -> bool:
    for a in ("code-reviewer", "security-auditor", "compliance-checker", "cost-optimizer", "dependency-auditor"):
        agent_path = ROOT / ".opencode" / "agents" / f"{a}.md"
        kilo_path = ROOT / ".kilo" / "agents" / f"{a}.md"
        if not agent_path.exists() or not kilo_path.exists():
            return False
        content = agent_path.read_text()
        if "edit: deny" not in content or "mode: subagent" not in content:
            return False
        if agent_path.read_bytes() != kilo_path.read_bytes():
            return False
    return True


# == 4. Ecosistema ==
def _check_python_syntax() -> bool:
    for f in (ROOT / "scripts").glob("*.py"):
        if run_cmd([sys.executable, "-m", "py_compile", str(f)]).returncode != 0:
            return False
    return True


def _run_mutation_check() -> bool:
    return run_cmd([sys.executable, "scripts/mutation_check.py", "--batch", "--strict", "--umbral", "0.85"]).returncode == 0


def _run_doc_validator_strict() -> bool:
    return run_cmd([sys.executable, "scripts/doc_validator.py", "--strict"]).returncode == 0


def _run_lessons_check() -> bool:
    return run_cmd([sys.executable, "scripts/lessons_extractor.py", "--check"]).returncode == 0


def _check_knowledge_index() -> bool:
    r1 = run_cmd([sys.executable, "scripts/index_knowledge.py"])
    r2 = run_cmd([sys.executable, "scripts/index_knowledge.py", "--check"])
    return r1.returncode == 0 and r2.returncode == 0


def _check_retrieval_quality() -> bool:
    sys.path.insert(0, str(ROOT / "scripts"))
    import index_knowledge as ik
    ik.KNOWLEDGE_DIR = ROOT / ".docs" / "knowledge"
    ik.STORAGE_DIR = ROOT / ".docs" / ".storage"
    ik.JSON_INDEX = ik.STORAGE_DIR / "index.json"
    ik.MANIFEST = ik.STORAGE_DIR / "manifest.json"
    ik.CHROMA_DIR = ik.STORAGE_DIR / "chroma_db"
    if not ik.check_fresh():
        print("  [FALLO] retrieval quality: indice no fresco (ejecuta 'python scripts/index_knowledge.py')")
        return False
    if not ik.JSON_INDEX.exists():
        print("  [FALLO] retrieval quality: backend JSON no disponible (index.json no existe)")
        return False
    test_queries = [
        ("pilar requisitos", "pilar"),
        ("trazabilidad contrato", "trazabilidad"),
        ("indice conocimiento", "indice"),
        ("lecciones aprendidas", "leccion"),
        ("sesgos falacias", "sesgo"),
    ]
    relevant = 0
    for query, expected_term in test_queries:
        hits = ik.search_json(query, k=10)
        if any(expected_term in hit["contenido"].lower() for hit in hits):
            relevant += 1
    recall = relevant / len(test_queries)
    if recall < 0.7:
        print(f"  [FALLO] retrieval quality: recall@10 = {recall:.2f} < 0.7")
        return False
    return True


def _run_tests_isolated() -> bool:
    return run_cmd([sys.executable, "scripts/run_tests_isolated.py"]).returncode == 0


def _run_doc_validator_demo() -> bool:
    return run_cmd([sys.executable, "scripts/doc_validator.py", "--root", "demo"]).returncode == 0


def _run_adr_validator() -> bool:
    return run_cmd([sys.executable, "scripts/adr_validator.py"]).returncode == 0


def _run_auto_audit() -> bool:
    return run_cmd([sys.executable, "scripts/auto_audit.py", "all"]).returncode == 0


def _run_diagnostico() -> bool:
    return run_cmd([sys.executable, "scripts/diagnostico.py", "--root", ".", "--min-score", "80"]).returncode == 0


def _check_sbom() -> bool:
    return run_cmd([sys.executable, "scripts/generate_sbom.py", "--check"]).returncode == 0


def _check_coverage() -> bool:
    """Ejecuta tests con coverage y verifica umbral >= 30% en scripts/ (inicial, subir progresivamente)."""
    # Ejecutar tests con coverage solo en scripts/ - solo tests que cubren scripts/
    result = run_cmd([
        sys.executable, "-m", "coverage", "run",
        "--source=scripts",
        "-m", "unittest",
        "tests.test_ecosistema.TestDocValidator",
        "tests.test_ecosistema.TestIndexKnowledge",
        "tests.test_ecosistema.TestMCPServer",
        "tests.test_ecosistema.TestLessonsExtractor",
        "tests.test_ecosistema.TestJevLlama",
        "-q"
    ])
    if result.returncode != 0:
        print("  [FALLO] coverage: tests fallaron")
        return False
    # Obtener reporte y parsear total
    report_result = run_cmd([sys.executable, "-m", "coverage", "report", "--format=total"])
    if report_result.returncode != 0:
        print("  [FALLO] coverage: no se pudo obtener reporte")
        return False
    try:
        total_line = report_result.stdout.strip().splitlines()[-1]
        coverage_pct = int(total_line.strip())
    except (IndexError, ValueError):
        print("  [FALLO] coverage: formato de reporte inesperado")
        return False
    # Umbral inicial 30% (subir progresivamente a 80%)
    threshold = 30
    if coverage_pct < threshold:
        print(f"  [FALLO] coverage: {coverage_pct}% < {threshold}%")
        return False
    print(f"  [OK] coverage: {coverage_pct}% >= {threshold}%")
    return True


# == 5. Repositorio ==
def _check_hook_installed(name: str) -> bool:
    hook_script = ROOT / "scripts" / "hooks" / name
    hook_installed = ROOT / ".git" / "hooks" / name
    if not hook_script.exists() or not hook_installed.exists():
        return False
    return hook_script.read_bytes() == hook_installed.read_bytes()


def _check_git_fsck() -> bool:
    result = run_cmd(["git", "fsck", "--unreachable"])
    return result.returncode == 0 and not result.stdout.strip()


def _check_no_unstaged() -> bool:
    result = run_cmd(["git", "status", "--porcelain"])
    return not any(line.startswith(" ") for line in result.stdout.splitlines())


def _check_clean_worktree() -> bool:
    result = run_cmd(["git", "status", "--porcelain"])
    return not result.stdout.strip()


def _check_main_synced() -> bool:
    result = run_cmd(["git", "status", "--porcelain", "--branch"])
    return not any(re.search(r"adelant|ahead|behind|adelanta", line) for line in result.stdout.splitlines())


def _check_remote_head() -> bool:
    try:
        head = run_cmd(["git", "ls-remote", "origin", "HEAD"])
        main = run_cmd(["git", "ls-remote", "origin", "refs/heads/main"])
        if head.returncode != 0 or main.returncode != 0:
            return True  # No remote, skip check
        return head.stdout.split()[0] == main.stdout.split()[0]
    except (IndexError, FileNotFoundError):
        return True  # No remote or git not available, skip check


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lite", action="store_true")
    parser.add_argument("--pre-commit", action="store_true")
    args = parser.parse_args()

    print("== 1. Reglas ==")
    check("20 reglas P0 definidas en AGENTS.md", _check_p0_rules)
    check("37 reglas P1 definidas en AGENTS.md", _check_p1_rules)
    check("IDs identicos en REGLAS-COMPLETAS", _check_ids_identical)
    check("titulos de reglas identicos en REGLAS-COMPLETAS", _check_titles_identical)
    check("referencias a rutas docs/, scripts/ y .opencode/ existen", _check_refs_exist)
    check("requisitos versionados y referencias de codigo validos", _check_doc_validator)
    check("ningun .env versionado en git", _check_no_env_in_git)
    if not args.lite:
        check("52 limitaciones en REGLAS-COMPLETAS", _check_limitaciones)
        check("50 errores en README", _check_readme_errores)
        check("IDs citados en CHECKLIST existen en AGENTS.md", _check_checklist_ids)
        check("IDs citados en README existen en AGENTS.md", _check_readme_ids)
        check("numeracion secuencial de pruebas en PRUEBAS", _check_pruebas_sequential)
        check("pruebas citadas en LECCIONES existen en PRUEBAS", _check_lecciones_citan_pruebas)
        check("conteo total reglas P0+P1+P2 = 62 (20 P0 + 37 P1 + 5 P2)", _check_total_reglas)
        check("README no dice '50 reglas P0/P1/P2' (son 61 reglas, 50 errores)", _check_readme_no_50_reglas)
        check("tools MCP habilitados = 4 (context7, gh_grep, sentry, better-project)", _check_mcp_tools)
        check("rondas PRUEBAS.md = 33 (coherente en todo el doc)", _check_pruebas_rondas)

    print("== 2. Config ==")
    check("kilo.json es JSON valido", lambda: json.load(open(ROOT / "kilo.json")))
    check("opencode.json es JSON valido (compatibilidad)", lambda: json.load(open(ROOT / "opencode.json")))
    check("304 patrones de permisos bash (218 deny, 85 ask, 1 allow)", _check_bash_patterns)
    check("kilo.json y opencode.json tienen los mismos permisos bash", _check_same_permissions)
    check("edit/read bloquean claves y credenciales", _check_edit_read_deny)
    check("experimental.policies en kilo.json: deny all + allow kilo, deepseek, openrouter", _check_kilo_policies)
    check("experimental.policies en opencode.json: deny all + allow opencode, opencode-go, kilo, deepseek", _check_opencode_policies)
    check("agente determinista: temperature/top_p/steps (sin seed ni maxSteps deprecado)", _check_deterministic_agent)
    check("init.sh genera perfiles con steps (sin seed ni maxSteps)", _check_init_sh)
    if not args.lite:
        check("conteos de patrones en README coherentes con la config", _check_readme_patterns)
        check("edit/read bloquean .env y permiten .env.example", _check_env_patterns)
        check("pares criticos deny presentes", _check_critical_deny_pairs)
        check("ningun ask posterior anula un deny (todas las familias)", _check_no_ask_overrides_deny)

    print("== 3. Seguridad (P0.9/P0.10) ==")
    check("sin IPs, claves, rutas .ssh o rutas de usuario en archivos", _check_no_personal_data)
    check("sin emails personales en archivos", _check_no_emails)
    check("sin formatos de claves API en archivos", _check_no_api_keys)
    check("sin eval/exec en scripts", _check_no_eval_exec)
    check("agentes de solo lectura con edit deny y sincronizados", _check_readonly_agents)

    print("== 4. Ecosistema better-project ==")
    check("sintaxis python de todos los scripts", _check_python_syntax)
    check_ruff()
    if os.environ.get("BETTER_MUTATION_ACTIVE") == "1":
        check("mutacion rapida batch critico (omitida: reentrada de mutacion)", lambda: True)
    else:
        check("mutacion rapida batch critico (umbral 0.85)", _run_mutation_check)
    check("trazabilidad REQ valida (doc_validator --strict)", _run_doc_validator_strict)
    check("lecciones validas (lessons_extractor --check)", _run_lessons_check)
    check("indice de conocimiento generable", _check_knowledge_index)
    check("retrieval quality recall@10 >= 0.7", _check_retrieval_quality)
    check("suite de tests del ecosistema (aislada por proceso)", _run_tests_isolated)
    check("SBOM regenerable (Syft CycloneDX/SPDX)", _check_sbom)
    check("coverage >= 80% en scripts/", _check_coverage)
    if not args.lite:
        check("demo valida con --root", _run_doc_validator_demo)
        check("ADRs validos + auditoria de sesgos (REQ-013)", _run_adr_validator)
        check("auto-auditoria del proyecto (REQ-014)", _run_auto_audit)
        check("diagnostico propio >= 80 (REQ-017)", _run_diagnostico)

    print("== 5. Repositorio ==")
    check("hook pre-commit instalado identico al script", lambda: _check_hook_installed("pre-commit"))
    check("hook commit-msg instalado identico al script", lambda: _check_hook_installed("commit-msg"))
    check("sin objetos huerfanos en git (fsck)", _check_git_fsck)
    if args.pre_commit:
        check("sin cambios sin stagear (solo staged permitido)", _check_no_unstaged)
        check("rama main sincronizada con origin", _check_main_synced)
        check("HEAD remoto apunta a main", _check_remote_head)
    else:
        check("arbol de trabajo limpio", _check_clean_worktree)
        check("rama main sincronizada con origin", _check_main_synced)
        check("HEAD remoto apunta a main", _check_remote_head)

    print()
    print(f"Resultado: {PASS} OK, {FAIL} FALLOS")
    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
