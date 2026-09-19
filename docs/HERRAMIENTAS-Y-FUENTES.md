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
| 3 | Mutation testing opcional (mutmut/cosmic-ray) para medir la fuerza de los tests | Propuesto |
| 4 | `vale` opcional con estilos propios de "claims sin métrica" | Propuesto |
| 5 | Auditoría de frescura P0.18 automatizada (pip-audit/OSV) vía skill `dependency-check` | Propuesto |

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
