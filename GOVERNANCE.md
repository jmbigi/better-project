# Gobernanza de better-project

> Documenta roles, procesos de decisión, sucesión y resolución de conflictos.

## Roles

| Rol | Responsabilidad | Actual |
|-----|----------------|--------|
| **Maintainer Principal** | Decisiones finales, merge, releases, seguridad | @jmbigi |
| **Revisores de Código** | `@code-reviewer`, `@security-auditor`, `@compliance-checker`, `@cost-optimizer`, `@dependency-auditor` (subagentes solo lectura) | Automatizados |
| **Contribuidores** | PRs, issues, documentación, tests | Abierto |

## Proceso de decisión

### Cambios en reglas (AGENTS.md, opencode.json)

1. **Propuesta**: Issue con justificación y evidencia
2. **Análisis**: Impacto en P0/P1/P2, pruebas de regresión
3. **Revisión**: Mínimo 1 revisor humano + subagentes
4. **Decisión**: Maintainer aprueba/rechaza con razonamiento
5. **Documentación**: Actualiza `docs/REGLAS-COMPLETAS.md`, `CHECKLIST.md`, `README.md`
6. **Verificación**: `bash scripts/verificar-proyecto.sh` en verde

### Decisiones de arquitectura (ADR)

1. **Crea ADR** en `docs/decisions/ADR-XXX.md` (usa `PLANTILLA.md`)
2. **Pre-mortem obligatorio**: Simula fallo catastrófico
3. **Mínimo 2 alternativas reales** (evita falsa dicotomía)
4. **Métricas cuantitativas** para atributos de calidad
5. **Valida**: `python3 scripts/adr_validator.py --strict`
6. **Revisión cruzada**: Subagentes + humano

### Cambios en dependencias

1. **SBOM + escaneo** obligatorio (P0.18):
   ```bash
   syft . -o spdx-json > docs/SBOM-$(date +%F).spdx.json
   pip-audit -r requirements-optional.txt
   ```
2. **Bloquea** si CRITICAL/HIGH sin excepción documentada
3. **Actualiza** `requirements-optional.lock` con hashes transitivos

## Resolución de conflictos

### Entre reglas (P1.36)

Jerarquía de prioridades:
1. **Seguridad** (P0.3–P0.12)
2. **Legalidad** (licencias, cumplimiento)
3. **Privacidad** (P0.9, P0.10)
4. **Control humano** (P1.8, P1.23)
5. **Exactitud/Verificabilidad** (P0.1, P1.1)
6. **Eficiencia** (P2)

### Entre contribuidores

1. **Evidencia real** gana sobre opinión (P0.1)
2. **Subagentes** como mediadores técnicos neutrales
3. **Maintainer** decide en último recurso con razonamiento escrito

## Bus factor y sucesión

### Riesgo actual

- **Bus factor: 1** (maintainer único con conocimiento completo)
- Conocimiento crítico en: reglas P0/P1, patrones deny, arquitectura MCP, calibración Jev

### Plan de mitigación

| Acción | Estado | Responsable |
|--------|--------|-------------|
| Documentar arquitectura en `docs/AGENT-ARCHITECTURE.md` | ✅ Hecho | Maintainer |
| `CONTRIBUTING.md` con proceso claro | ✅ Hecho | Maintainer |
| `GOVERNANCE.md` (este archivo) | ✅ Hecho | Maintainer |
| Onboarding guiado (`setup.sh`) | ✅ Hecho | Maintainer |
| **Buscar co-maintainer** | ⏳ Pendiente | Maintainer |
| **Documentar patrones deny** (lecciones 3, 4, 8, 28) | ✅ En `docs/PRUEBAS.md` | Maintainer |
| **Automatizar más checks** (reducir conocimiento tribal) | 🔄 En curso | Maintainer |

### Sucesión de emergencia

Si el maintainer principal no está disponible:
1. Los subagentes (`@code-reviewer`, `@security-auditor`) mantienen la verificación automática
2. Cualquier contribuidor con acceso de merge puede aplicar hotfixes de seguridad (P0)
3. Decisiones de arquitectura se congelan hasta nuevo maintainer
4. Contactar: ver `SECURITY.md` o GitHub security advisories

## Versionado y releases

- **SemVer** para API pública (scripts, MCP tools)
- **CalVer** (YYYY.MM) para reglas y documentación
- **Tags**: `v<semver>` para código, `rules-<calver>` para AGENTS.md
- **Changelog**: `docs/CHANGELOG.md` (generado desde commits convencionales)

## Políticas

### IA (P1.16)

- Modelos permitidos: `opencode/deepseek-v4-flash-free`, `opencode-go/deepseek-v4-flash`
- Prohibido: modelos `pro`, otros proveedores sin permiso
- Locales gratuitos (Ollama/llama.cpp) SOLO para matriz de pruebas de reglas

### Seguridad (P0.3–P0.12)

- `sudo` PROHIBIDO siempre
- Producción: SOLO LECTURA
- Denies en `opencode.json`/`kilo.json` son inmutables sin revisión de seguridad

### Privacidad (P0.9, P0.10)

- Anonimización obligatoria en lecciones, docs, commits
- Auditoría `git log --all -p` antes de releases públicos

### Calidad (P1.1, P1.11, P1.12)

- Tests deben poder fallar
- Cambios graduales, verificados paso a paso
- "Mejorar" = excelencia 100% demostrable
- "Avanzado" = perfección sin errores conocidos

## Métricas de salud del proyecto

| Métrica | Objetivo | Actual (21-09-2026) | Herramienta / comando |
|---------|----------|---------------------|-----------------------|
| Cobertura scripts | ≥ 85% | 89% (2632/2945) | `pytest --cov=scripts` (omite scripts manuales vía `.coveragerc`) |
| Mutation score (batch) | ≥ 0.8 | 0.898 (168/187) | `python3 scripts/mutation_check.py --batch --strict` |
| Recall@10 retrieval | ≥ 0.7 | check en verde | `verificar-proyecto.sh` (REQ-002) |
| ADRs con alertas | 0 | 0 (8 ADR) | `python3 scripts/adr_validator.py` |
| Lecciones abiertas > 180 días | 0 | 0 (2 abiertas, recientes) | `python3 scripts/auto_audit.py decisiones` |
| Commits sin `Assisted-by` | 0 | TBD | `python3 scripts/auto_audit.py ia` |

> Las cifras son el último valor **medido**; al actualizarlas se cita el comando
> y la fecha (una métrica sin procedencia no es evidencia, P0.1). El gate de
> cobertura del CI es ≥ 85% (era 90%, inalcanzable con la suite actual).

## Revisión periódica

| Frecuencia | Actividad | Responsable |
|------------|-----------|-------------|
| Cada commit | `verificar-proyecto.sh` (hook) | Automatizado |
| Cada PR | Subagentes + maintainer | Automatizado + Humano |
| Semanal | `auto_audit.py all` | Maintainer |
| Mensual | Revisión métricas salud | Maintainer |
| Trimestral | Revisión gobernanza, bus factor | Maintainer + Co-maintainers |

## Contacto

- **Seguridad**: `security@better-project.local` (ver `SECURITY.md`)
- **General**: Issues en GitHub
- **Maintainer**: @jmbigi