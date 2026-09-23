#!/usr/bin/env python3
"""adr_backfill.py — Genera borradores de ADR retroactivos desde historial Git y lecciones.

# REQ-025
# Propuesta Fase 2 Pilar 4

Analiza:
- `git log --grep` para commits con mensajes de decision
- `docs/LECCIONES-APRENDIDAS.md` para lecciones que implican decisiones
- `docs/PRUEBAS.md` para rondas de validacion que cerraron decisiones

Genera borradores en `docs/decisions/ADR-NNN-titulo.md` listos para revisar.

Uso:
    python3 scripts/adr_backfill.py           # lista candidatos
    python3 scripts/adr_backfill.py --write   # escribe borradores
    python3 scripts/adr_backfill.py --dry-run # muestra lo que haria
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "docs" / "decisions"
LESSONS_DIR = ROOT / ".docs" / "lessons"
PRUEBAS_FILE = ROOT / "docs" / "PRUEBAS.md"

# Patrones para detectar decisiones en commits
DECISION_PATTERNS = [
    (r"(?i)adopt(?:a|ar|amos?)\s+", "Adopción de "),
    (r"(?i)migra(?:r|cion|mos?)\s+(?:a|hacia)\s+", "Migración a "),
    (r"(?i)cambia(?:r|mos?)\s+(?:a|por)\s+", "Cambio a "),
    (r"(?i)decid(?:i|imos?)\s+(?:usar|adoptar)\s+", "Decisión: usar "),
    (r"(?i)reemplaza(?:r|mos?)\s+", "Reemplazo de "),
    (r"(?i)elimina(?:r|mos?)\s+", "Eliminación de "),
    (r"(?i)introduc(?:e|imos?)\s+", "Introducción de "),
    (r"(?i)configura(?:r|cion|mos?)\s+", "Configuración de "),
]

# Palabras clave que indican decisiones arquitectonicas
ARCH_KEYWORDS = [
    "arquitectura", "stack", "framework", "patron", "diseño",
    "dependencia", "proveedor", "modelo", "motor", "backend",
    "frontend", "api", "base de datos", "orm", "cache", "cola",
    "seguridad", "permiso", "validacion", "verificacion", "test",
    "ci", "cd", "deploy", "despliegue", "infraestructura",
]

CANDIDATE_TEMPLATE = """---
id: ADR-{num:03d}
titulo: {titulo}
estado: Propuesto
fecha: {fecha}
---

# ADR-{num:03d}: {titulo}

## Contexto

{contexto}

## Alternativas consideradas

- **Alternativa A — {alt_a}**: {alt_a_desc}
- **Alternativa B — {alt_b}**: {alt_b_desc}
- **Alternativa C — {alt_c} (elegida)**: {alt_c_desc}

## Decision

{decision}

## Consecuencias

### Positivas
- {pos_1}
- {pos_2}

### Negativas / deuda asumida
- {neg_1}
- {neg_2}

### Reversibilidad
{reversibilidad}

## Supuestos

- {sup_1}
- {sup_2}

## Metricas de exito

- {metrica_1}
- {metrica_2}

## Pre-mortem (Análisis Prospectivo de Fallos)

- **Escenario 1 — {esc_1}**: {esc_1_desc}. *Mitigación*: {esc_1_mit}
- **Escenario 2 — {esc_2}**: {esc_2_desc}. *Mitigación*: {esc_2_mit}

## Referencias

