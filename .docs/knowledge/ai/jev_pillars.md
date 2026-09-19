# Jev y los tres pilares (REQ-012)

## Concepto

`scripts/jev_pillars.py` usa el motor Jev de REQ-011 para **proponer**
etiquetas sobre los tres pilares del ecosistema. Es una capa de clasificación
**asistida y no autoritativa**: el resultado se consume como propuesta y la
aplicación a los documentos es siempre una acción humana (P1.17/P1.23).

| Pilar | Comando | Propone | Tipo Jev |
|---|---|---|---|
| Requisitos | `requisitos --req REQ-XXX` | `prioridad` (Baja/Media/Alta) | `choice` |
| Conocimiento | `conocimiento --file <fragmento>` | `relevancia` (0–3) | `score` |
| Lecciones | `lecciones --id LSN-XXX` | `fase` y `categoria` | `choice` |

## Uso

```bash
python3 scripts/jev_pillars.py requisitos --req REQ-011
python3 scripts/jev_pillars.py conocimiento --file docs/REGLAS-COMPLETAS.md --json
python3 scripts/jev_pillars.py lecciones --id LSN-008 --json
# también --text "..." para texto directo
```

El script **solo lee**: nunca escribe en `.docs/requirements/`,
`.docs/knowledge/` ni `.docs/lessons/` (criterio 8). Al leer un REQ o una
lección, el frontmatter YAML se descarta para no filtrar al modelo la etiqueta
que se le pide predecir.

## Esquema de salida (`--json`)

```json
{
  "subcomando": "requisitos",
  "id": "REQ-011",
  "tipo": "choice",
  "accuracy_referencia": 0.9167,
  "experimental": false,
  "decisiones": [
    {
      "id": "REQ-011",
      "campo": "prioridad",
      "tipo": "choice",
      "decision": null,
      "propuesta": "Alta",
      "probabilities": {"Baja": 0.06, "Media": 0.3, "Alta": 0.64},
      "confidence": 0.41,
      "revision_humana": true,
      "accuracy_referencia": 0.9167,
      "experimental": false
    }
  ]
}
```

- `decision`: valor emitido; `null` si la confianza no alcanza el umbral.
- `propuesta`: argmax, siempre presente (para revisión humana).
- `revision_humana`: `true` si no se emite etiqueta definitiva.
- `accuracy_referencia`: accuracy medida para el tipo de pregunta en el set de
  calibración de REQ-011.
- `experimental`: `true` si la accuracy es desconocida o < 0.6.

## Umbrales y configuración

| Variable | Default | Descripción |
|---|---|---|
| `JEV_MODEL_PATH` | cache local | Modelo GGUF (ver REQ-011) |
| `JEV_TEMPERATURE` | `1.0` | Temperatura de calibración (ver REQ-011) |
| `JEV_MIN_CONFIDENCE` | `0.5` | Confianza mínima para emitir etiqueta definitiva |
| `JEV_CALIBRATION_REPORT` | `.docs/.storage/jev_calibration.json` | Informe con la accuracy por tipo |

Si el informe de calibración no existe, `accuracy_referencia` es `null` y el
comando queda `experimental: true` (no se inventan valores; P1.19/P1.29).

## Precisión medida por tarea

Valores del set validado (REQ-011 v8, Qwen3.5-4B Q4_K_M, 148 casos, `T=1.6`):

| Pilar | Tipo | Accuracy | IC Wilson 95 % | Estado |
|---|---|---|---|---|
| Requisitos | `choice` | 0.896 (n=48) | [0.778, 0.955] | utilizable (revisión humana) |
| Lecciones | `choice` | 0.896 (n=48) | [0.778, 0.955] | utilizable (revisión humana) |
| Conocimiento | `score` | 0.479 (n=48) | [0.345, 0.617] | `experimental` (no guardarraíl) |

El tipo `score` (relevancia de conocimiento) es poco fiable con el proxy de
primer token y queda marcado `experimental` automáticamente (accuracy < 0.6).
No debe usarse como guardarraíl sin recalibrar y ampliar el set.

## Limitaciones

- El motor usa el **primer token** de cada opción como proxy (REQ-011).
- Las propuestas no son autoritativas: aplicar una etiqueta es una acción
  humana (P1.17/P1.25).
- La accuracy por tipo es una referencia agregada del set de REQ-011, no una
  medida específica de cada nuevo fragmento.
- No reemplaza los guardarraíles deterministas (`opencode.json`, `kilo.json`,
  `analyze_shell.py`).

## Licencias

Iguales que REQ-011 (`llama-cpp-python` MIT; modelo Qwen3.5-4B y sus
cuantizaciones GGUF según la licencia del modelo base).
