# ARQUITECTURA-DETERMINISMO — Determinismo y control de generación en better-ai

> Documento de diseño técnico (adoptado 26-08-2026, tras revisar la propuesta
> "Determinismo y Control de Generación en better-ai" del programador).
> Extiende la capa de protección determinista del SO (deny/ask) hacia el motor de
> inferencia (temperature/top_p) como defensa de tres capas:
> **SO → reglas de texto → inferencia**.

## 1. Objetivo

Reducir la varianza estadística de las respuestas del LLM en tareas de misión
crítica (auditorías, revisiones, compliance) y garantizar que la evidencia
producida (P0.1) sea reproducible entre pasos (P1.10).

## 2. Estado verificado del soporte (28-08-2026) — P0.2, P0.1

Verificado contra la documentación oficial de opencode (docs/agents, última
actualización 26-08-2026), el CLI real (opencode 1.18.25) y ejecuciones reales
del test de determinismo:

| Parámetro | Soporte opencode | Evidencia | Estado |
|---|---|---|---|
| `temperature` (por agente) | ✅ Nativo (JSON + frontmatter MD) | Doc oficial "Options → Temperature" + runtime JSON válido | **Aplicado** |
| `top_p` (por agente) | ✅ Nativo | Doc oficial "Options → Top P" | **Aplicado** |
| `seed` (por agente) | ❌ **No soportado verificablemente** | No aparece en `$schema` oficial (validado 26-08-2026) ni en `opencode run --help` (1.18.25); no existe flag `--seed` ni campo documentado para fijarlo en el frontmatter de agentes primarios | **NO se adopta**. La reproducibilidad se maximiza con `temperature=0.0` y se mide por modelo |
| `steps` (límite de iteraciones) | ✅ Nativo (`steps`; `maxSteps` **DEPRECIADO**) | Doc oficial "Options → Max steps" | No aplicado (no necesario) |
| `model` (por agente) | ✅ Nativo | Doc oficial "Options → Model" | No aplicado (no forzar; sigue config global) |
| `tools:` en frontmatter MD | ⚠️ DEPRECIADO → usar `permission` | Doc oficial "Options → Tools (deprecated)" | Nuestros subagentes ya usan `permission` (correcto) |
| Bloque `agent` en `kilo.json` | ❌ Sin evidencia de soporte | $schema de kilo no verificado | **NO aplicado** — solo en `opencode.json** |

> **Nota (26-08-2026)**: la propuesta original usaba `maxSteps` y
> `tools: {write: false}` en sus ejemplos; ambos están deprecados en la doc
> oficial actual → el plan se ajustó (`steps`/`permission`).
> **Nota (28-08-2026)**: se añade agente primario `audit` con `temperature=0.0`
> para tareas de auditoría/revisión críticas.

## 3. Perfiles de muestreo por rol (aplicado)

| Rol / Agente | temperature | top_p | Tipo de operación |
|---|---|---|---|
| `build` (primario) | 0.3 | 1.0 | Generativa (implementar, refactor) |
| `plan` (primario) | 0.1 | 1.0 | Análisis/planificación |
| `audit` (primario) | 0.0 | 1.0 | Crítica (auditoría determinista) |
| `security-auditor` (subagente) | 0.0 | 1.0 | Crítica (auditoría) |
| `code-reviewer` (subagente) | 0.0 | 1.0 | Crítica (revisión) |
| `compliance-checker` (subagente) | 0.0 | 1.0 | Crítica (compliance) |
| `dependency-auditor` (subagente) | 0.0 | 1.0 | Crítica (supply chain) |
| `cost-optimizer` (subagente) | 0.1 | 1.0 | Análisis |

**Decisión (26-08-2026, programador)**: opción mínima — sin regla P0/P1 nueva;
el determinismo entra como safeguard listado en **P1.9** y como configuración
operativa. No se añade P1.31 porque `temperature`/`top_p` no previenen una clase
de error nueva (la varianza entre pasos ya está cubierta por P0.1 y P1.10) y una
regla extra diluiría las existentes (fuente Anthropic 5: no sobreconstreñir).

## 4. Implementación

### 4.1 Configuraciones afectadas

- `opencode.json` → bloque `agent` (`build`, `plan`, `audit`), sin `model` ni `seed` ni `steps`.
- `.opencode/agents/*.md` → frontmatter `temperature`/`top_p` (5 subagentes).
- `scripts/verificar-proyecto.sh` → check "agente determinista" (valida presencia,
  valores correctos y **ausencia** de `seed`/`maxSteps`; desde 28-08-2026 también
  valida la existencia del agente primario `audit`).
- `kilo.json` / `.kilo/kilo.json` → **NO modificados** (sin evidencia de soporte
  del bloque `agent`; pendiente de verificación con su $schema).

### 4.2 Principio de no-romper coexistentes

- La config global usa `experimental.policies` (deny all + allow list) — sin cambios.
- Los subagentes mantienen `permission` (edit/bash deny) — sin cambios.

## 5. Test de determinismo (`scripts/test-determinism.py`)

Alineado a la propuesta (EMR ≥ 95 %) con las reglas del proyecto:

- 10 ejecuciones del mismo prompt sintético complejo **por defecto** (`--runs 10`).
- Agente primario por defecto: `audit` (`temperature=0.0`). Sobreescribible con `--agent`.
- EMR (Exact Match Ratio) tras normalización; umbral de varianza 5 %: **fail fast**.
- `--model` (por defecto `opencode-go/deepseek-v4-flash`; si no está disponible, el
  programador puede indicar otro modelo permitido).
- **Falla explícito** si la API devuelve error (nunca "skip" silencioso, P0.1/P1.19).
- Reporta tiempo y coste estimado (P0.19).
- **Ejecución (28-08-2026)**: `test-determinism.py` actualizado para parsear el
  formato de eventos de opencode 1.18.25 (`type:text`). Con el modelo gratuito
  `opencode/mimo-v2.5-free` y agente `audit` se obtuvo **EMR 33,33 %** (3 runs),
  por debajo del umbral del 95 %. Esto no invalida el safeguard: demuestra que
  la reproducibilidad depende fuertemente del modelo/proveedor y justifica medirla
  antes de usar un modelo para auditorías críticas. Los modelos de pago configurados
  (`opencode-go/deepseek-v4-flash`) devolvieron `APIError` por límite de servicio;
  no se reporta EMR inventado (P0.1).

## 6. Decisión sobre `seed` (cerrada el 28-08-2026)

1. Se verificó que `seed` **no está documentado ni expuesto por el CLI** de opencode
   1.18.25 (no existe flag `--seed`; no aparece en `$schema` oficial).
2. No hay mecanismo verificable para fijar la semilla en el frontmatter de agentes
   primarios ni en `opencode.json`.
3. **Decisión**: `seed` NO se adopta. El proyecto no reclama reproducibilidad bit a
   bit; la reduce al máximo con `temperature=0.0` (agente `audit`) y mide la varianza
   real con `test-determinism.py`.
4. Si en el futuro opencode documenta soporte nativo de `seed`, se reevaluará con el
   protocolo: medir EMR con y sin `seed`; solo adoptar si mejora estadísticamente.

## 7. Limitaciones declaradas

- `temperature=0.0` **no** garantiza salidas bit a bit (FP no asociativo en GPUs,
  arquitecturas MoE; doc oficial de proveedores). Sin soporte verificable de `seed`
  en opencode CLI, no se puede aspirar a reproducibilidad perfecta; se maximiza lo
  posible y se mide por modelo.
- Los subagentes Markdown heredan el modelo del agente principal (doc oficial);
  el frontmatter no fija modelo → el perfil de determinismo aplica al sampling,
  no al router de modelos.
- `kilo.json` sin soporte verificado del bloque `agent` (§2).
- Los modelos gratuitos disponibles durante la verificación mostraron alta varianza
  (EMR 33,33 %); para auditorías críticas se recomienda usar el agente `audit` y,
  si el presupuesto lo permite, validar el EMR del modelo de pago elegido antes de
  confiar en él para evidencia.

## 8. Fuentes verificadas (28-08-2026)

- opencode Docs — Agents (Options: Temperature, Top P, Max steps/steps, Model,
  Tools deprecated, Additional): https://opencode.ai/docs/agents/
- opencode CLI 1.18.25 real (`opencode run --help`): sin flags `--seed`/
  `--temperature`; la configuración se carga desde `opencode.json`.
- Ejecuciones reales de `scripts/test-determinism.py` el 28-08-2026 contra
  `opencode/mimo-v2.5-free` (agente `audit`) y `opencode-go/deepseek-v4-flash`.
- Propuesta del programador: "Determinismo y Control de Generación en better-ai"
  (PDF, 5 págs, revisada 26-08-2026).
