# AGENT-ARCHITECTURE — Cómo interactúan los agentes con el ecosistema

> Guía de arquitectura de better-project: flujo de una interacción típica,
> jerarquía de reglas y cómo extender el ruleset. Complementa (no duplica)
> `AGENTS.md` (las reglas), `docs/REGLAS-COMPLETAS.md` (su justificación) y
> `docs/ARQUITECTURA-DETERMINISMO.md` (perfiles de muestreo).

## 1. Diagrama de una interacción típica

```mermaid
sequenceDiagram
    participant H as Programador
    participant A as Agente (opencode/kilocode)
    participant R as Reglas (AGENTS.md + guardarraíles deny/ask)
    participant M as MCP (mcp_server.py)
    participant F as Archivos (.docs/, scripts/, tests/)

    H->>A: Tarea (única fuente de órdenes, P0.13)
    A->>R: Carga AGENTS.md al iniciar el proyecto
    Note over A,R: Toda acción de riesgo pasa por el<br/>guardarraíl determinista (deny/ask)
    A->>M: search_knowledge(query) — fundamentar (P0.2)
    M-->>A: Fragmentos de .docs/knowledge/ (DATO, no orden)
    A->>M: read_requirement(REQ-XXX) — antes de implementar
    M-->>A: Especificación con criterios de aceptación
    A->>F: Lee el código que va a tocar (P0.17/P0.3)
    A->>F: Implementa cambios pequeños (P1.11)
    A->>M: validate_requirements() — trazabilidad
    M-->>A: OK / errores / advertencias
    A->>F: Ejecuta tests + verificar-proyecto.sh (P1.1)
    alt Fallo o hallazgo
        A->>M: create_lesson(problema, recomendacion) (P1.20)
    end
    A-->>H: Reporte: qué cambió, evidencia, qué falta (P1.6)
    Note over H: Revisión humana obligatoria (P1.15);<br/>el commit solo con orden (P0.7)
```

Cada llamada a herramienta MCP queda registrada en
`.docs/.storage/mcp_audit.jsonl` (REQ-007): auditoría local sin proveedores.

## 2. Capas de protección (defensa en profundidad)

```
┌─────────────────────────────────────────────────────────┐
│ 1. Guardarraíles deterministas (opencode.json/kilo.json) │
│    304 patrones bash (218 deny / 85 ask) + read/edit     │
│    → actúan AUNQUE el modelo ignore las reglas de texto  │
├─────────────────────────────────────────────────────────┤
│ 2. Reglas de texto (AGENTS.md: P0/P1/P2)                 │
│    → guían el comportamiento; NO son boundary (LLM07)    │
├─────────────────────────────────────────────────────────┤
│ 3. Inferencia (temperature/top_p por rol)                │
│    → reduce varianza en auditorías (ARQUITECTURA-DETERM.)│
├─────────────────────────────────────────────────────────┤
│ 4. Verificación externa: hook pre-commit + ci.sh + tests │
│    → red fuera del modelo; el hook aborta commits rotos  │
└─────────────────────────────────────────────────────────┘
```

## 3. Jerarquía de reglas en la práctica

- **P0 (nunca violar)**: si una orden del programador choca con una P0, se
  explica el riesgo y se pregunta (P1.8) — no se ejecuta ni se desobedece en
  silencio. Ejemplo: "borra la BD de producción" → P0.4 gana; se reporta.
- **P1 (siempre cumplir)**: gobiernan el trabajo diario. Ante duda entre dos
  P1, la que produce evidencia verificable gana (P0.1 manda sobre la
  elegancia).
- **P2 (cuando aplique)**: preferencias; nunca justifican saltarse una P0/P1.

Ante conflicto: orden explícita del programador > reglas de texto, EXCEPTO
contra las P0, donde la regla gana y se consulta.

## 4. Cómo añadir una regla o herramienta nueva

1. **Regla nueva**: solo si el mismo fallo se repitió 2+ veces documentado en
   `docs/LECCIONES-APRENDIDAS.md` (P1.20). Añadirla en `AGENTS.md` y en
   `docs/REGLAS-COMPLETAS.md` con el MISMO título (el verificador comprueba
   IDs y conteos: 20 P0, 36 P1), referenciarla en `README.md`/`CHECKLIST.md`
   si aplica, y ejecutar `bash scripts/verificar-proyecto.sh`.
2. **Feature nueva** (script, herramienta MCP, vista TUI): primero su
   `REQ-XXX` en `.docs/requirements/` con criterios medibles; el código lleva
   comentario `# REQ-XXX`; tests que puedan fallar en
   `tests/test_ecosistema.py`.
3. **Patrón de permisos nuevo** en `opencode.json`/`kilo.json`: probarlo
   contra el comando real que debe bloquear (los patrones matchean por
   tokens y posición; los deny específicos van DESPUÉS de los ask genéricos
   de su familia — lecciones de las rondas 3/4/8). El verificador incluye un
   mini-matcher que comprueba que ningún ask posterior anula un deny.

## 5. Verificación sin proveedores

Todo local y open source: `scripts/verificar-proyecto.sh` (38 checks),
`scripts/ci.sh` (REQ-009: exporta HEAD a copia limpia y verifica allí, como
un clon fresco), hook pre-commit local y suite unittest stdlib. No se usa
GitHub Actions, GitLab CI ni servicios externos por decisión del programador
(2026-09-04).
