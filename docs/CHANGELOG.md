# Changelog

Todos los cambios relevantes de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y
el versionado es [SemVer](https://semver.org/lang/es/) para la API pública
(scripts y tools MCP) y CalVer (AAAA.MM) para reglas y documentación, según
`GOVERNANCE.md`. Las entradas se derivan de los commits convencionales.

> Estado: el proyecto **aún no ha cortado una release etiquetada**. Todo lo
> listado bajo `Unreleased` está en `main` y verificado con
> `bash scripts/verificar-proyecto.sh`.

## [Unreleased]

### Añadido

- Framework de 4 pilares: requisitos (`.docs/requirements/`, REQ-001),
  conocimiento (`.docs/knowledge/`, REQ-002), lecciones
  (`.docs/lessons/<año>.yaml`, REQ-003) y control de sesgos/falacias
  (`docs/decisions/`, REQ-013).
- Servidor MCP local por stdio (`scripts/mcp_server.py`, REQ-004), endurecido
  con límites de entrada y auditoría JSONL sin contenidos (REQ-007).
- Herramientas del ecosistema: `doc_validator.py` (REQ-001),
  `index_knowledge.py` con backend ChromaDB y reserva JSON TF-IDF (REQ-002),
  `lessons_extractor.py` (REQ-003), `tui.py` (REQ-006), `setup.sh` (REQ-008),
  `ci.sh` (REQ-009), `verificar-proyecto.sh` (REQ-010),
  `adr_validator.py` (REQ-013), `auto_audit.py` (REQ-014),
  `mutation_check.py` (REQ-015), `tydm_review.py` (REQ-016),
  `diagnostico.py` (REQ-017), `tydm_calibration_merge.py` (REQ-018),
  `run_tests_isolated.py` (REQ-026).
- Motor MDT liviano con llama.cpp (`scripts/tydm_llama.py`, REQ-011) y su
  integración con los tres pilares (REQ-012). Experimental: accuracy 0.646.
- Verificador determinista (REQ-022) y ADRs obligatorios con pre-mortem,
  alternativas reales y métricas (REQ-023).
- Auditoría de cadena de suministro: lock con hashes
  (`requirements-optional.lock`) y severidad (REQ-020).
- Guardarraíles de agentes: 304 patrones de permiso bash (218 `deny`,
  85 `ask`, 1 `allow`) y bloqueo de lectura/edición de claves y credenciales.
- Subagentes de solo lectura: `code-reviewer`, `security-auditor`,
  `compliance-checker`, `cost-optimizer`, `dependency-auditor`
  (`.opencode/agents/`, `.kilo/agents/`).
- Gobernanza y comunidad: `GOVERNANCE.md`, `CONTRIBUTING.md`,
  `docs/THREAT-MODEL.md`, `docs/ALCANCE.md`, `SECURITY.md`,
  `CODE_OF_CONDUCT.md`, `CHECKLIST.md`.
- Instrumentación opcional con OpenTelemetry en el verificador (P1.30) y
  wrappers anti-RCE `safe-curl`/`safe-wget` (P0.8).
- Sonda de comportamiento de guardarraíles en runtime
  (`scripts/probar_policies.py`, REQ-031) con 7 tests deterministas.
- Instrumentación opt-in de tiempos por check del verificador
  (`BETTER_TIMING=1`, REQ-030) con línea base medida (333 s / 55 checks).
- Puente opcional StrictDoc para el Pilar 1 (REQ-032, ADR-011):
  `scripts/strictdoc_bridge.py` stdlib (13 tests),
  `.docs/requirements/puente-strictdoc.sdoc` (SDOC-001/002 con Mermaid),
  check `trazabilidad StrictDoc (.sdoc)` en ambos verificadores y
  `requirements-strictdoc.txt` aislado (pip-audit 0 vulns, 2026-10-01).
- Capa de export StrictDoc reproducible (REQ-032, ADR-011):
  `requirements-strictdoc.lock` (hashes), `scripts/setup_strictdoc.sh`
  (venv aislado + auditoria P0.18), `scripts/strictdoc_export.py`
  (export/`--check`/`--smoke`) y check opcional `export HTML StrictDoc (sonda
  E2E)` con `[SKIP]` en ambos verificadores (2026-10-03).
- Cierre verificado de las 11 lecciones abiertas (LSN-045..054 y 056), con
  evidencia por leccion, y 2 lecciones nuevas: LSN-060 (los KPIs `n/d`
  ocultaban que `ci.sh` nunca completaba) y LSN-061 (salida no determinista de
  strictdoc) (2026-10-03).
- Check `YAML valido (workflows, pre-commit, lecciones, vale)` en ambos
  verificadores (paridad; PyYAML opcional, LSN-048 resuelta).
- Sonda `--repro` de `scripts/strictdoc_export.py`: dos exports normalizados y
  comparacion sha256 (102 archivos identicos en 2 corridas).

### Cambiado

- La suite de tests se ejecuta aislada por proceso por defecto (REQ-026) para
  evitar OOM con las dependencias opcionales; alternativa in-process con
  `python3 -m unittest discover -s tests -q`.
- Gate de cobertura del CI ajustado a ≥ 85% (medido 88% el 23-09-2026 con
  `pytest --cov=scripts`; `.coveragerc` omite los módulos que la suite solo
  ejercita como subproceso).
- Dashboard de KPIs (REQ-024) implementado: `docs/health.md` regenerado por
  `scripts/ci.sh` con 5 KPIs, metas y tendencia; REQ-025 (backfill de ADR)
  pasa a **Implementado** (borradores con idempotencia por titulo).
- Renombrado el motor "Jev" a **MDT** (modelos de decisión tipados; TyDM en
  inglés): módulos `scripts/tydm_*.py`, variables de entorno `TYDM_*` y
  artefactos `tydm_*.json` (ADR-010). Los nombres propios de terceros
  (OpenJev, https://github.com/razorback16/openjev) se conservan.
- Suite de tests dividida en modulos tematicos (`tests/test_pilares.py`,
  `test_verificador.py`, `test_mcp_tui.py`, `test_tydm.py`,
  `test_cadena_suministro.py`, `test_portabilidad.py`); `test_ecosistema.py`
  queda como integracion del hook. Consumidores actualizados (targets de
  mutacion, coverage, `auto_audit`) y 7 patrones `assertEqual(f(x), f(x))`
  reescritos con variable intermedia.

### Corregido

- `SECURITY.md` ya no cita etiquetas inexistentes (`v*`) como soportadas.
- mypy: parametro de tipo faltante en tests (`CompletedProcess[str]`),
  latente y visible solo al ejecutar `ci.sh` completo (LSN-060).
- Salida de strictdoc normalizada (UUIDs, timestamp e indice de busqueda
  ordenado) para reproducibilidad byte a byte (LSN-061).

- Verificador: el check de SBOM con syft se omite cuando la herramienta no
  está disponible (REQ-020) y verifica regeneración real en directorio
  temporal cuando lo está; `mutation_check` exige el resumen del runner
  ("Ran ") con rc==0 para no confundir un runner interrumpido con un
  superviviente (batch 187/187, 25-09-2026).
- Referencias rotas de `GOVERNANCE.md`: se crean `SECURITY.md` y este
  CHANGELOG, antes citados sin existir.
- Trazabilidad IA y deriva documental (REQ-019); hook `commit-msg` con
  `Assisted-by`.
- Recolección de tests de `pytest` acotada con `pytest.ini` (`testpaths=tests`)
  para no ejecutar scripts manuales que gastan tokens (P0.19).
- `verificar_proyecto.py` abortaba entero en máquinas sin ruff instalado
  (`check_ruff` fuera del wrapper `check()`): ahora omite con `[SKIP]`
  (REQ-029, LSN-055).
- Fugas de recursos en la suite (4 `ResourceWarning` por corrida): test
  zombie sin recolectar (`proc.wait()`) y 41 `open()` sin cerrar en el
  verificador migrados a `Path.read_text` (REQ-033, pruebas 163-168).

### Seguridad

- Único `eval`/`exec` esperado: el patrón del propio verificador; prohibido en
  el resto de scripts (P1.26, P0.8).
- Auditoría por commit de secretos, IPs, rutas de usuario y datos personales
  (P0.6, P0.9, P0.10).
- Advisories **abiertos** sin parche en dependencias opcionales
  (chromadb 1.5.9, diskcache 5.6.3). El backend stdlib por defecto no los
  instala; detalle y mitigación en `README.md` y `docs/ALCANCE.md`.
- Hallazgo verificado (2026-10-01): `experimental.policies` no impide el uso
  de proveedores denegados en runtime en opencode 1.18.32 (sonda REQ-031,
  pruebas 146-148); la restricción efectiva hoy son las credenciales mínimas
  y la regla de texto (MEJORAS #22, LSN-056). Los 218 `deny` de bash sí se
  cumplen en runtime (red-team, prueba 149).
