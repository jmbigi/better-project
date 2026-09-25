# Lista de Mejoras Priorizadas (basado en auditoría real)

| # | Mejora | Prioridad | Valor (%) | Esfuerzo (h) | Evidencia | Estado |
|---|--------|-----------|-----------|--------------|-----------|--------|
| 1 | **Corregir 3 violaciones P1.26 en `verificar_proyecto.py`** (`except: pass` líneas 291, 332, 363) | P0 | 95 | 1 | `auto_audit.py all` reportaba 3 errores críticos | Hecho (2026-09-24); reverificado 2026-09-25: `auto_audit.py tests` 0 errores y `grep -n "except.*pass" scripts/verificar_proyecto.py` sin resultados |
| 2 | **Hacer `curses` opcional en `tydm_review.py`** (fallback a modo `--report` en Windows) | P0 | 90 | 2 | Suite rota en Windows por `ModuleNotFoundError: _curses` | Hecho (2026-09-24); reverificado 2026-09-25: `TestTyDMReview` verde y el fallback a `--report` tiene test dedicado |
| 3 | **Forzar índice JSON en `index_knowledge.py`** (flag `--json` o variable de entorno) para retrieval quality check | P1 | 85 | 2 | `diagnostico.py` daba 60/100 en conocimiento; el check de retrieval saltaba | Hecho: flag `--json` y `BETTER_INDEX_BACKEND=json` (`index_knowledge.py:428-429`), usados por el verificador y por el check `recall@10` |
| 4 | **Instalar `pip-audit` en venv** y ejecutar `audit_advisories.py` en CI | P1 | 80 | 1 | P0.18 requiere SBOM + escaneo; el escaneo fallaba | Parcial: `ci.sh:84` ya ejecuta `audit_advisories.py` (aviso no bloqueante); el venv no incluye `pip-audit`/`osv-scanner` (usan red). P0.18 se cubre con SBOM versionado + `generate_sbom.py --check` |
| 5 | **Corregir `verificar-proyecto.sh` para Windows** (PowerShell nativo o documentar WSL obligatorio) | P1 | 75 | 4 | El verificador principal no ejecuta en Windows nativo | Pendiente y **no verificable en este equipo** (Linux); requiere una sesión Windows. El hook corre anteponiendo `C:\Program Files\Git\bin` al PATH |
| 6 | **Añadir mutation score gate en `verificar-proyecto.sh`** (umbral 0.85 ya configurado) | P1 | 70 | 1 | El gate no estaba en el verificador principal | Hecho: `mutation_check.py --batch --strict --umbral 0.85` (`verificar-proyecto.sh:380`), con guarda anti-recursión |
| 7 | **Documentar dependencia `curses` / `windows-curses`** en `docs/HERRAMIENTAS-Y-FUENTES.md` | P2 | 60 | 0.5 | Un usuario Windows no sabía por qué fallaba la TUI | Hecho (2026-09-25): `docs/HERRAMIENTAS-Y-FUENTES.md` §5.1 |
| 8 | **Añadir test de integración Windows** en `run_tests_isolated.py` (detectar curses faltante) | P2 | 55 | 2 | Prevenir regresión | Parcial: hay tests de degradación sin `curses` (`tui.main` devuelve 1; `tydm_review` fuerza `--report`); la ejecución nativa en Windows no se puede verificar desde Linux |
| 9 | **Generar SBOM automático** (`syft`) en `verificar-proyecto.sh` | P2 | 50 | 3 | P0.18 obligatorio antes de usar deps | Hecho: `check_sbom` (`verificar-proyecto.sh:85-89`) valida la capacidad de regenerar y marca `[SKIP]` visible si falta `syft` |
| 10 | **Migrar `verificar_proyecto.py` a Python** (eliminar bash, portable) | P3 | 40 | 16 | Eliminar dependencia WSL/bash | Hecho (paridad): `scripts/verificar_proyecto.py` replica los checks del `.sh` y existe test de paridad bash/Python |
| 11 | **Añadir coverage real** (`coverage.py`) y gate mínimo en verificador | P3 | 35 | 3 | No había métrica de cobertura | Hecho: gate 85 % en `ci.sh:67` y check en `verificar_proyecto.py`; medido **92 %** el 2026-09-25 |
| 12 | **Benchmark retrieval quality** (recall@10, MRR, nDCG) automatizado | P3 | 30 | 4 | P0.20 requiere métricas cuantitativas | Hecho: `recall@10 >= 0.7` en `verificar-proyecto.sh:386` y `verificar_proyecto.py:630` |
| 13 | **Resolver árboles huérfanos que bloquean el gate `fsck`** (`1c62aa5f` raíz, `0fec6a9b` scripts; creados 2026-09-24 10:44:33) | P0 | 95 | 1-3 | `[FALLO] sin objetos huerfanos en git (fsck)` en `verificar-proyecto.sh --pre-commit` | Resuelto (2026-09-25): `git fsck --no-progress` sin hallazgos en Linux; era un artefacto del entorno Git Bash/Windows, no del repositorio |
| 14 | **Suite aislada falla solo dentro del hook (Git Bash)**: `python3` ahí es Python 3.12.4 de QGIS (`C:\Python314\python3.exe` no existe) | P0 | 90 | 2-4 | `[FALLO] suite de tests (aislada por proceso)` en el hook con 1 test fallido sin identificar | Pendiente y **no verificable en este equipo**: en Linux la suite aislada pasa (evidencia en `docs/LECCIONES-APRENDIDAS.md`, 2026-09-25). Requiere reproducir en Windows/Git Bash |
| 15 | **Temporales versionados en la raíz** (`run_test.py`, `simple_test.py`; a943243 solo ignoró `test_*.py`) | P2 | 40 | 0.2 | `git status` los mostraba; hoy están **dentro** del repo (rastreados) | Pendiente: propuesta de eliminarlos en un commit dedicado; **no ejecutado** (borrado de ficheros rastreados: requiere orden explícita, P0.3) |

