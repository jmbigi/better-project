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
  `mutation_check.py` (REQ-015), `jev_review.py` (REQ-016),
  `diagnostico.py` (REQ-017), `jev_calibration_merge.py` (REQ-018),
  `run_tests_isolated.py` (REQ-026).
- Motor Jev liviano con llama.cpp (`scripts/jev_llama.py`, REQ-011) y su
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

### Corregido

- Referencias rotas de `GOVERNANCE.md`: se crean `SECURITY.md` y este
  CHANGELOG, antes citados sin existir.
- Trazabilidad IA y deriva documental (REQ-019); hook `commit-msg` con
  `Assisted-by`.
- Recolección de tests de `pytest` acotada con `pytest.ini` (`testpaths=tests`)
  para no ejecutar scripts manuales que gastan tokens (P0.19).

### Seguridad

- Único `eval`/`exec` esperado: el patrón del propio verificador; prohibido en
  el resto de scripts (P1.26, P0.8).
- Auditoría por commit de secretos, IPs, rutas de usuario y datos personales
  (P0.6, P0.9, P0.10).
- Advisories **abiertos** sin parche en dependencias opcionales
  (chromadb 1.5.9, diskcache 5.6.3). El backend stdlib por defecto no los
  instala; detalle y mitigación en `README.md` y `docs/ALCANCE.md`.
