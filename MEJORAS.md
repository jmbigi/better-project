# Lista de Mejoras Priorizadas (basado en auditoría real)

| # | Mejora | Prioridad | Valor (%) | Esfuerzo (h) | Evidencia |
|---|--------|-----------|-----------|--------------|-----------|
| 1 | **Corregir 3 violaciones P1.26 en `verificar_proyecto.py`** (`except: pass` líneas 291, 332, 363) | P0 | 95 | 1 | `auto_audit.py all` reporta 3 errores críticos |
| 2 | **Hacer `curses` opcional en `jev_review.py`** (fallback a modo `--report` en Windows) | P0 | 90 | 2 | Suite rota en Windows por `ModuleNotFoundError: _curses` |
| 3 | **Forzar índice JSON en `index_knowledge.py`** (flag `--json` o variable de entorno) para retrieval quality check | P1 | 85 | 2 | `diagnostico.py` da 60/100 en conocimiento; check retrieval salta silenciosamente |
| 4 | **Instalar `pip-audit` en venv** y ejecutar `audit_advisories.py` en CI | P1 | 80 | 1 | P0.18 requiere SBOM + escaneo; actualmente falla |
| 5 | **Corregir `verificar-proyecto.sh` para Windows** (PowerShell nativo o documentar WSL obligatorio) | P1 | 75 | 4 | Verificador principal no ejecuta en Windows nativo |
| 6 | **Añadir mutation score gate en `verificar-proyecto.sh`** (umbral 0.85 ya configurado) | P1 | 70 | 1 | Ya pasa (0.995) pero no está en verificador principal |
| 7 | **Documentar dependencia `curses` / `windows-curses`** en `docs/HERRAMIENTAS-Y-FUENTES.md` | P2 | 60 | 0.5 | Usuario Windows no sabe por qué falla |
| 8 | **Añadir test de integración Windows** en `run_tests_isolated.py` (detectar curses faltante) | P2 | 55 | 2 | Prevenir regresión |
| 9 | **Generar SBOM automático** (`syft`) en `verificar-proyecto.sh` | P2 | 50 | 3 | P0.18 obligatorio antes de usar deps |
| 10 | **Migrar `verificar_proyecto.py` a Python** (eliminar bash, portable) | P3 | 40 | 16 | Eliminar dependencia WSL/bash |
| 11 | **Añadir coverage real** (`coverage.py`) y gate mínimo en verificador | P3 | 35 | 3 | No hay métrica de coverage hoy |
| 12 | **Benchmark retrieval quality** (recall@10, MRR, nDCG) automatizado | P3 | 30 | 4 | P0.20 requiere métricas cuantitativas |

## Resumen de impacto

- **Quick wins (1-4)**: ~6h, resuelven 80% de bloqueantes críticos
- **Media (5-9)**: ~10.5h, portabilidad y compliance completo
- **Largo plazo (10-12)**: ~23h, arquitectura y métricas avanzadas

## Criterio de priorización

- **P0**: Bloquea entrega / viola regla P0 / rompe CI en plataforma soportada
- **P1**: Deuda técnica que impide verificación completa / compliance parcial
- **P2**: Mejora DX / prevención / documentación
- **P3**: Arquitectura / métricas avanzadas / nice-to-have