## Resumen de impacto (recalculado 2026-09-25)

- **Hechas**: 1, 2, 3, 6, 7, 9, 10, 11, 12, 13 (10 de 15).
- **Parciales**: 4 y 8 (falta el escáner en el venv y la ejecución en Windows nativo).
- **Pendientes reales**: 5, 14 (ambas exigen un entorno Windows) y 15 (borrado que requiere orden).
- **Quién bloquea**: nada bloquea el CI en Linux; lo que queda depende de una sesión Windows o de una decisión del programador.

## Hallazgos de la revisión del 2026-09-25

- **Guardarraíl de latencia en rojo en árbol limpio**: `TestTyDMFast::test_umbral_competitivo`
  medía `bench()` *dentro* del proceso de tests; bajo `pytest --cov` el tracer
  elevaba el p50 a **3214 µs** (>3000 µs del umbral) y el test fallaba sin que
  el motor hubiera empeorado (en proceso real: **413 µs**). Corregido midiendo
  la latencia en un subproceso sin instrumentación (`LSN-043`, `LSN-044`).
- **Cobertura 90 % → 92 %** (3616 sentencias, 302 sin cubrir) con 42 tests
  nuevos: `auto_audit` 83→95 %, `tydm_review` 69→75 %, `index_knowledge` 84→86 %
  y `tui` 82→84 %. Sin cubrir por diseño: UI curses interactiva y backend
  ChromaDB (ver `docs/HERRAMIENTAS-Y-FUENTES.md` §5.1).
- **Mutación `--all`**: medición en una sola pasada registrada en
  `docs/LECCIONES-APRENDIDAS.md` (2026-09-25).

## Criterio de priorización

- **P0**: Bloquea entrega / viola regla P0 / rompe CI en plataforma soportada
- **P1**: Deuda técnica que impide verificación completa / compliance parcial
- **P2**: Mejora DX / prevención / documentación
- **P3**: Arquitectura / métricas avanzadas / nice-to-have