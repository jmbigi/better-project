# Herramientas y fuentes de referencia (calidad y control de sesgos)

> Documento vivo del **Pilar 4**. Recoge qué herramientas externas podemos
> adoptar y qué fuentes consultar para mejorar la calidad de better-project y de
> los proyectos que sigan sus reglas. Investigación inicial: 2026-09-19.
>
> **Advertencia anti-sesgo**: adoptar una herramienta "porque la usa todo el
> mundo" es *ad populum* y "porque es nueva" es *ad novatem*. Cada adopción debe
> registrarse como ADR (≥ 2 alternativas) y pasar P0.18 (SBOM + escaneo +
> licencia) antes de entrar.

## 1. Criterios de selección

1. Open source y gratuita.
2. Local/offline siempre que sea posible (sin nube).
3. Licencia compatible con GPL-3.0-or-later.
4. Preferir stdlib y `pre-commit`; evitar dependencias pesadas.
5. Mantenida y con procedencia verificable (hash/firma, SLSA).
6. Justificar el encaje con un ADR; si no aporta, retirarla.

## 2. Herramientas verificadas en esta investigación

| Herramienta | Para qué | Licencia | Encaje |
|---|---|---|---|
| **Vale** (vale-cli/vale) | Linter de prosa markup-aware; reglas propias (claims, muletillas, voz pasiva); corre en editor y CI | MIT | Alto: complementa `auto_audit sesgos`; binario local |
| **Hypothesis** | Property-based testing: genera casos límite que no se te ocurren | por verificar | Alto: endurece P1.1/P1.21 |
| **Giskard** (v3) | Evals y red teaming de agentes LLM; calidad RAG; alineado a OWASP LLM | Apache-2.0 | Alto si se prueban agentes; pesado (Python 3.12+) |
| **OpenSSF Scorecard** | Métricas de salud de seguridad de un repositorio | Apache-2.0 | Medio: requiere token y red; auditoría puntual |
| **SLSA** | Niveles de integridad y procedencia de artefactos | Community Specification | Medio: guía para releases firmados (hoy no hay releases) |

## 3. Herramientas candidatas (licencia/versión por verificar antes de adoptar)

- **Calidad de código y tests**: Ruff, mypy/pyright, coverage, **mutmut** o
  **cosmic-ray** (mutation testing: detecta tests que no pueden fallar),
  vulture (código muerto), radon (complejidad), jscpd (duplicación),
  Semgrep/CodeQL/Bandit (SAST).
- **Cadena de suministro**: pip-audit, OSV-Scanner, Syft/Grype/Trivy,
  pip-licenses, CycloneDX, detect-secrets/gitleaks.
- **Sesgo y fairness (si el proyecto anfitrión entrena modelos)**: Fairlearn,
  AI Fairness 360, Evidently, Deepchecks, SHAP, LIME, Aequitas.
- **Agentes LLM**: promptfoo, garak, PyRIT, Ragas (RAG), DeepEval,
  NeMo Guardrails.
- **Observabilidad y coste de agentes**: OpenTelemetry GenAI, Langfuse,
  Phoenix.
- **Documentación**: markdownlint, lychee (enlaces), cspell, alex (lenguaje
  inclusivo).
- **Proceso y decisiones**: DORA y SPACE (métricas), Renovate/Dependabot
  (dependencias), adr-tools / log4brains / MADR (registro de ADR).

## 4. Fuentes y estándares de referencia

| Fuente | Aporte | Acceso |
|---|---|---|
| **NIST AI RMF 1.0** y **NIST AI 600-1** (GenAI Profile) | Marco de gestión de riesgo IA (Govern/Map/Measure/Manage) | Público (nist.gov) |
| **ISO/IEC 42001:2023** | Sistema de gestión de IA (AIMS), certificable | Estándar de pago (iso.org/standard/42001) |
| **OWASP GenAI Security Project / Top 10 LLM (2025)** | Riesgos de aplicaciones LLM; ya mapeado en `docs/REGLAS-COMPLETAS.md` §7 | Público |
| **MITRE ATLAS** | Tácticas adversarias contra sistemas de IA/ML | Público |
| **SLSA** y **OpenSSF Scorecard** | Integridad de la cadena de suministro y salud del repo | Público |
| ISO/IEC/IEEE 29148 (requisitos), ISO/IEC 25010 (calidad), ISO/IEC/IEEE 42010 (arquitectura) | Requisitos, modelo de calidad, descripción arquitectónica | Estándares de pago |
| EU AI Act, UNESCO (ética de la IA), ACM Code of Ethics | Gobernanza y ética | Público |
| Kahneman (sesgos), Tversky-Kahneman 1974, Tetlock (calibración), Gawande (checklists), Nygard (ADR), Klein (pre-mortem) | Base conceptual del Pilar 4 | Bibliografía |
| Guo 2017, Nixon 2019, Kadavath 2022, Kumar 2019 | Calibración de probabilidades (REQ-011) | arXiv |

## 5. Plan de adopción en better-project

| Prioridad | Acción | Estado |
|---|---|---|
| 1 | `scripts/auto_audit.py` (sesgos, evidencias, decisiones, tests, IA) + integración en el verificador | Implementado (REQ-014) |
| 2 | `docs/HERRAMIENTAS-Y-FUENTES.md` (este documento) referenciado desde README/AGENTS | Implementado |
| 3 | Chequeo de mutaciones stdlib (`scripts/mutation_check.py`, REQ-015); `mutmut`/`cosmic-ray` como alternativas maduras | Implementado (2026-09-19) |
| 4 | Linter de prosa `vale` con estilo propio de "claims sin métrica" (`.vale.ini` + `.vale/styles/BetterProject/Claims.yml`) | Implementado (2026-09-19) |
| 5 | Re-escaneo de dependencias (`auto_audit vulns` con pip-audit/osv-scanner) | Implementado (2026-09-19) |
| 6 | Lint de codigo `ruff` (config `ruff.toml`, E/F/W sin E501); opcional, se ejecuta en el verificador si esta instalado | Implementado (2026-09-20) |

