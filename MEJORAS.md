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
| 15 | **Temporales versionados en la raíz** (`run_test.py`, `simple_test.py`; a943243 solo ignoró `test_*.py`) | P2 | 40 | 0.2 | `git status` los mostraba; hoy están **dentro** del repo (rastreados) | Hecho (2026-09-26): `git rm run_test.py simple_test.py` con orden explícita del programador; verificado que solo se citaban en esta lista |
| 16 | **Adopción portable rota**: `init.sh` copiaba `verificar-proyecto.sh` (repo-específico) sin su toolchain; proyecto externo quedaba con 9 OK/27 FALLOS y hook bloqueante | P1 | 85 | 3 | Hallazgo 2026-09-26 reproducido en proyecto externo temporal | Hecho (2026-09-26): tooling portable + `scripts/portable_verifier.py` + `doc_validator --ignore` (REQ-028); E2E externo 5 OK/0 fallos |

## Resumen de impacto (recalculado 2026-09-25)

- **Hechas**: 1, 2, 3, 6, 7, 9, 10, 11, 12, 13, 15, 16 (12 de 16).
- **Parciales**: 4 y 8 (falta el escáner en el venv y la ejecución en Windows nativo).
- **Pendientes reales**: 5 y 14 (ambas exigen un entorno Windows).
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

## Hallazgos de la revisión del 2026-09-26

- **MCP `run_verification` inviable**: el timeout síncrono era de 300 s y la
  verificación completa mide ~357 s (medido con `time`), por lo que toda
  llamada fallaba (`-32001 Request timed out` en el cliente). Ahora se lanza en
  segundo plano con PID + log (`.docs/.storage/verification-last.log`) y guarda
  de no duplicación (REQ-004/P1.34); cubierto por tests async en
  `TestMCPServer` que no ejecutan la suite real.
- **OWASP**: la edición 2026 citada por el proyecto existe en el repositorio
  oficial (`GenAI-Security-Project/GenAI-LLM-Top10/2026/final`), así que el
  mapeo es correcto; el malentendido vino de que `genai.owasp.org` aún muestra
  la edición 2025. Se anotó la edición en las 4 referencias que mezclaban
  numeración 2025 (README #35, CHECKLIST, SECURITY y REGLAS-COMPLETAS,
  System Prompt Leakage).
- **GitHub Actions**: la política real es "sin cuenta requerida, sin pagos;
  verificación local" (aclarada por el programador). Documentada en `AGENTS.md`
  y `docs/AGENT-ARCHITECTURE.md`; corregido el artefacto roto de
  `.github/workflows/ci.yml` (subía `.docs/.storage/tydm_review.json`, que
  `audit_advisories.py` nunca escribe). Hecho (2026-09-26): instalación de syft
  con versión fijada (v1.52.0) + SHA256 oficial para Linux y Windows,
  verificados descargando ambos artefactos; se eliminó `curl | sh` y la matriz
  parcial (antes solo Python 3.11 instalaba syft); `permissions: contents: read`.
  Ejecución real del workflow no verificable desde este equipo.
- **KPI desactualizado**: `docs/health.md` reportaba "REQs trazados 25/25".
  Hecho (2026-09-26): `bash scripts/ci.sh` regeneró el dashboard con 26/26,
  mutación 1.000, cobertura 91.77 % (gate 85 %), onboarding 156 s y CI 380 s.
- **Adopción portable (REQ-028)**: `init.sh` copiaba el verificador específico
  del framework sin su toolchain (9 OK/27 FALLOS en el destino; el hook
  bloqueaba commits). Ahora copia tooling portable a `scripts/`, genera un
  wrapper y un verificador genérico que excluye el propio tooling del escaneo
  de trazabilidad. E2E en proyecto externo temporal: 5 OK / 0 FALLOS.

## Hallazgos de la revisión externa del 2026-09-27

