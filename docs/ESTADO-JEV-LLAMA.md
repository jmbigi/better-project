# Estado: Jev AI liviano con llama.cpp (REQ-011)

Fecha: 2026-09-19 (revision y correccion)

## Realizado

### Requisito y codigo

- `REQ-011` creado en `.docs/requirements/REQ-011.md` con criterios de aceptacion.
- `scripts/jev_llama.py`: motor de decisiones tipadas (`noul`, `choice`, `score`)
  que carga un modelo GGUF con `llama-cpp-python` y lee logits sin samplear.
- `scripts/download_jev_model.py`: descarga idempotente del modelo recomendado
  (`bartowski/Qwen_Qwen3.5-4B-GGUF`, Q4_K_M, ~3.0 GB reales) desde HuggingFace.
- `.docs/knowledge/ai/jev_llama.md`: conceptos, uso, hardware y licencias.
- `requirements-optional.txt`: anade `llama-cpp-python`.
- `tests/test_ecosistema.py`: tests unitarios con mocks (`TestJevLlama`).

### Revision y correcciones (2026-09-19)

La revision detecto que el motor **no podia ejecutar inferencia real** pese a
figurar como implementado. Bugs corregidos:

| Bug | Causa | Correccion |
|---|---|---|
| `JEV_MODEL_PATH` ignorado | `_default_model_path()` no leia el entorno | lee `JEV_MODEL_PATH` (con `expanduser`) |
| Nombre por defecto distinto al descargado | `Qwen3.5-...` vs `Qwen_Qwen3.5-...` | `DEFAULT_MODEL` alineado al helper |
| `eval` no guardaba logits | llama-cpp-python solo guarda `scores` si `logits_all=True` | se pasa `logits_all=True` al constructor |
| Crash en `_softmax` | `scores` es 2D `(n_ctx, vocab)`; se pasaba completo | se lee la fila del ultimo token (`scores[n_tokens-1]`) |
| Estado KV acumulado | `eval` no se reiniciaba entre preguntas | `reset()` antes de cada evaluacion |
| Descarga "completa" falsa | existia el archivo parcial y se daba por buena | valida tamano minimo y reanuda con `Range` |
| Mocks no fieles | `scores` simulado como lista plana ocultaba el bug 2D | mock 2D + tests de regresion |

### Verificacion con evidencia

| Verificacion | Resultado |
|---|---|
| `python3 -m py_compile scripts/jev_llama.py scripts/download_jev_model.py` | OK |
| `python3 -m unittest discover -s tests -q` | 49 tests OK |
| `bash scripts/verificar-proyecto.sh` | 40 OK, 1 fallo (arbol de trabajo con cambios, esperado) |
| Inferencia real, `JEV_MODEL_PATH` a Llama-3.2-1B Q4 local | OK |
| Descarga completa del modelo recomendado | OK (2.8 GB, `Qwen_Qwen3.5-4B-Q4_K_M.gguf`) |
| Demo con el modelo recomendado | OK (ver abajo) |

Antes de la correccion, la ejecucion fallaba con
`TypeError: only 0-dimensional arrays can be converted to Python scalars`.

Salida real con el modelo recomendado
(`.venv/bin/python scripts/jev_llama.py --demo`, Qwen3.5-4B Q4_K_M, CPU):

```json
{
  "bloqueante": {"type": "noul", "noul": 0.6712, "confidence": 0.0863},
  "area": {"type": "choice", "choice": "verificacion", "confidence": 0.9991},
  "severidad": {"type": "score", "score": 1.0243, "confidence": 0.1297}
}
```

Salida previa con un modelo local alternativo
(`JEV_MODEL_PATH=<ruta-a-un-modelo-gguf-local>`, Llama-3.2-1B-Instruct Q4_K_M):

```json
{
  "bloqueante": {"type": "noul", "noul": 0.7636, "confidence": 0.2110},
  "area": {"type": "choice", "choice": "verificacion", "confidence": 0.3535},
  "severidad": {"type": "score", "score": 2.0130, "confidence": 0.3352}
}
```

### Commit

- `648f95f` — feat(jev): cliente Jev AI liviano con llama.cpp (REQ-011).
- Correcciones posteriores: pendientes de commit.

## Pendiente

1. **Calibracion de calidad**: las probabilidades deben calibrarse sobre un
   conjunto de decisiones etiquetadas antes de usar el motor como capa de
   decision/guardarrail.
2. **Ampliacion opcional**: integrar Jev con los tres pilares (clasificar
   requisitos, scorear conocimiento, clasificar lecciones) — no solicitado aun.

## Notas

- El motor usa el primer token de cada opcion como proxy (documentado).
- No reemplaza los guardarrailes deterministas existentes.
- `.venv/` y el modelo en `~/.cache/better-project/jev/` no se versionan.
