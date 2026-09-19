#!/usr/bin/env python3
"""Análisis estático de comandos shell para detectar patrones peligrosos.

Usa únicamente la stdlib de Python (shlex, re) para no añadir dependencias
externas (P0.18). Detecta:

- Pipes donde una fuente de red (curl/wget/fetch) alimenta un intérprete shell.
- Process substitution que alimenta un shell: bash <(curl ...).
- Uso de eval/exec/source.
- Command substitution $(...) o `...` con descargadores dentro.
- bash -c / sh -c con contenido peligroso.
- Subcomandos destructivos encadenados (;, &&, ||) o con rutas absolutas no
  cubiertas por los patrones deny (rm -rf, git reset --hard, etc.).

Limitaciones conocidas: no es un parser completo de Bash. Construcciones muy
retorcidas pueden escapar, pero cubre las variantes documentadas en P0.8.
"""

import re
import shlex
from typing import List, Set

DOWNLOADERS = {"curl", "wget", "fetch"}
SHELL_NAMES = {"bash", "sh", "zsh", "ksh", "dash", "csh", "tcsh"}
EVAL_LIKE = {"eval", "exec", "source", "."}
SUDO = "sudo"

# Subcomandos destructivos que los patrones deny de opencode.json no pueden
# matchear cuando van encadenados (;, &&), dentro de sh -c / bash -c, o con
# rutas absolutas no cubiertas. Se aplican a cada subcomando por separado.
DANGEROUS_SUBCOMMAND_PATTERNS: List[tuple[str, str]] = [
    (r"\brm\s+-rf\b", "rm-rf"),
    (r"\brm\s+-r\b", "rm-r"),
    (r"\brm\s+-f\b", "rm-f"),
    (r"\bgit\s+reset\s+--hard\b", "git-reset-hard"),
    (r"\bgit\s+push\s+--force\b", "git-push-force"),
    (r"\bdocker\s+compose\s+down\s+-v\b", "docker-compose-down-v"),
    (r"\bsqlite3\s+.*\bDROP\b", "sqlite3-drop"),
    (r"\bsqlite3\s+.*\bTRUNCATE\b", "sqlite3-truncate"),
    (r"\bsqlite3\s+.*\bDELETE\b", "sqlite3-delete"),
    (r"\bsqlite3\s+.*\bALTER\b", "sqlite3-alter"),
    (r"\bpsql\s+.*\bDROP\b", "psql-drop"),
    (r"\bpsql\s+.*\bTRUNCATE\b", "psql-truncate"),
    (r"\bpsql\s+.*\bDELETE\b", "psql-delete"),
    (r"\bpsql\s+.*\bALTER\b", "psql-alter"),
    (r"\bmysql\s+.*\bDROP\b", "mysql-drop"),
    (r"\bmysql\s+.*\bTRUNCATE\b", "mysql-truncate"),
    (r"\bmysql\s+.*\bDELETE\b", "mysql-delete"),
    (r"\bmysql\s+.*\bALTER\b", "mysql-alter"),
    (r"\bredis-cli\s+.*\bFLUSHALL\b", "redis-flushall"),
    (r"\bredis-cli\s+.*\bFLUSHDB\b", "redis-flushdb"),
]


