# PLANTILLA — Registro de Decision de Arquitectura (ADR)

> Copiar a `docs/decisions/ADR-NNN-titulo-corto.md` y completar **todas** las
> secciones. El validador `scripts/adr_validator.py` exige `Contexto`,
> `Alternativas consideradas`, `Decision`, `Consecuencias` y `Pre-mortem (Análisis Prospectivo de Fallos)` para estados Propuesto/Aceptado; recomienda
> `Supuestos`, `Metricas de exito`.

```markdown
---
id: ADR-NNN
titulo: <decision en una frase>
estado: Propuesto        # Propuesto | Aceptado | Rechazado | Reemplazado | Deprecado
fecha: AAAA-MM-DD
---

# ADR-NNN: <decision en una frase>

## Contexto

<Que problema se resuelve, que restricciones aplican (requisitos, hardware,
coste, plazos) y que evidencia existe. Evitar adjetivos sin metrica.>

## Alternativas consideradas

<Al menos DOS opciones reales, cada una con su criterio y su costo. Una sola
opcion es indicio de falsa dicotomia.>

- **Alternativa A**: <descripcion, pros y contras medibles, motivo de descarte>.
- **Alternativa B**: <descripcion, pros y contras medibles>.
- **Alternativa C (elegida)**: <descripcion>.

## Decision

<Que se decide y por que gana frente a las alternativas, con criterios
verificables.>

## Consecuencias

- **Positivas**: <beneficios esperados>.
- **Negativas / deuda asumida**: <costes, riesgos, trabajo postergado>.
- **Reversibilidad**: <coste de deshacer la decision>.

## Supuestos

<Premisas que, si resultan falsas, invalidan la decision. Explicitarlas evita
premisas ocultas.>

## Metricas de exito

<Como se sabra si la decision fue correcta: numeros verificables (p. ej.,
p99 < 200 ms, accuracy >= 0.6, coste mensual <= X).>

## Pre-mortem (Análisis Prospectivo de Fallos)

<Imaginar que la decision fracaso catastroficamente y enumerar hacia atras
al menos DOS causas posibles con sus mitigaciones; esto neutraliza el
optimismo y el sesgo de confirmacion (Pilar 4).>

## Referencias

<Enlaces a REQ-XXX, lecciones LSN-XXX, ADR relacionados y documentos.>
```
