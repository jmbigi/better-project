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
| `python3 -m py_compile` de `jev_calibration.py` | OK |
| `python3 -m unittest` (10 tests nuevos de calibracion) | 59 tests OK |
| Calibracion real (Qwen3.5-4B, 40 casos, k-fold) | OK (ver abajo) |

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
- `b289293` — fix(jev): corrige inferencia real del motor REQ-011.
- `1f62e37` — feat(jev): calibracion por temperatura con NLL/Brier/ECE.
- Push a `origin/main`: sincronizado.

## Calibracion (2026-09-19)

Se anadio `scripts/jev_calibration.py` y `JEV_TEMPERATURE` al motor. El set
etiquetado `.docs/knowledge/ai/jev_calibration_set.json` (40 casos: 16 noul,
12 choice, 12 score) se basa en P0/P1, el estado de los REQ y LSN-001..008; sus
etiquetas son la verdad de referencia **propuesta** y deben ser revisadas.

Metodologia segun Guo 2017 (arXiv:1706.04599), Nixon 2019 (arXiv:1904.01685) y
Kadavath 2022 (arXiv:2207.05221): T por minimizacion de NLL, Brier/NLL
primarios, ECE secundario, validacion cruzada k-fold.

Resultado medido (Qwen3.5-4B Q4_K_M):

| Metrica | T=1 | T=2.0 | CV antes | CV despues |
|---|---|---|---|---|
| NLL | 0.808 | 0.741 | 0.808 | 0.745 |
| Brier | 0.480 | 0.454 | 0.480 | 0.455 |
| ECE | 0.135 | 0.116 | 0.269 | 0.226 |
| Accuracy | 0.650 | 0.650 | 0.650 | 0.650 |

Accuracy por tipo (T=2.0): choice 0.917, noul 0.625, score 0.417. T=2.0 reduce
NLL/Brier/ECE sin cambiar la accuracy. Informe JSON (generado, no versionado)
en `.docs/.storage/jev_calibration.json`. Aplicar con `JEV_TEMPERATURE=2.0`.

## Etiquetas aprobadas (2026-09-19)

El programador reviso y aprobo las 40 etiquetas **sin correcciones** (40/40). El
set paso a `version: 2` con `revision_humana.estado = "Aprobada"`; los casos
ambiguos S03, S06, S11 y S12 se confirmaron con el criterio de adjudicacion
documentado. La precision por tarea es evidencia valida (P1.15), con las
cautelas estadisticas del artefacto de revision.

## Integracion con los tres pilares (REQ-012, 2026-09-19)

- `scripts/jev_pillars.py`: clasificacion asistida de los tres pilares
  (`requisitos` -> `prioridad`; `conocimiento` -> `relevancia` 0-3; `lecciones`
  -> `fase` y `categoria`). Solo lee; nunca escribe en los documentos.
- Umbral `JEV_MIN_CONFIDENCE` (default 0.5) y marca `experimental` automatica
  cuando la accuracy de referencia < 0.6 (el tipo `score` queda experimental).
- `tests/test_ecosistema.py`: tests de REQ-012 con cliente simulado (sin modelo).
- Documentacion en `.docs/knowledge/ai/jev_pillars.md`.

| Verificacion | Resultado |
|---|---|
| `python3 -m py_compile scripts/jev_pillars.py` | OK |
| `python3 -m unittest discover -s tests -q` | 73 tests OK |
| `bash scripts/verificar-proyecto.sh --pre-commit` | 38 OK, 0 fallos |
| `bash scripts/verificar-proyecto.sh` (completo) | 40 OK, 1 fallo esperado (arbol de trabajo con cambios) |
| Inferencia real `.venv/bin/python scripts/jev_llama.py --demo` (Qwen3.5-4B Q4_K_M) | OK |
| Inferencia real `scripts/jev_pillars.py lecciones --id LSN-008 --json` | OK (fase `Testing` correcta; categoria propuesta `Proceso` frente a la real `Riesgo_Tecnico`) |

## Auto-auditoria y gobernanza (REQ-013/REQ-014, 2026-09-19)

- `scripts/adr_validator.py` (REQ-013): valida los ADR y audita sesgos de
  decision; registro en `docs/decisions/` (ADR-001, ADR-002, ADR-003).
- `scripts/auto_audit.py` (REQ-014): seis subcomandos (sesgos documentales,
  frescura del SBOM, decisiones pendientes, tests debiles, trazabilidad de IA y
  re-escaneo de vulnerabilidades).
- `docs/SESGOS-Y-FALACIAS.md` y `docs/HERRAMIENTAS-Y-FUENTES.md` (referencia).
- Ambos integrados en `scripts/verificar-proyecto.sh`.

| Verificacion | Resultado |
|---|---|
| `python3 -m unittest discover -s tests -q` | 115 tests OK |
| `python3 scripts/adr_validator.py --strict` | 3 ADR, 0 errores, 0 alertas |
| `python3 scripts/auto_audit.py all` | 0 errores (1 alerta: LSN-009 abierta) |
| `python3 scripts/auto_audit.py vulns` (pip-audit) | 0 errores, 5 advisories (chromadb 1.5.9 y diskcache 5.6.3, sin parche) |
| `python3 scripts/mutation_check.py` (adr_validator) | 16 mutantes, 16 muertos, score 1.000 |
| `cosmic-ray` 8.7.0 (adr_validator, copia aislada) | 160 mutantes, 124 muertos (77.5 %) |
| `vale README.md docs .docs` (opcional, Pilar 4) | 0 errores, 0 alertas (34 archivos) |
| `bash scripts/verificar-proyecto.sh --pre-commit` | 40 OK, 0 fallos |

## Pendiente

1. **Revision humana de las clasificaciones de REQ-012**: la integracion con el
   modelo real funciona y **propone**; la categoria de `LSN-008` salio
   equivocada, lo que confirma que la etiqueta definitiva es del humano
   (P1.17/P1.23).
2. **Ampliar el set de calibracion** (>= 100 casos por tipo) para estabilizar el
   ECE y la accuracy de `score`; hoy n=12 y el intervalo de confianza es ancho.
3. **Regenerar el SBOM** (`docs/SBOM-2026-09-04.spdx.json`) con `syft` cuando
   este disponible. `auto_audit vulns` ya re-escanea a demanda con pip-audit
   (2026-09-19: 4 advisories sin parche en chromadb 1.5.9 y 1 en diskcache
   5.6.3; riesgo aceptado para uso local embebido, LSN-007). Nota: el `.venv`
   no tiene chromadb instalado, por lo que un SBOM por escaneo no refleja el
   grafo resuelto de `requirements-optional.txt`.

## Notas

- El motor usa el primer token de cada opcion como proxy (documentado).
- No reemplaza los guardarrailes deterministas existentes.
- `.venv/` y el modelo en `~/.cache/better-project/jev/` no se versionan.