**Hallazgo del re-escaneo (2026-09-20)**: `auto_audit vulns` detectó 5
advisories sin parche: 4 en chromadb 1.5.9 y 1 en diskcache 5.6.3 (transitiva).
Son dependencias opcionales y el riesgo se acepta para uso **local embebido**
(LSN-007); el backend stdlib sigue siendo el recomendado por defecto. SBOM
vigente: `docs/SBOM-2026-09-20.cdx.json` (CycloneDX, 119 componentes, 5
advisories), regenerado con `pip-audit -f cyclonedx-json -r
requirements-optional.txt`; las versiones directas están fijadas en
`requirements-optional.txt` (P0.18). Pendiente: lock con hashes de dependencias
transitivas.

**Evaluación de `mutmut` (2026-09-19)**: se probó `mutmut` 3.6 en una copia
aislada; exige configuración específica de pytest y su recolección de stats
falla sobre esta suite unittest (`BadTestExecutionCommandsException`), aunque
pytest 9 sí recoge `TestADRValidator` por separado (14 passed). Se mantiene el
chequeo stdlib `scripts/mutation_check.py`; `cosmic-ray` queda sin evaluar
(LSN-015).

**Evaluación de `cosmic-ray` (2026-09-19)**: `cosmic-ray` 8.7.0 (MIT) se
instaló en `.venv` y funcionó en copia aislada. Config mínima:

```toml
[cosmic-ray]
module-path = "scripts/adr_validator.py"
timeout = 30.0
test-command = ".venv/bin/python -m unittest tests.test_ecosistema.TestADRValidator"
[cosmic-ray.distributor]
name = "local"
```

```bash
.venv/bin/cosmic-ray init cr.toml session.sqlite
.venv/bin/cosmic-ray exec cr.toml session.sqlite
.venv/bin/cr-report session.sqlite
```

Resultado: **160 mutantes, 124 eliminados (77.5 %)**; los 36 supervivientes son
relativos a ese único objetivo de test (con la suite completa bajarían). Es más
rico que `mutation_check.py` (operadores como `ZeroIterationForLoop`) y se adopta
como herramienta **opcional de desarrollo**; `mutmut` queda descartado (LSN-015).

**Medición de calidad de la suite (2026-09-20)**: `coverage 7.10.6` sobre la
suite (240 tests) da **81 %** de cobertura de líneas en `scripts/` (2747
sentencias, 510 sin cubrir). Tras los tests de integración, `mcp_server.py`
(99 %) y `tui.py` (95 %) dejan de ser zonas bajas; quedan `analyze_shell.py`
(62 %), `jev_pillars.py` (62 %), `jev_calibration.py` (64 %), `jev_review.py`
(71 %) e `index_knowledge.py` (72 %) por ramas opcionales (chromadb/CLI).

`mutation_check.py` (REQ-015, heurística stdlib). El modo `--batch` mide varios
módulos y agrega el score ponderado por mutantes (integrado en `scripts/ci.sh`
con `--strict --umbral 0.8`, ~110 s):

| Módulo | Mutantes | Score |
|---|---|---|
| adr_validator | 16 | **1.00** |
| doc_validator | 22 | **1.00** |
| auto_audit | 40 | **1.00** |
| diagnostico | 12 | **1.00** |
| mcp_server | 40 | **1.00** |
| lessons_extractor | 14 | **0.79** |
| index_knowledge | 29 | **0.97** |
| **Batch (global ponderado)** | **173** | **0.98** |

Otros módulos medidos a demanda alcanzan **1.00** (`mcp_server`, `jev_review`,
`jev_pillars`) y `jev_calibration_merge` **0.91**. Los supervivientes restantes
son en su mayoría equivalentes (defaults de flags, guarda `__main__`, `parents`/
`exist_ok` cuando el directorio ya existe) o rutas no ejercitables sin
`chromadb` (dependencia opcional). La mutación no entra en el pre-commit
(medición a demanda); el modo `--batch` sí corre en el CI local.

**Linter de prosa `vale` (2026-09-19)**: instalado con `go install
github.com/vale-cli/vale/v3/cmd/vale@latest` (MIT, usuario, sin sudo). Config en
`.vale.ini` y estilo local `.vale/styles/BetterProject/Claims.yml` (claims sin
métrica: garantías absolutas, porcentajes totales, superlativos). Uso:

```bash
vale README.md docs .docs    # rutas explícitas: 'vale .' rompe por el
                             # frontmatter YAML de .kilo/.opencode (E201)
```

Es **opcional**: no entra en el verificador (puede no estar instalado en todos
los entornos). Complementa `auto_audit sesgos` (heurística stdlib).

## 6. Para los proyectos que sigan estas reglas

- Copiar `scripts/auto_audit.py` (stdlib puro, sin dependencias) y añadir el
  subcomando al verificador local.
- Adoptar los "perfiles" mínimos por lenguaje: lint + tests + mutation testing
  + SBOM/vuln scan + linter de prosa.
- Registrar cada adopción como ADR y mantener este documento como referencia
  viva de licencias y encaje.

## 7. Límites declarados

- Las listas de "candidatas" no están verificadas en detalle: **no adoptar sin
  comprobar licencia, versión y procedencia** (P0.2/P0.18).
- Las herramientas de sesgo/fairness de la sección 3 aplican a proyectos con
  modelos predictivos propios; better-project no entrena modelos.
- La auditoría de sesgos es heurística y asiste la revisión humana (P1.15).
