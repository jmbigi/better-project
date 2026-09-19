# Estado: Jev AI liviano con llama.cpp (REQ-011)

Fecha: 2026-09-19

## Realizado

### Requisito y codigo

- `REQ-011` creado en `.docs/requirements/REQ-011.md` con criterios de aceptacion.
- `scripts/jev_llama.py`: motor de decisiones tipadas (`noul`, `choice`, `score`)
  que carga un modelo GGUF con `llama-cpp-python` y lee logits sin samplear.
- `scripts/download_jev_model.py`: descarga idempotente del modelo recomendado
  (`bartowski/Qwen_Qwen3.5-4B-GGUF`, Q4_K_M, ~2.8 GB) desde HuggingFace.
- `.docs/knowledge/ai/jev_llama.md`: conceptos, uso, hardware y licencias.
- `requirements-optional.txt`: anade `llama-cpp-python`.
- `tests/test_ecosistema.py`: 5 tests unitarios con mocks (`TestJevLlama`).

### Verificacion con evidencia

| Verificacion | Resultado |
|---|---|
| `python3 -m py_compile scripts/jev_llama.py scripts/download_jev_model.py` | OK |
| `python3 -m unittest discover -s tests -v` | 46 tests OK |
| `bash scripts/verificar-proyecto.sh` | 40 OK, 0 fallos de codigo |
| Pre-commit del commit `648f95f` | 38 OK, 0 FALLOS |
| `pip install llama-cpp-python` en `.venv` | OK (0.3.35 + numpy 2.4.6) |

### Commit

- `648f95f` — feat(jev): cliente Jev AI liviano con llama.cpp (REQ-011)
  publicado en `origin/main`.

## Pendiente

1. **Descarga completa del modelo**: la descarga del GGUF quedo incompleta
   (~2.1 GB de 2.8 GB) y fue detenida al cerrar la sesion. Reintentar con:
   `python3 scripts/download_jev_model.py --yes` o `curl -L -C - -o <ruta> <url>`.
2. **Prueba de inferencia real**: no ejecutada. Falta correr:
   `.venv/bin/python scripts/jev_llama.py --demo` con el modelo completo.
3. **Validacion de calidad**: las probabilidades deben calibrarse en una carga
   real antes de usar el motor como capa de decision.
4. **Ampliacion opcional**: integrar Jev con los tres pilares (clasificar
   requisitos, scorear conocimiento, clasificar lecciones) — no solicitado aun.

## Notas

- El motor usa el primer token de cada opcion como proxy (documentado).
- No reemplaza los guardarrailes deterministas existentes.
- `.venv/` y el modelo en `~/.cache/better-project/jev/` no se versionan.