| # | Mejora | Prioridad | Valor (%) | Esfuerzo (h) | Evidencia | Estado |
|---|--------|-----------|-----------|--------------|-----------|--------|
| 17 | **Test de comportamiento de `experimental.policies`** (proveedor fuera de la allow-list rechazado en runtime) y re-ejecución local del red-team de los 304 deny (hoy heredado de better-ai) | P1 | 80 | 3-4 | Auditoría externa 2026-09-27 (LSN-051); `PRUEBAS.md` no cubre policies y su red-team es del repo upstream | Hecho (2026-10-01): red-team bash `deny` verificado en runtime (`rm -rf` bloqueado, prueba 149) y sonda reproducible `scripts/probar_policies.py` (REQ-031); la sonda de `policies` destapó el hueco #22 (LSN-056) |
| 18 | **Coherencia ollama**: el texto permitía modelos locales para la matriz de pruebas pero `policies` los bloqueaba | P1 | 90 | 0.5 | Auditoría externa 2026-09-27 (LSN-050): allow `ollama` en `opencode.json`, `kilo.json` e `init.sh`; checks bash/Python del verificador y `CONTRIBUTING.md` actualizados | Hecho (2026-09-27); reverificado en `verificar-proyecto.sh` |
| 19 | **Aritmética de la rúbrica**: decía "Peso total: 100%" con pesos que suman 110 | P2 | 40 | 0.2 | Auditoría externa 2026-09-27 (LSN-052); normalización explícita en `.docs/rubric-evaluacion.md` | Hecho (2026-09-27) |
| 20 | **Cifra de accuracy sin backend**: ALCANCE decía 0.646 y README/TDM 0.802 (llama vs fast) | P2 | 40 | 0.2 | Auditoría externa 2026-09-27 (LSN-053); `docs/ALCANCE.md` ahora nombra backend y set | Hecho (2026-09-27) |
| 21 | **Guard de idempotencia bloqueado por un zombie**: `run_verification` no recolectaba al hijo y `os.kill(pid, 0)` responde también en `<defunct>`; tras la primera verificación el MCP decía "ya había una en curso" con un PID muerto | P1 | 85 | 0.5 | Auditoría externa 2026-09-27 (LSN-054): `ps` mostró el PID 665983 `<defunct>` y el MCP rechazó el relanzamiento; `_pid_activo` + `waitpid(WNOHANG)` + hilo reaper; test `test_verification_running_ignora_zombie_y_lo_recolecta` | Hecho (2026-09-27) |

## Criterio de priorización

- **P0**: Bloquea entrega / viola regla P0 / rompe CI en plataforma soportada
- **P1**: Deuda técnica que impide verificación completa / compliance parcial
- **P2**: Mejora DX / prevención / documentación
- **P3**: Arquitectura / métricas avanzadas / nice-to-have

## Hallazgos de la revisión del 2026-10-01

Ronda ejecutada en equipo Linux limpio (sin ruff ni syft instalados; opencode
1.18.32). Evidencia completa: `docs/PRUEBAS.md` ronda 37 (pruebas 142-152).

| # | Mejora | Prioridad | Valor (%) | Esfuerzo (h) | Evidencia | Estado |
|---|--------|-----------|-----------|--------------|-----------|--------|
| 22 | ⚠️ **`experimental.policies` no se cumple en runtime (opencode 1.18.32)**: con `deny provider.use *` (aislado a nivel proyecto Y a nivel global) el proveedor denegado ejecuta igualmente; el schema oficial sigue vigente, así que el hueco es de enforcement, no de config | P1 | 90 | 0.5 por reintento | Pruebas 146-148, LSN-056 | Ticket: mitigación efectiva hoy = credenciales mínimas + regla de texto; re-probar con `scripts/probar_policies.py provider` tras cada actualización de opencode |

Cerrados en la misma ronda (con REQ propio y tests de regresión):

- **REQ-029**: el verificador Python abortaba entero en máquina sin ruff
  (`FileNotFoundError` fuera del wrapper `check()`); fix `shutil.which` + 2
  tests que simulan ausencia/presencia (pruebas 142-144, LSN-055).
- **REQ-030**: instrumentación opt-in de tiempos por check (`BETTER_TIMING=1`)
  con salida por defecto byte-idéntica; línea base medida registrada en la
  prueba 145.
- **REQ-031**: `scripts/probar_policies.py` (sonda manual runtime, 7 tests
  deterministas) + red-team de `permission.bash` en runtime: **los 218 `deny`
  sí se cumplen** (`rm -rf` bloqueado por regla, temporal intacto, prueba 149).