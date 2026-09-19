---
id: ADR-002
titulo: Adoptar el Pilar 4 (control de sesgos y falacias) con registro de ADR y auditoria
estado: Aceptado
fecha: 2026-09-19
---

# ADR-002: Adoptar el Pilar 4 con registro de ADR y auditoria

## Contexto

El ecosistema ya cubre tres pilares de datos (requisitos, conocimiento,
lecciones) con reglas, scripts y verificacion. Sin embargo, las decisiones de
diseno e implementacion (stack, patrones, deuda tecnica) se tomaban sin un
registro formal de alternativas ni de supuestos, lo que las expone a sesgos de
anclaje, confirmacion y autoridad. El programador solicito institucionalizar el
control de sesgos y falacias (2026-09-19).

## Alternativas consideradas

- **Alternativa A — No hacer nada**: seguir con revision informal; coste 0, pero
  mantiene los sesgos sin trazabilidad ni evidencia.
- **Alternativa B — Solo documentar**: agregar `docs/SESGOS-Y-FALACIAS.md` sin
  proceso ni herramienta; mejora la cultura, pero no fuerza ningun control.
- **Alternativa C — Documentar + registro de ADR + validador (elegida)**:
  `docs/decisions/`, plantilla, `scripts/adr_validator.py` integrado en el
  verificador y checklist cognitivo.

## Decision

Se adopta la Alternativa C. Cada decision de arquitectura se registra como ADR
con contexto, alternativas (minimo 2), decision, consecuencias, supuestos,
metricas y premortem. El validador emite alertas heuristicas y el verificador lo
ejecuta en cada pre-commit.

## Consecuencias

- **Positivas**: trazabilidad del "por que" de cada decision; deteccion
  temprana de falsas dicotomias y premisas ocultas; 0 EUR de coste (solo
  stdlib); refuerza P0.1 y P1.15.
- **Negativas / deuda asumida**: los ADR requieren tiempo de redaccion; la
  auditoria es heuristica y puede producir alertas que exigen juicio humano.
- **Reversibilidad**: alta; el registro y el validador son archivos locales y
  pueden retirarse sin afectar a los tres pilares de datos.

## Supuestos

- El equipo (programador + agentes) mantendra el registro actualizado al menos
  en las decisiones de alto impacto.
- La heuristica textual detecta una parte util de los sesgos, no todos.

## Metricas de exito

- `python3 scripts/adr_validator.py` termina con 0 errores en cada pre-commit.
- Al menos 2 ADR reales registrados en 2026 (ADR-001 y ADR-002 lo cumplen).
- El verificador mantiene 39 checks en verde.

## Premortem

Si en 6 meses el registro queda vacio, las causas probables son: (1) ADR
demasiado largos, (2) el validador no se ejecuta, o (3) no se percibe utilidad.
Mitigacion: plantilla corta, integracion en el hook pre-commit ya hecha y
revision del registro en la retrospectiva.

## Referencias

- `docs/SESGOS-Y-FALACIAS.md` (Pilar 4), REQ-013.
- ADR-001 (cliente Jev liviano), `CHECKLIST.md` (seccion Pilar 4).
