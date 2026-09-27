# Salud del proyecto

> Generado por `scripts/health_dashboard.py` (REQ-024); no editar a mano.
> Ultimo run registrado: 2026-09-26.

| # | KPI | Valor | Meta | Estado |
|---|-----|-------|------|--------|
| 1 | 1. Onboarding (clone -> verificador verde) | 156 s | <= 600 s | OK |
| 2 | 2. REQs trazados (Implementados con refs / no Deprecados) | 100.0 % (26/26) | >= 90 % | OK |
| 3 | 3. Mutation score (batch ponderado) | 1.000 | >= 0.85 | OK |
| 4 | 4. Tiempo CI completo | 380 s | <= 1800 s | OK |
| 5 | 5. Coste mantenimiento (% producto demo) | 1.2 % (72/6234 SLOC) | <= 20 % | OK |

## Tendencia (ultimos 10 runs)

| Fecha | Onboarding (s) | REQs trazados (%) | Mutation | CI (s) | Producto (%) |
|-------|----------------|-------------------|----------|--------|--------------|
| 2026-09-25 | 181 s | 100.0 | 1.0 | 325 s | 1.3 |
| 2026-09-26 | 156 s | 100.0 | 1.0 | 380 s | 1.2 |

## Definiciones

- KPI 1 y 4: medidos por el CI local `bash scripts/ci.sh` (REQ-009);
  en runs locales sin CI quedan `n/d` (no se inventan, P0.1).
- KPI 2: `scripts/doc_validator.py` (estado del frontmatter + refs REQ-XXX
  en codigo); el denominador excluye REQs Deprecados.
- KPI 3: `scripts/mutation_check.py --batch` (REQ-015), ponderado por
  numero de mutantes; el CI pasa el score ya medido.
- KPI 5: proxy de coste, SLOC de `demo/**/*.py` (producto) sobre
  `scripts/**/*.py` + `demo/**/*.py`; se ignoran lineas vacias y
  comentarios. El historial vive en `.docs/.storage/health_runs.jsonl`.
