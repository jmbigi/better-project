# Rúbrica de Evaluación Explicita better-project

**Objetivo**: Transformar la evaluación de "opinión con formato numérico" a evaluación reproducible con criterios, pesos y baselines externas.

## 1. Pesos por Categoría

| Categoría | Peso | Justificación |
|-----------|------|---------------|
| **Estructura y Organización** | 15% | Hecho verificable: 26 scripts, 26 REQ, árbol sin huérfanos. |
| **Reglas y Compliance** | 20% | 62 reglas P0/P1/P2 presentes y coherentes con REGLAS-COMPLETAS.md. |
| **Prácticas de Seguridad** | 15% | 304 patrones bash (218 deny, 85 ask, 1 allow); sin secretos expuestos. |
| **Documentación** | 10% | README 50 errores, AGENTS.md completo, CHECKLIST.md, ADRs, sesgos/falacias. |
| **Tooling y Automatización** | 15% | Pipeline completo (`verificar-proyecto.sh`), MCP locales, hooks pre-commit. |
| **Cobertura de Tests** | 20% | Mutation score, coverage real, suite verde. **P0.19 bloqueante si rota.** |
| **Configuración** | 10% | kilo.json/opencode.json consistentes, agentes deterministas, políticas correctas. |
| **Gestión de Dependencias** | 5% | Deps opcionales documentadas con advisories; stdlib fallback. |

**Peso total: 100%**

---

## 2. Criterios de Puntuación por Categoría

### Estructura y Organización (15% máximo)
| Score | Criterio |
|-------|----------|
| 15/15 | 26 scripts Python presentes en `scripts/`, 26 REQ en `.docs/requirements/`, sin archivos huérfanos, árbol coherente. |
| 12/15 | Estructura mayormente presente: 20+ scripts, 20+ REQ, algunos archivos por verificar. |
| 8/15 | Estructura incompleta: <20 scripts o <20 REQ, archivos faltantes significativos. |
| 0/15 | Estructura vacía o inválida. |

### Reglas y Compliance (20% máximo)
| Score | Criterio |
|-------|----------|
| 20/20 | 62 reglas P0/P1/P2 presentes y coherentes con REGLAS-COMPLETAS.md. Auto-evaluación transparente (P1.31). |
| 16/20 | 45+ reglas presentes, coherentes, con evaluación honesta de limitaciones. |
| 12/20 | 30+ reglas presentes, algunas inconsistencias o sin evaluación externa. |
| 0/20 | Sin reglas o reglas que violan P0 internamente sin justificación. |

### Prácticas de Seguridad (15% máximo)
| Score | Criterio |
|-------|----------|
| 15/15 | 304 patrones bash correctos (218 deny, 85 ask, 1 allow), sin secretos/credentials expuestos, SBOM documentado. |
| 12/15 | 250+ patrones correctos, algunos secrets documentados con riesgo aceptado, SBOM parcial. |
| 8/15 | <250 patrones, secrets sin documentar, riesgo no evaluado. |
| 0/15 | Sin modelo de seguridad o secrets hardcodeados sin mitigación. |

### Documentación (10% máximo)
| Score | Criterio |
|-------|----------|
| 10/10 | README 50 LLM errors, AGENTS.md completo, CHECKLIST.md, ADRs, SESGOS-Y-FALACIAS.md, todos los REQ docs. |
| 8/10 | Documentación mayormente presente, algunos sections faltantes o parcialmente completos. |
| 5/10 | Documentación mínima, gaps significativos en áreas críticas. |
| 0/10 | Sin documentación o documentación falsa/misleading. |

### Tooling y Automatización (15% máximo)
| Score | Criterio |
|-------|----------|
| 15/15 | `verificar-proyecto.sh` completo y funcional, MCP servers (context7, gh_grep, sentry, better-project) operativos, hooks pre-commit configurados. |
| 12/15 | Herramientas principales funcionales, algunos checks condicionales/lite-mode. |
| 8/15 | Herramientas básicas operativas, gaps en pipeline de verificación. |
| 0/15 | Sin herramientas de verificación o todas rotas. |

### Cobertura de Tests (20% máximo) — **P0.19 bloqueante**
| Score | Criterio |
|-------|----------|
| 20/20 | Suite de tests verde (python3 -m unittest discover -s tests -q return code 0), mutation score ≥ 80%, coverage ≥ 85%. |
| 16/20 | Suite mayormente verde: algunos tests rotos pero con justificación documentada y ruta de corrección. |
| 12/20 | Suite parcialmente verde: >50% tests pasan, mutation score ≥ 50%, coverage ≥ 70%. |
| 8/20 | Suite mayormente rota: <50% tests pasan, sin mutation score, sin coverage documentada. **P0.19: bloquea entrega sin justificación.** |
| 4/20 | Suite gravemente rota: <25% tests pasan, tests fuera de clase sin validar (REQ-026). |
| 0/20 | Sin suite de tests o todos los tests fallan sin recuperación. |

### Configuración (10% máximo)
| Score | Criterio |
|-------|----------|
| 10/10 | kilo.json/opencode.json consistentes (304 patrones: 218 deny + 85 ask + 1 allow), agentes deterministas (temperature/top_p/steps, sin seed/maxSteps), políticas experimental correctas. |
| 8/10 | Configuración mayormente consistente, algunos patrones por verificar. |
| 5/10 | Configuración parcial, gaps en determinismo o políticas. |
| 0/10 | Configuración inválida o inconsistente crítica. |

