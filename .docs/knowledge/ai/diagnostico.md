# Diagnóstico de los cuatro pilares en proyectos externos (REQ-017)

## Concepto

`scripts/diagnostico.py` evalúa **cualquier proyecto** (`--root <carpeta>`) sobre
los cuatro pilares de better-project y su higiene general, y devuelve una
puntuación por pilar, hallazgos y **sugerencias accionables**. Es de **solo
lectura**: nunca crea ni modifica archivos del proyecto evaluado (P0.3/P1.17).

## Uso

```bash
python3 scripts/diagnostico.py --root <carpeta>
python3 scripts/diagnostico.py --root <carpeta> --json
python3 scripts/diagnostico.py --root <carpeta> --min-score 60   # exit 1 si <
```

`--min-score N` permite usarlo como puerta en el CI de un proyecto tercero.

## Qué evalúa

| Pilar | Comprueba | Herramienta reutilizada |
|---|---|---|
| 1 requisitos | `.docs/requirements/REQ-*.md`, frontmatter y trazabilidad código↔REQ | `doc_validator` |
| 2 conocimiento | `.docs/knowledge/**/*.md` e índice | propia + `index_knowledge` (sugerido) |
| 3 lecciones | `.docs/lessons/*.yaml` y validez de campos | `lessons_extractor` |
| 4 sesgos/decisiones | `docs/decisions/ADR-*.md`, `docs/SESGOS-Y-FALACIAS.md`, `AGENTS.md` | `adr_validator` |
| higiene | README, tests, verificación, manifiesto, licencia | — |

## Puntuación y niveles

- Cada pilar: `score` 0–100 y `nivel` (`ausente` <25, `inicial` <55, `parcial`
  <80, `solido` ≥80).
- Global: media de los cinco bloques. El repo better-project mide **100/100**
  (2026-09-19); un directorio vacío mide 0/100 con 11 sugerencias.

## Salida JSON

```json
{
  "root": "/ruta/al/proyecto",
  "fecha": "2026-09-19",
  "puntuacion_global": 100,
  "nivel_global": "solido",
  "pilares": ["..."],
  "sugerencias": ["..."]
}
```

## Limitaciones

- Read-only y heurístico: no ejecuta el código del proyecto evaluado.
- El pilar 4 y la higiene comprueban presencia y formato, no profundidad de las
  decisiones.
- No sustituye la revisión humana (P1.15).

## Referencias

- REQ-017, `docs/HERRAMIENTAS-Y-FUENTES.md`, `README.md` (Pilar 4).
