#!/usr/bin/env python3
"""health_dashboard.py — Dashboard de KPIs del framework en CI (REQ-024).

# REQ-024

Genera `docs/health.md` con los 5 KPIs del proyecto, sus metas y la tendencia
de los ultimos runs. El historial vive en `.docs/.storage/health_runs.jsonl`
(generado, no versionado; `docs/health.md` si se versiona). El CI local
(`scripts/ci.sh`, REQ-009) lo invoca al terminar en verde y le pasa los
tiempos medidos; en runs locales los KPIs de tiempo quedan `n/d`.

Uso:
    python3 scripts/health_dashboard.py [--onboarding-seconds N] [--ci-seconds N]
        [--mutation-score F] [--fecha AAAA-MM-DD] [--json]
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORAGE_DIR = ROOT / ".docs" / ".storage"
HISTORY = STORAGE_DIR / "health_runs.jsonl"
HEALTH_MD = ROOT / "docs" / "health.md"
MAX_RUNS = 10

# Metas numericas por KPI (REQ-024). Mutation alineada con el gate del
# verificador (0.85); coherencia con GOVERNANCE.md "Metricas de salud".
METAS = {
    "onboarding_segundos": 600.0,
    "reqs_trazados_pct": 90.0,
    "mutation_score": 0.85,
    "ci_segundos": 1800.0,
    "producto_pct": 20.0,
}


def _estado(valor: float | None, meta: float, mayor_es_mejor: bool) -> str:
    if valor is None:
        return "n/d"
    cumple = valor >= meta if mayor_es_mejor else valor <= meta
    return "OK" if cumple else "FUERA"


def kpi_reqs_trazados(reqs: dict, refs: dict) -> tuple[float, int, int]:
    """(% trazado, implementados con refs, total no Deprecados)."""
    no_deprecados = {
        rid: entry
        for rid, entry in reqs.items()
        if entry["meta"].get("estado") != "Deprecado"
    }
    total = len(no_deprecados)
    con_refs = sum(
        1
        for rid, entry in no_deprecados.items()
        if entry["meta"].get("estado") == "Implementado" and rid in refs
    )
    pct = 100.0 * con_refs / total if total else 100.0
    return pct, con_refs, total


def _sloc(paths: list[Path]) -> int:
    """SLOC: lineas no vacias y que no son solo comentario."""
    total = 0
    for path in paths:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            texto = line.strip()
            if texto and not texto.startswith("#"):
                total += 1
    return total


def kpi_producto(root: Path = ROOT) -> tuple[float, int, int]:
    """(% producto, SLOC producto demo/, SLOC tooling scripts/)."""
    tooling = sorted((root / "scripts").rglob("*.py"))
    producto = sorted((root / "demo").rglob("*.py"))
    sloc_tooling = _sloc(tooling)
    sloc_producto = _sloc(producto)
    total = sloc_tooling + sloc_producto
    pct = 100.0 * sloc_producto / total if total else 0.0
    return pct, sloc_producto, sloc_tooling


def kpi_mutation(root: Path = ROOT) -> float:
    """Mutation score ponderado (batch, REQ-015) sobre copia temporal."""
    import mutation_check as mc

    copia = mc._copia_temporal(root)
    try:
        return float(mc.medir_batch(copia)["score"])
    finally:
        shutil.rmtree(copia, ignore_errors=True)


def cargar_historial(path: Path | None = None) -> list[dict]:
    """Lista de reportes guardados; [] si aun no existe el historial."""
    destino = path or HISTORY
    if not destino.exists():
        return []
    registros: list[dict] = []
    for linea in destino.read_text(encoding="utf-8").splitlines():
        texto = linea.strip()
        if texto:
            registros.append(json.loads(texto))
    return registros


def registrar(reporte: dict, path: Path | None = None) -> list[dict]:
    """Anade el reporte al historial y conserva los ultimos MAX_RUNS."""
    destino = path or HISTORY
    historial = cargar_historial(destino)
    historial.append(reporte)
    historial = historial[-MAX_RUNS:]
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in historial),
        encoding="utf-8",
    )
    return historial


def _valor_segundos(valor: float | None) -> str:
    return f"{valor:.0f} s" if valor is not None else "n/d"


def render_md(historial: list[dict]) -> str:
    """Markdown del dashboard: KPIs actuales + tendencia de ultimos runs."""
    run = historial[-1]
    onb = run.get("onboarding_segundos")
    ci = run.get("ci_segundos")
    mut = run.get("mutation_score")
    filas = [
        (
            "1. Onboarding (clone -> verificador verde)",
            _valor_segundos(onb),
            f"<= {METAS['onboarding_segundos']:.0f} s",
            _estado(onb, METAS["onboarding_segundos"], mayor_es_mejor=False),
        ),
        (
            "2. REQs trazados (Implementados con refs / no Deprecados)",
            f"{run.get('reqs_trazados_pct', 0.0):.1f} % "
            f"({run.get('reqs_implementados_con_refs', 0)}"
            f"/{run.get('reqs_no_deprecados', 0)})",
            f">= {METAS['reqs_trazados_pct']:.0f} %",
            _estado(run.get("reqs_trazados_pct"), METAS["reqs_trazados_pct"], True),
        ),
        (
            "3. Mutation score (batch ponderado)",
            f"{mut:.3f}" if mut is not None else "n/d",
            f">= {METAS['mutation_score']:.2f}",
            _estado(mut, METAS["mutation_score"], True),
        ),
        (
            "4. Tiempo CI completo",
            _valor_segundos(ci),
            f"<= {METAS['ci_segundos']:.0f} s",
            _estado(ci, METAS["ci_segundos"], mayor_es_mejor=False),
        ),
        (
            "5. Coste mantenimiento (% producto demo)",
            f"{run.get('producto_pct', 0.0):.1f} % "
            f"({run.get('sloc_producto', 0)}"
            f"/{run.get('sloc_producto', 0) + run.get('sloc_tooling', 0)} SLOC)",
            f"<= {METAS['producto_pct']:.0f} %",
            _estado(run.get("producto_pct"), METAS["producto_pct"], False),
        ),
    ]
    lineas = [
        "# Salud del proyecto",
        "",
        "> Generado por `scripts/health_dashboard.py` (REQ-024); no editar a mano.",
        f"> Ultimo run registrado: {run.get('fecha', 'n/d')}.",
        "",
        "| # | KPI | Valor | Meta | Estado |",
        "|---|-----|-------|------|--------|",
    ]
    lineas += [f"| {i} | {kpi} | {valor} | {meta} | {estado} |" for i, (kpi, valor, meta, estado) in enumerate(filas, 1)]
    lineas += [
        "",
        "## Tendencia (ultimos 10 runs)",
        "",
        "| Fecha | Onboarding (s) | REQs trazados (%) | Mutation | CI (s) | Producto (%) |",
        "|-------|----------------|-------------------|----------|--------|--------------|",
    ]
    for registro in historial:
        lineas.append(
            "| {fecha} | {onb} | {reqs} | {mut} | {ci} | {prod} |".format(
                fecha=registro.get("fecha", "n/d"),
                onb=_valor_segundos(registro.get("onboarding_segundos")),
                reqs=registro.get("reqs_trazados_pct", "n/d"),
                mut=registro.get("mutation_score", "n/d"),
                ci=_valor_segundos(registro.get("ci_segundos")),
                prod=registro.get("producto_pct", "n/d"),
            )
        )
    lineas += [
        "",
        "## Definiciones",
        "",
        "- KPI 1 y 4: medidos por el CI local `bash scripts/ci.sh` (REQ-009);",
        "  en runs locales sin CI quedan `n/d` (no se inventan, P0.1).",
        "- KPI 2: `scripts/doc_validator.py` (estado del frontmatter + refs REQ-XXX",
        "  en codigo); el denominador excluye REQs Deprecados.",
        "- KPI 3: `scripts/mutation_check.py --batch` (REQ-015), ponderado por",
        "  numero de mutantes; el CI pasa el score ya medido.",
        "- KPI 5: proxy de coste, SLOC de `demo/**/*.py` (producto) sobre",
        "  `scripts/**/*.py` + `demo/**/*.py`; se ignoran lineas vacias y",
        "  comentarios. El historial vive en `.docs/.storage/health_runs.jsonl`.",
    ]
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dashboard de KPIs (REQ-024)")
    parser.add_argument("--onboarding-seconds", type=float, default=None)
    parser.add_argument("--ci-seconds", type=float, default=None)
    parser.add_argument("--mutation-score", type=float, default=None)
    parser.add_argument("--fecha", default=date.today().isoformat())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    import doc_validator as dv

    reqs = dv.collect_req_files()
    refs = dv.collect_code_refs()
    pct_reqs, con_refs, total_reqs = kpi_reqs_trazados(reqs, refs)
    pct_prod, sloc_prod, sloc_tool = kpi_producto()
    score = args.mutation_score if args.mutation_score is not None else kpi_mutation()

    reporte = {
        "fecha": args.fecha,
        "onboarding_segundos": args.onboarding_seconds,
        "reqs_trazados_pct": round(pct_reqs, 1),
        "reqs_implementados_con_refs": con_refs,
        "reqs_no_deprecados": total_reqs,
        "mutation_score": round(score, 4),
        "ci_segundos": args.ci_seconds,
        "producto_pct": round(pct_prod, 1),
        "sloc_producto": sloc_prod,
        "sloc_tooling": sloc_tool,
    }
    historial = registrar(reporte)
    HEALTH_MD.write_text(render_md(historial), encoding="utf-8")

    if args.json:
        print(json.dumps(reporte, ensure_ascii=False))
    else:
        print(f"Dashboard generado: {HEALTH_MD}")
        print(f"  REQs trazados: {pct_reqs:.1f}% ({con_refs}/{total_reqs})")
        print(f"  mutation score: {score:.3f}")
        print(f"  producto: {pct_prod:.1f}% ({sloc_prod} SLOC)")
        print(
            "  onboarding: "
            f"{_valor_segundos(args.onboarding_seconds)}  "
            f"CI: {_valor_segundos(args.ci_seconds)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
