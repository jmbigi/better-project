---
id: ADR-011
titulo: Puente opcional StrictDoc para el Pilar 1 (sin migrar los REQ-XXX.md)
estado: Aceptado
fecha: 2026-10-01
---

# ADR-011: Puente opcional StrictDoc para el Pilar 1 (sin migrar los REQ-XXX.md)

## Contexto

El Pilar 1 gestiona requisitos como `REQ-XXX.md` con frontmatter YAML y
trazabilidad vía `doc_validator.py` (31 REQs, 30 referencias de código al
01-10-2026). Ese formato no soporta diagramas ni relaciones ricas. El
programador ordenó complementar el proyecto con StrictDoc (texto plano,
Mermaid, pseudocódigo, colaboración asíncrona vía Git, Apache-2.0).

Evidencia del prototipo aislado (P1.21, 01-10-2026, strictdoc **0.30.1** — la
versión "7.13" citada inicialmente no existe; máximo en PyPI: 0.30.1):

- Instalación aislada (`pip --target`): **444 MB**, ~100 paquetes transitivos
  (fastapi, pandas, plotly…). Choca con el diseño stdlib-first si fuera núcleo.
- `pip-audit 2.10.1` (OSV) sobre el entorno: **0 vulnerabilidades conocidas**.
- `strictdoc export` de 1 documento: ~1.6 s, 4 vistas HTML (17 MB estáticos);
  Mermaid renderizado en el navegador con motor incluido (el texto del
  diagrama no sale del equipo).
- Gramática real (verificada en el paquete, no en la memoria): `OPTIONS:` +
  `MARKUP: Markdown`, nodos `[TEXT]` con `STATEMENT: >>> … <<<`.

## Alternativas consideradas

- **Alternativa A — adopción profunda**: migrar los 31 `REQ-XXX.md` a `.sdoc`
  y sustituir `doc_validator.py`. Descartada: reescritura masiva (P1.11),
  rompe la trazabilidad existente y la autoría histórica; coste estimado >16 h
  sin beneficio medible sobre la trazabilidad actual.
- **Alternativa B — no hacer nada**: mantener solo Markdown. Descartada: la
  orden explícita del programador pide requisitos enriquecidos con diagramas
  (P1.8); los ADR ya echan de menos diagramas de flujo legibles en repo.
- **Alternativa C (elegida) — puente opcional**: los `.sdoc` conviven con los
  `.md`; `strictdoc_bridge.py` (stdlib) valida su trazabilidad sin instalar
  nada; strictdoc solo se instala (aislado) para exportar HTML.

## Decision

Se adopta la **alternativa C**, puente opcional, con estas reglas:

1. Los `REQ-XXX.md` siguen siendo la **autoridad** de trazabilidad; los
   `.sdoc` solo alojan requisitos NUEVOS que se beneficien de diagramas.
2. UIDs con esquema `SDOC-\d{3}` (sin subcadena `REQ-\d{3}`) para no colisionar
   con `CODE_RE` de `doc_validator.py` (`\bREQ-(\d{3})\b`).
3. `scripts/strictdoc_bridge.py` valida estructura y referencias `SDOC-XXX` en
   código usando solo stdlib; el verificador lo ejecuta si hay `.sdoc`
   (`[SKIP]` si no).
4. La capa de export (strictdoc) es opcional y aislada:
   `requirements-strictdoc.txt` + instalación en venv/`--target` (P0.5) tras
   auditoría P0.18 documentada.

## Consecuencias

- Positivas: requisitos con diagramas Mermaid versionados en Git; trazabilidad
  `.sdoc`↔código con gate en el verificador; el núcleo sigue funcionando sin
  instalar nada (suite y verificador verdes sin strictdoc).
- Negativas: dos formatos de requisitos conviviendo (riesgo de deriva);
  +444 MB de disco SOLO si se instala la capa de export; un check más en el
  verificador (~0.1 s cuando hay `.sdoc`).
- Neutras: `requirements-optional.txt` NO incluye strictdoc por defecto; es
  una capa aparte, como `requirements-tydm.txt`.

## Supuestos

- StrictDoc se mantiene como proyecto activo (última release 0.30.1 en PyPI al
  01-10-2026); si se abandonara, el bridge sigue validando sin él (la export
  HTML es prescindible).
- El esquema `SDOC-\d{3}` no colisiona con otros identificadores del repo
  (verificado con grep y test de no colisión en la suite).

## Metricas de exito

- `python3 scripts/strictdoc_bridge.py` → exit 0 en el repo (con el `.sdoc` de
  dogfooding presente) y exit 1 ante cualquiera de los 6 casos límite testeados.
- Suite completa verde y verificador 0 FALLOS nuevos tras la integración.
- `strictdoc export` del `.sdoc` de dogfooding reproducible en ≤5 s en el
  entorno aislado documentado.

## Pre-mortem (Análisis Prospectivo de Fallos)

Es 2027 y la integración se considera fallida. Causas más probables:

1. **Deriva de formatos**: alguien edita el `.sdoc` y olvida el `.md` gemelo
   (o al revés). Mitigación: regla 1 (el `.md` manda) + el check del
   verificador que obliga a mantener referencias válidas.
2. **La dependencia pesada se cuela en el núcleo**: alguien importa strictdoc
   en el bridge. Mitigación: bridge stdlib puro con test que falla si el módulo
   importa paquetes externos (AST), igual que la guarda de `tydm_fast`.
3. **La gramática cambia entre versiones de strictdoc** y el `.sdoc` deja de
   exportar. Mitigación: `requirements-strictdoc.txt` fija `==0.30.1`; el
   bridge no depende de la gramática completa (parser tolerante de campos
   mínimos, no de textX).