### Gestión de Dependencias (5% máximo)
| Score | Criterio |
|-------|----------|
| 5/5 | Deps opcionales documentadas con advisories conocidos, stdlib fallback funcional, SBOM actualizado. |
| 3/5 | Deps documentadas, algunos advisories sin resolver, fallback no verificado. |
| 1/5 | Deps mínimamente documentadas, advisories desconocidos, sin SBOM. |
| 0/5 | Sin gestión de dependencias o dependencias no seguras. |

---

## 3. Baselines Externas (para validación independiente)

Estos son los estándares externos contra los que comparar el proyecto:

| Métrica | Baseline Externa | Fuente |
|---------|------------------|--------|
| **Mutation score** | ≥ 80% | Estándar industria Python (pytest-mutate, coverage-mutants) |
| **Coverage** | ≥ 85% | Estándar proyecto serio |
| **Test suite** | Verde completo | `python3 -m unittest discover -s tests -q` exit code 0 |
| **P0 violations** | 0 | Reglas P0 internas no violadas (auto-evaluación honesta) |
| **SBOM** | SPDX 2.2 completo | `syft` scan, `docs/SBOM-<fecha>.spdx.json` |
| **Advisories** | 0 CRITICAL/HIGH sin excepción | `pip-audit` o `grype` |
| **Token consumption** | ≤ 1M tokens/sesión | Límite P0.19 |
| **Latencia p95** | ≤ 500 ms | P0.20 validación embeddings |

**Nota**: Estas baselines externas son lo que diferencia una evaluación "objetiva" de una "auto-evaluación circular". Cualquier score debe ser acompañado de: ¿cumple la baseline externa? ¿Por qué/no?

---

## 4. Plantilla de Informe de Evaluación

Cada evaluación debe incluir este frontmatter:

```markdown
---
evaluador: Kilo (opencode)
fecha: YYYY-MM-DD
version_rubrica: 1.0
baseline_externa: cumplida_parcialmente / no_cumplida
score_global: XX/100
categorias:
  estructura: YY/15
  compliance: ZZ/20
  seguridad: AA/15
  documentacion: BB/10
  tooling: CC/15
  tests: DD/20
  config: EE/10
  deps: FF/5
hallazgos_criticos:
  - test_suite_rota: P0.19 bloquea entrega sin justificación
  - compliance_100_auto_complacency: requiere verificación externa
  - security_92_sin_mitigar: advisories documentados pero no parcheados
mejora_principal: rubrica_explicita_con_pesos_y_baselines_externas
---
```

**Obligatorio**: Si `hallazgos_criticos` no está vacío, el veredicto no puede ser "listo para entrega" hasta que se aborden.

---

## 5. Aplicación a la Evaluación Anterior (87/100 → Ajustada)

Aplicando la rubrica a la evaluación que dio 87/100:

| Categoría | Score Anterior | Score Ajustado | Justificación |
|-----------|---------------|----------------|---------------|
| Estructura | 15/15 | 15/15 | Inventario verificado: 26 scripts, 26 REQ |
| Compliance | 20/20 → **16/20** | 16/20 | Reglas presentes, pero auto-evaluación sin verificación externa (P1.31) |
| Seguridad | 15/15 → **11/15** | 11/15 | Advisories documentados pero sin parchear (documentado ≠ mitigado) |
| Documentación | 10/10 | 10/10 | Completa y coherente |
| Tooling | 15/15 → **12/15** | 12/15 | Pipeline funcional, algunos checks condicionales |
| **Tests** | **20/20** → **8/20** | **8/20** | Suite rota (5 tests fuera de clase sin validar), sin mutation score, sin coverage |
| Config | 10/10 | 10/10 | kilo.json/opencode.json consistentes |
| Deps | 5/5 | 5/5 | Documentadas con advisories |
| **Global** | **87/100** | **~77/100** | Media ponderada con correcciones |

**Veredicto ajustado**: `77/100 - Sólido con deudas críticas` (no "listo para entrega" hasta que suite de tests pase y advisories sean mitigados).

**Cambios clave en la ajustada**:
1. Tests: 20 → 8 puntos (suite rota + sin mutation score + 5 tests fuera de clase)
2. Compliance: 20 → 16 puntos (auto-complacencia detectada por P1.31)
3. Seguridad: 15 → 11 puntos (advisories documentados pero no mitigados)

---

## 6. Próximos Pasos para Implementación

1. **Auditar test_ecosistema.py:534-579** - Determinar si los 5 tests fuera de clase son intencionales o bug. Si bug, corregir o documentar con ruta de fix.

2. **Ejecutar mutation_check.py** sobre una copia temporal - Obtener mutation score real. Si < 80%, restar puntos según rubrica.

3. **Ejecutar cobertura real** - `coverage report` sobre la suite. Si < 85%, restar puntos adicionales.

4. **Validar baselines externas** - Comparar contra estándares de la industria (mutation score ≥ 80%, coverage ≥ 85%, etc.).

5. **Actualizar CHECKLIST.md** - Incorporar items de verificación de rubrica (ya hecho: items 101-103).

6. **Documentar ruta de corrección** - Si hay deudas críticas, crear issues/ADRs con planes de mitigación y fechas.

7. **Re-evaluar con rubrica** - Aplicar la rubrica nuevamente y reportar score ajustado con evidencia.

---

**Principio rector**: Todo score debe ser fundamentado en evidencia real, no en opiniones. La rubrica provee la estructura; los datos reales (salida de tests, mutation score, coverage, advisories) proveen el valor. Si los datos no están disponibles, el score debe declarar `"no verificado"` y proponer la recolección de evidencia.