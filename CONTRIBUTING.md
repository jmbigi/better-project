# Contribuir a better-project

> **Regla de oro**: Una contribución debe valer más que el tiempo de revisión que cuesta (P1.15).

## Antes de contribuir

1. **Lee la documentación obligatoria**:
   - `AGENTS.md` — Reglas de IA (P0/P1/P2)
   - `README.md` — Arquitectura y uso rápido
   - `docs/REGLAS-COMPLETAS.md` — Justificación de cada regla
   - `CHECKLIST.md` — Checklist pre-entrega (imprimible)

2. **Entiende los cuatro pilares**:
   - Pilar 1: Requisitos (`.docs/requirements/REQ-XXX.md`)
   - Pilar 2: Conocimiento (`.docs/knowledge/`)
   - Pilar 3: Lecciones (`.docs/lessons/<año>.yaml`)
   - Pilar 4: Sesgos/Falacias (`docs/decisions/ADR-XXX.md`)

3. **Configura el entorno**:
   ```bash
   bash scripts/setup.sh --yes
   ```

## Flujo de trabajo

### Para nuevas features

1. **Revisa requisitos existentes** (`.docs/requirements/`)
2. **Si no existe REQ**, créalo con frontmatter:
   ```yaml
   ---
   id: REQ-XXX
   titulo: Título descriptivo
   estado: Draft
   prioridad: Media
   version: 1.0
   fecha_creacion: 2026-XX-XX
   ---
   ```
3. **Implementa** con referencia `# REQ-XXX` en cada función/clase
4. **Valida**:
   ```bash
   python3 scripts/doc_validator.py --strict
   python3 -m unittest discover -s tests -q
   bash scripts/verificar-proyecto.sh
   ```
5. **Registra lección** si hubo hallazgos:
   ```bash
   python3 scripts/lessons_extractor.py
   # O vía MCP: create_lesson(...)
   ```

### Para correcciones (bugfix)

1. **Revisa lecciones** (`.docs/lessons/`) para no repetir errores
2. **Corrige** con cambio mínimo y verificable
3. **Valida** igual que arriba
4. **Si el bug se repitió 2+ veces**, propone regla nueva en `AGENTS.md`

### Para decisiones de arquitectura

1. **Crea ADR** en `docs/decisions/ADR-XXX-titulo.md` usando `PLANTILLA.md`
2. **Incluye**: Contexto, Alternativas consideradas, Decisión, Consecuencias, Supuestos
3. **Valida**:
   ```bash
   python3 scripts/adr_validator.py --strict
   ```
4. **Pre-mortem**: Imagina el fallo catastrófico y argumenta causas

## Estándares de código

- **Python**: `python3 -m py_compile`, `ruff check` (config `ruff.toml`)
- **Shell**: `bash -n script.sh`
- **Tests**: `unittest` stdlib, herméticos (directorios temporales)
- **Sin placeholders**: Nada de `pass`, `...`, `TODO` como implementación (P1.33)
- **Errores explícitos**: Nada de `except: pass` (P1.26)
- **Rutas**: `pathlib`, config por capas (P1.33)

## Uso de IA

- **Declaración obligatoria** en commits significativos:
  ```
  Assisted-by: opencode
  ```
- **Revisión humana obligatoria** (P1.15): El humano debe entender y probar lo generado
- **Modelos permitidos**: Solo `opencode/deepseek-v4-flash-free` o `opencode-go/deepseek-v4-flash`
- **Nunca** uses modelos `pro` sin permiso explícito

## Seguridad

- **Nunca** commitees `.env`, claves, tokens (P0.6, P0.7)
- **Nunca** ejecutes `sudo` (P0.5)
- **Verifica** `git status`/`git diff` antes de commit
- **Los denies** en `opencode.json`/`kilo.json` son la protección real

## Checklist pre-entrega (obligatorio)

Ver `CHECKLIST.md` — completar **TODAS** las casillas P0 con evidencia real.

## Reportar problemas

- **Seguridad**: Abre issue con `⚠️ SECURITY` en el título
- **Bugs**: Incluye pasos para reproducir, salida real, entorno
- **Mejoras**: Referencia REQ existente o crea uno nuevo

## Licencia

GPL-3.0-or-later. Ver `LICENSE`.