- {ref_1}
- {ref_2}
"""


def run_git_log() -> list[dict]:
    """Extrae commits que parecen decisiones."""
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--pretty=format:%H|%ad|%s", "--date=short"],
            cwd=ROOT, capture_output=True, text=True, check=True
        )
    except subprocess.CalledProcessError:
        return []

    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        sha, date, subject = parts
        commits.append({"sha": sha[:8], "date": date, "subject": subject})
    return commits


def is_decision_commit(subject: str) -> tuple[bool, str | None]:
    """Detecta si un commit parece una decision y extrae titulo sugerido."""
    subject_lower = subject.lower()
    for pattern, prefix in DECISION_PATTERNS:
        match = re.search(pattern + r"(.+)", subject_lower)
        if match:
            rest = match.group(1).strip()
            # Limpiar y capitalizar
            titulo = prefix + rest[:80]
            # Verificar si tiene keywords arquitectonicas
            if any(kw in subject_lower for kw in ARCH_KEYWORDS):
                return True, titulo
    return False, None


def extract_lessons_decisions() -> list[dict]:
    """Extrae decisiones implicitas de lecciones aprendidas."""
    decisions = []
    for year_file in sorted(LESSONS_DIR.glob("*.yaml")):
        content = year_file.read_text(encoding="utf-8")
        # Parse simple de YAML (cada entrada empieza con "- id:")
        entries = re.split(r"\n- id:", content)
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            if entry.startswith("- id:"):
                entry = entry[len("- id:"):].strip()
            lines = entry.split("\n")
            entry_data = {"id": lines[0].strip()}
            for line in lines[1:]:
                if ":" in line:
                    key, val = line.split(":", 1)
                    entry_data[key.strip()] = val.strip().strip('"').strip("'")
            # Buscar lecciones que impliquen decisiones
            problema = entry_data.get("problema", "")
            recomendacion = entry_data.get("recomendacion", "")
            categoria = entry_data.get("categoria", "")
            if any(kw in (problema + recomendacion).lower() for kw in ARCH_KEYWORDS):
                lsn_id = entry_data["id"]
                if not lsn_id.startswith("LSN-"):
                    lsn_id = f"LSN-{lsn_id}"
                decisions.append({
                    "source": lsn_id,
                    "date": entry_data.get("fecha", ""),
                    "titulo": f"Lección {categoria}: {problema[:60]}",
                    "contexto": f"Problema: {problema}\nRecomendación: {recomendacion}",
                })
    return decisions


def extract_pruebas_decisions() -> list[dict]:
    """Extrae decisiones de rondas de PRUEBAS.md."""
    if not PRUEBAS_FILE.exists():
        return []
    content = PRUEBAS_FILE.read_text(encoding="utf-8")
    decisions = []
    # Buscar "Corrección", "Solución", "Decisión" en rondas
    for ronda_match in re.finditer(r"## Ronda (\d+)", content):
        ronda_num = ronda_match.group(1)
        # Extraer sección de la ronda
        start = ronda_match.start()
        next_ronda = re.search(r"## Ronda \d+", content[start+1:])
        end = next_ronda.start() + start + 1 if next_ronda else len(content)
        ronda_text = content[start:end]
        # Buscar correcciones/soluciones
        for corr in re.finditer(r"(?:Correcci[oó]n|Soluci[oó]n|Decisi[oó]n):\s*(.+)", ronda_text, re.IGNORECASE):
            decisions.append({
                "source": f"Ronda {ronda_num}",
                "date": "",
                "titulo": f"Ronda {ronda_num}: {corr.group(1)[:60]}",
                "contexto": corr.group(1)[:200],
            })
    return decisions


def get_next_adr_num() -> int:
    """Obtiene el siguiente numero de ADR disponible."""
    existing = list(ADR_DIR.glob("ADR-*.md"))
    nums = []
    for f in existing:
        match = re.match(r"ADR-(\d{3})", f.name)
        if match:
            nums.append(int(match.group(1)))
    return max(nums, default=0) + 1


def titulos_existentes() -> set[str]:
    """Titulos ya registrados en ADR: --write no duplica borradores (REQ-025)."""
    titulos = set()
    for f in ADR_DIR.glob("ADR-*.md"):
        match = re.search(r"^titulo:\s*(.+)$", f.read_text(encoding="utf-8"), re.MULTILINE)
        if match:
            titulos.add(match.group(1).strip().lower())
    return titulos


def generate_candidates() -> list[dict]:
    """Genera lista de candidatos a ADR."""
    candidates = []

    # Desde commits
    for commit in run_git_log():
        is_dec, titulo = is_decision_commit(commit["subject"])
        if is_dec:
            candidates.append({
                "source": f"Commit {commit['sha']}",
                "date": commit["date"],
                "titulo": titulo,
                "contexto": f"Commit: {commit['subject']}",
            })

    # Desde lecciones
    candidates.extend(extract_lessons_decisions())

    # Desde pruebas
    candidates.extend(extract_pruebas_decisions())

    # Deduplicar por titulo similar
    seen = set()
    unique = []
    for c in candidates:
        key = c["titulo"].lower()[:40]
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera borradores ADR retroactivos (propuesta Fase 2)")
    parser.add_argument("--write", action="store_true", help="Escribe archivos ADR")
    parser.add_argument("--dry-run", action="store_true", help="Muestra lo que haria sin escribir")
    parser.add_argument("--list", action="store_true", help="Solo lista candidatos")
    args = parser.parse_args(argv)

    candidates = generate_candidates()

    if not candidates:
        print("No se encontraron candidatos a ADR retroactivos.")
        return 0

    print(f"Candidatos encontrados: {len(candidates)}")
    for i, c in enumerate(candidates, 1):
        print(f"  {i}. [{c['source']}] {c['titulo']} ({c['date']})")

    if args.list:
        return 0

    if args.dry_run:
        print("\n--- DRY RUN: archivos que se crearían ---")
        for i, c in enumerate(candidates):
            num = get_next_adr_num() + i
            safe_title = re.sub(r"[^\w\s-]", "", c["titulo"]).strip().replace(" ", "-").lower()[:50]
            fname = f"ADR-{num:03d}-{safe_title}.md"
            print(f"  {fname}")
        return 0

    if not args.write:
        print("\nUse --write para crear los archivos, --dry-run para previsualizar, --list para solo listar.")
        return 0

    # Escribir borradores
    ADR_DIR.mkdir(parents=True, exist_ok=True)
    existentes = titulos_existentes()
    for i, c in enumerate(candidates):
        num = get_next_adr_num() + i
        safe_title = re.sub(r"[^\w\s-]", "", c["titulo"]).strip().replace(" ", "-").lower()[:50]
        fname = f"ADR-{num:03d}-{safe_title}.md"
        fpath = ADR_DIR / fname

        if c["titulo"].strip().lower() in existentes:
            print(f"[SKIP] ya existe un ADR con el titulo: {c['titulo']}")
            continue

        if fpath.exists():
            print(f"[SKIP] {fname} ya existe")
            continue

        # Generar contenido basico (plantilla)
        content = CANDIDATE_TEMPLATE.format(
            num=num,
            titulo=c["titulo"],
            fecha=c["date"] or datetime.now().strftime("%Y-%m-%d"),
            contexto=c["contexto"] or "Pendiente: describir el contexto y problema que motiva esta decisión.",
            alt_a="Mantener estado actual",
            alt_a_desc="No cambiar; coste 0 pero mantiene el problema.",
            alt_b="Alternativa intermedia",
            alt_b_desc="Solución parcial con menor alcance.",
            alt_c="Solución completa",
            alt_c_desc="Implementación completa que resuelve el problema.",
            decision="Pendiente: documentar qué se decide y por qué.",
            pos_1="Beneficio principal medible.",
            pos_2="Beneficio secundario.",
            neg_1="Coste o riesgo asumido.",
            neg_2="Deuda técnica o limitación.",
            reversibilidad="Alta/Media/Baja: descripción del coste de revertir.",
            sup_1="Premisa clave que valida la decisión.",
            sup_2="Segunda premisa.",
            metrica_1="KPI verificable 1.",
            metrica_2="KPI verificable 2.",
            esc_1="Fallo principal imaginado",
            esc_1_desc="Descripción del escenario de fallo.",
            esc_1_mit="Acción de mitigación.",
            esc_2="Fallo secundario imaginado",
            esc_2_desc="Descripción del escenario de fallo.",
            esc_2_mit="Acción de mitigación.",
            ref_1="REQ-XXX o LSN-XXX relacionado.",
            ref_2="ADR-XXX o documento relacionado.",
        )
        fpath.write_text(content, encoding="utf-8")
        existentes.add(c["titulo"].strip().lower())
        print(f"[CREADO] {fname}")

    print(f"\n{len(candidates)} borradores creados en {ADR_DIR}")
    print("REVISAR Y COMPLETAR cada archivo antes de cambiar estado a 'Aceptado'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