def tokenize(cmd: str) -> List[str]:
    """Tokeniza un comando shell respetando comillas y separadores."""
    lexer = shlex.shlex(cmd, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def split_into_commands(tokens: List[str]) -> List[List[List[str]]]:
    """Divide tokens en comandos y cada comando en etapas de pipeline.

    Retorna una lista de comandos; cada comando es una lista de etapas;
    cada etapa es una lista de tokens.
    """
    commands: List[List[List[str]]] = []
    current_command: List[List[str]] = [[]]
    has_content = False

    for tok in tokens:
        if tok in (";", "&&", "||"):
            if has_content:
                commands.append(current_command)
            current_command = [[]]
            has_content = False
        elif tok == "|":
            current_command.append([])
            has_content = True
        else:
            current_command[-1].append(tok)
            has_content = True

    if has_content:
        commands.append(current_command)

    return commands


def _basename(token: str) -> str:
    """Devuelve el nombre base de una ruta, sin comillas."""
    token = token.strip("'\"")
    if "/" in token:
        return token.rsplit("/", 1)[-1]
    return token


def _is_downloader_name(token: str) -> bool:
    """True si el token (nombre o ruta) es un descargador conocido."""
    return _basename(token) in DOWNLOADERS


def _is_shell_name(token: str) -> bool:
    """True si el token (nombre o ruta) es un intérprete shell."""
    return _basename(token) in SHELL_NAMES


def is_downloader(tokens: List[str], index: int = 0) -> bool:
    """True si el token en index es un descargador conocido."""
    if not tokens or index >= len(tokens):
        return False
    return _is_downloader_name(tokens[index])


def has_downloader(tokens: List[str]) -> bool:
    """True si algún token de la etapa es un descargador conocido."""
    return any(_is_downloader_name(tok) for tok in tokens)


def find_shell(tokens: List[str]) -> int:
    """Devuelve el índice de un intérprete shell, o -1 si no hay.

    Soporta prefijos como sudo / sudo -S.
    """
    i = 0
    while i < len(tokens):
        if _is_shell_name(tokens[i]):
            return i
        if _basename(tokens[i]) == SUDO:
            # Saltar sudo y sus opciones hasta encontrar shell o fin.
            i += 1
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 1
            if i < len(tokens) and _is_shell_name(tokens[i]):
                return i
            continue
        i += 1
    return -1


def is_shell(tokens: List[str], index: int = 0) -> bool:
    """True si el token en index es un intérprete shell (o sudo + shell)."""
    if not tokens or index >= len(tokens):
        return False
    name = _basename(tokens[index])
    if name in SHELL_NAMES:
        return True
    if name == SUDO and index + 1 < len(tokens):
        return _is_shell_name(tokens[index + 1])
    return False


def is_eval_like(tokens: List[str], index: int = 0) -> bool:
    """True si el token en index es eval/exec/source."""
    if not tokens or index >= len(tokens):
        return False
    return _basename(tokens[index]) in EVAL_LIKE


def _extract_substitution(token: str) -> List[str]:
    """Si el token es $(...) o `...`, devuelve el contenido interno."""
    inner: List[str] = []
    if token.startswith("$(") and token.endswith(")"):
        inner.append(token[2:-1])
    elif token.startswith("`") and token.endswith("`") and len(token) > 1:
        inner.append(token[1:-1])
    return inner


def _extract_command_substitutions(tokens: List[str]) -> List[str]:
    """Extrae contenidos de command substitution $(...) de una lista de tokens.

    shlex puede representar $(...) como un único token o como la secuencia
    '$', '(', ..., ')' según el contexto; esta función cubre ambos casos.
    """
    result: List[str] = []
    i = 0
    while i < len(tokens):
        # Caso 1: token único $(...)
        if tokens[i].startswith("$(") and tokens[i].endswith(")"):
            result.append(tokens[i][2:-1])
            i += 1
            continue
        # Caso 2: secuencia '$', '(', ..., ')'
        if tokens[i] == "$" and i + 1 < len(tokens) and tokens[i + 1] == "(":
            depth = 1
            start = i + 2
            j = start
            while j < len(tokens) and depth > 0:
                if tokens[j] == "$" and j + 1 < len(tokens) and tokens[j + 1] == "(":
                    depth += 1
                    j += 1
                elif tokens[j] == ")":
                    depth -= 1
                j += 1
            if depth == 0:
                inner = " ".join(tokens[start:j - 1])
                result.append(inner)
                i = j - 1
        i += 1
    return result


def _extract_process_substitutions(tokens: List[str]) -> List[str]:
    """Extrae contenidos de process substitution <(...)> como lista de strings."""
    result: List[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] == "<(":
            depth = 1
            start = i + 1
            j = start
            while j < len(tokens) and depth > 0:
                if tokens[j] == "<(":
                    depth += 1
                elif tokens[j] == ")":
                    depth -= 1
                j += 1
            if depth == 0:
                inner = " ".join(tokens[start:j - 1])
                result.append(inner)
                i = j - 1
        i += 1
    return result


def _extract_backtick_blocks(tokens: List[str]) -> List[str]:
    """Reconstruye bloques entre backticks y devuelve sus contenidos."""
    result: List[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("`"):
            if tok.endswith("`") and len(tok) > 1:
                result.append(tok[1:-1])
                i += 1
                continue
            block = [tok[1:]]
            j = i + 1
            while j < len(tokens):
                block.append(tokens[j])
                if tokens[j].endswith("`"):
                    break
                j += 1
            if j < len(tokens):
                block[-1] = block[-1][:-1]
                result.append(" ".join(block))
                i = j
        i += 1
    return result


def _extract_bash_c_content(tokens: List[str]) -> List[str]:
    """Devuelve los argumentos de comandos shell invocados con -c."""
    result: List[str] = []
    if not tokens:
        return result
    if not _is_shell_name(tokens[0]):
        return result
    try:
        idx = tokens.index("-c")
    except ValueError:
        return result
    if idx + 1 < len(tokens):
        result.append(tokens[idx + 1])
    return result


def _dangerous_subcommand_patterns() -> List[tuple[re.Pattern[str], str]]:
    return [(re.compile(p, re.IGNORECASE), label) for p, label in DANGEROUS_SUBCOMMAND_PATTERNS]


def check_dangerous_subcommand(text: str) -> Set[str]:
    """Detecta subcomandos destructivos en texto shell ya normalizado."""
    findings: Set[str] = set()
    for pat, label in _dangerous_subcommand_patterns():
        if pat.search(text):
            findings.add(f"dangerous-subcommand:{label}: {text[:80]}")
    return findings


def analyze_stage(stage: List[str]) -> Set[str]:
    """Analiza una etapa de pipeline (sin pipes internos)."""
    findings: Set[str] = set()
    if not stage:
        return findings

    # Subcomandos destructivos directos (p. ej. rm -rf, git reset --hard)
    stage_text = " ".join(stage)
    findings.update(check_dangerous_subcommand(stage_text))

    # eval / exec / source
    if is_eval_like(stage):
        findings.add(f"eval-like: {' '.join(stage[:4])}")

    # bash -c "$(curl ...)" o bash -c "curl ... | bash"
    if find_shell(stage) != -1 and "-c" in stage:
        for content in _extract_bash_c_content(stage):
            content_tokens = tokenize(content)
            # Command substitution con descargador dentro del argumento -c
            for inner in _extract_command_substitutions(content_tokens):
                if any(dl in inner for dl in DOWNLOADERS):
                    findings.add(f"shell-c-with-downloader: {' '.join(stage[:4])}")
            for inner in _extract_backtick_blocks(content_tokens):
                if any(dl in inner for dl in DOWNLOADERS):
                    findings.add(f"shell-c-with-downloader: {' '.join(stage[:4])}")
            findings.update(analyze(content))

    # command substitution peligrosa dentro de la etapa (recursivo)
    for inner in _extract_command_substitutions(stage):
        findings.update(analyze(inner))
    for tok in stage:
        for inner in _extract_substitution(tok):
            findings.update(analyze(inner))

    # process substitution peligrosa: bash <(curl ...)
    shell_idx = find_shell(stage)
    if shell_idx != -1:
        for inner in _extract_process_substitutions(stage):
            if any(dl in inner for dl in DOWNLOADERS):
                findings.add(
                    f"shell-with-process-substitution: {' '.join(stage[:4])}"
                )
            findings.update(analyze(inner))

    # backtick blocks
    for inner in _extract_backtick_blocks(stage):
        findings.update(analyze(inner))

    return findings


def analyze_pipeline(stages: List[List[str]]) -> Set[str]:
    """Analiza un pipeline completo (varias etapas separadas por |)."""
    findings: Set[str] = set()
    if not stages:
        return findings

    # Detección de pipe peligroso: descargador -> shell
    if len(stages) >= 2:
        source = stages[0]
        sink = stages[-1]
        if has_downloader(source) and find_shell(sink) != -1:
            findings.add(
                f"dangerous-pipe: {' '.join(source[:4])} | ... | {' '.join(sink[:4])}"
            )

    # Pipe donde la fuente es un backtick con descargador
    if len(stages) >= 2:
        source = stages[0]
        sink = stages[-1]
        if find_shell(sink) != -1:
            for inner in _extract_backtick_blocks(source):
                if any(dl in inner for dl in DOWNLOADERS):
                    findings.add(
                        f"dangerous-pipe-backtick: {' '.join(source[:4])} | ..."
                    )

    # Analizar cada etapa por separado
    for stage in stages:
        findings.update(analyze_stage(stage))

    return findings


def analyze(cmd: str) -> List[str]:
    """Analiza un comando shell y devuelve la lista de hallazgos ordenada."""
    try:
        tokens = tokenize(cmd)
    except ValueError as exc:
        # Falla explícita: no tragamos errores de tokenización (P1.26).
        raise ValueError(f"No se pudo tokenizar el comando: {cmd!r}: {exc}") from exc

    commands = split_into_commands(tokens)
    findings: Set[str] = set()
    for pipeline in commands:
        findings.update(analyze_pipeline(pipeline))
        # Cada subcomando separado por ; / && / || se revisa tambien por patrones
        # destructivos que el matcher de comodines no puede cubrir.
        subcommand_text = " | ".join(" ".join(stage) for stage in pipeline)
        findings.update(check_dangerous_subcommand(subcommand_text))

    return sorted(findings)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python3 scripts/analyze_shell.py '<comando shell>'", file=sys.stderr)
        sys.exit(1)

    result = analyze(sys.argv[1])
    if result:
        print("\n".join(result))
        sys.exit(1)
    sys.exit(0)
