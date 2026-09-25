---
id: ADR-010
titulo: Renombrar el motor Jev a MDT (modelos de decisión tipados, TyDM en inglés)
estado: Aceptado
fecha: 2026-09-25
---

# ADR-010: Renombrar el motor Jev a MDT (modelos de decisión tipados, TyDM en inglés)

## Contexto

El proyecto bautizó su motor local de decisiones como "Jev" (REQ-011, ADR-001).
Ese término es, además, el nombre de un producto de un tercero (TypeSafe) y de
un ecosistema de clones open source (p. ej. OpenJev); la coincidencia genera
ambigüedad en documentación, mensajes de error y conversaciones, y un posible
conflicto de marca. El programador ordenó el 2026-09-25 renombrar los nombres y
abreviaturas del proyecto a "typed decision models" (TyDM), con "MDT" (modelos
de decisión tipados) como abreviatura en español.

## Alternativas consideradas

- **Alternativa A — Mantener "Jev"**: coste cero, pero conserva la ambigüedad
  con el producto de terceros y el riesgo de marca; descartada por orden del
  programador (2026-09-25).
- **Alternativa B — Renombrar solo la documentación**: barata, pero deja los
  identificadores (`jev_llama.py`, `JEV_MODEL_PATH`) divergentes de los textos,
  lo que produce incoherencias verificables en cada búsqueda (P1.10);
  descartada.
- **Alternativa C — Renombrar todo con convención por idioma (elegida)**:
  identificadores en `tydm`/`TYDM`/`TyDM` (código), prosa en español con
  "MDT" y glosa en la primera mención, y conservación de nombres propios de
  terceros (OpenJev) donde el texto hable de ellos.

## Decision

Se adopta la Alternativa C. Convención:

1. **Código**: módulos y rutas `tydm_*`; clase `TyDMLlama`; variables de
   entorno `TYDM_*`; artefactos generados `tydm_calibration*.json`,
   `tydm_review*.json`; caché del modelo `~/.cache/better-project/tydm/`.
2. **Prosa en español**: "MDT" (modelos de decisión tipados), con
   "(TyDM en inglés)" en la primera mención del documento.
3. **Nombres propios de terceros**: se conservan literales (OpenJev, su URL);
   renombrarlos sería falso (P0.2).
4. El nombre anterior "Jev" solo puede aparecer al documentar este cambio
   (este ADR, changelog y lecciones).

## Consecuencias

- **Positivas**: término descriptivo sin marca ajena; búsquedas
  `grep -i jev` sin coincidencias salvo las excepciones declaradas; código y
  documentación alineados en una sola convención.
- **Negativas / deuda asumida**: los entornos que definieran variables `JEV_*`
  o rutas de caché antiguas dejan de funcionar y exigen migrar a `TYDM_*`
  (falla explícita, sin fallback silencioso); las referencias históricas en
  documentación se reescribieron; el modelo GGUF cacheado en la ruta anterior
  debe re-descargarse (no había caché en la máquina de desarrollo).
- **Reversibilidad**: alta; `git revert` del commit de renombrado restaura
  módulos, variables y textos.

## Supuestos

- No existen consumidores externos que importen los módulos `jev_*` ni lean
  `.docs/.storage/jev_*.json` (proyecto local, sin usuarios externos).
- OpenJev sigue siendo el clon open source de referencia del mismo enfoque
  (verificado: github.com/razorback16/openjev, 2026-09-25).

## Metricas de exito

- `git grep -i jev` devuelve solo las excepciones declaradas (OpenJev y este
  ADR); verificado en el commit del renombrado.
- Suite completa en verde (409/409, 2026-09-25) y verificador sin fallos.
- `python3 scripts/tydm_llama.py --demo` y `tydm_pillars.py --help` responden
  con los nombres nuevos (smoke test, 2026-09-25).

## Pre-mortem (Análisis Prospectivo de Fallos)

- **Escenario 1 — Rutinas externas rotas**: un script del programador invoca
  `scripts/jev_llama.py` o lee `JEV_MODEL_PATH` y falla. *Mitigación*: el
  fallo es explícito (módulo no encontrado / valor por defecto documentado),
  sin fallbacks silenciosos (P1.19); el changelog lista los nombres nuevos.
- **Escenario 2 — Divergencia MDT/TyDM**: documentos futuros usan "TyDM" en
  prosa española por inercia y la terminología se bifurca. *Mitigación*: la
  convención queda fijada en el punto 3 de este ADR y con glosa en la primera
  mención de cada documento.
- **Escenario 3 — Pérdida de contexto histórico**: lectores futuros no saben
  por qué existen commits `feat(jev)` en el historial de git. *Mitigación*:
  este ADR y la lección LSN-036 registran el cambio y su motivo.

## Referencias

- REQ-011 (cliente MDT liviano), REQ-012 (integración con los tres pilares),
  REQ-016 (revisión humana), REQ-018 (fusión de calibración).
- ADR-001 (cliente MDT en lugar de OpenJev o API en la nube).
- Lección LSN-036; `docs/ESTADO-TYDM-LLAMA.md`.
- OpenJev (proyecto de terceros conservado): https://github.com/razorback16/openjev
