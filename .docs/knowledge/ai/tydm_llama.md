# MDT liviano con llama.cpp

## Concepto

Los **modelos de decisión tipados** (MDT; en inglés *typed decision models*,
TyDM) son modelos de la clase **System One**: en lugar de generar texto libre,
responden decisiones tipadas (`noul`, `choice`, `score`) con probabilidades
calibradas. Es util para clasificacion, enrutamiento y
verificacion dentro de software, donde el resultado se consume como una
estructura de datos, no como lenguaje natural.

**OpenJev** ([razorback16/openjev](https://github.com/razorback16/openjev)) es
una implementacion open source del mismo enfoque basada en DiffusionGemma,
pero requiere ~24 GB de VRAM. Para correr en hardware mas modesto (~6 GB),
better-project incluye `scripts/tydm_llama.py`, un cliente nativo con
`llama-cpp-python` y un modelo GGUF cuantizado.

## Arquitectura local

```text
.better-project/
  scripts/tydm_llama.py          # motor de decisiones tipadas
  scripts/download_tydm_model.py # helper de descarga
  requirements-optional.txt     # llama-cpp-python
```

El motor carga el modelo, evalua un prompt y lee los **logits** de los tokens
candidatos para cada opcion. No samplea tokens, por lo que la respuesta siempre
esta dentro del schema declarado (aunque la calidad de la decision depende del
modelo y debe validarse empiricamente).

## Modelo recomendado

| Modelo | Cuantizacion | Tamano aprox. | VRAM estimado |
|---|---|---|---|
| `bartowski/Qwen_Qwen3.5-4B-GGUF` | Q4_K_M | ~3.0 GB | ~3–4 GB |

Qwen3.5-4B es de codigo abierto. Las cuantizaciones GGUF son compatibles con
llama.cpp y permiten fallback a CPU si no hay GPU disponible.

## Instalacion

```bash
# 1. Instalar dependencia opcional en el venv del proyecto
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-optional.txt

# 2. Descargar el modelo (~3.0 GB)
python3 scripts/download_tydm_model.py

# 3. Probar con el demo
python3 scripts/tydm_llama.py --demo
```

## Configuracion

Variables de entorno:

| Variable | Default | Descripcion |
|---|---|---|
| `TYDM_MODEL_PATH` | `~/.cache/better-project/tydm/Qwen_Qwen3.5-4B-Q4_K_M.gguf` | Ruta al modelo GGUF |
| `TYDM_N_CTX` | `4096` | Contexto maximo |
| `TYDM_N_THREADS` | auto | Hilos CPU |
| `TYDM_TIMEOUT` | `300` | Timeout de carga del modelo (s) |
| `TYDM_TEMPERATURE` | `1.0` | Temperatura de calibracion > 0 (ver seccion Calibracion) |

## Formato de entrada

```json
{
  "state": "El pipeline de CI fallo porque un test referencia un REQ inexistente.",
  "questions": {
    "bloqueante": {
      "type": "noul",
      "instructions": "¿El fallo bloquea el merge a main?"
    },
    "area": {
      "type": "choice",
      "instructions": "¿Que area esta afectada?",
      "criteria": {
        "requisitos": "trazabilidad REQ",
        "verificacion": "tests o hooks",
        "documentacion": "docs o knowledge"
      }
    },
    "severidad": {
      "type": "score",
      "instructions": "¿Que tan severo es el problema?",
      "criteria": ["bajo", "medio", "alto", "critico"]
    }
  }
}
```

Uso:

```bash
python3 scripts/tydm_llama.py --input decision.json
```

## Tipos de decision

- **noul**: devuelve `noul` como probabilidad de "yes" (1 = si, 0 = no).
- **choice**: elige una opcion entre las declaradas y devuelve probabilidades.
- **score**: devuelve una puntuacion ponderada sobre una escala ordinal.

En todos los casos se devuelve `confidence = 1 - H(p)/ln(K)` (1 = certeza,
0 = distribucion uniforme).

## Limitaciones

- Para opciones multi-token solo se considera el **primer token** como proxy.
  Esto es suficiente cuando las opciones comienzan con tokens distintivos.
- Las probabilidades son condicionales a las opciones declaradas; deben
  calibrarse en la carga real antes de usarlas como guardarrail principal.
- No reemplaza los guardarrailes deterministas (`opencode.json`, `kilo.json`,
  `analyze_shell.py`); es una capa de decision adicional.

## Calibracion

Las probabilidades de un LLM suelen ser **overconfident** (Guo et al. 2017,
"On Calibration of Modern Neural Networks", ICML, arXiv:1706.04599).
`scripts/tydm_calibration.py` ajusta una unica **temperatura** T (dividir los
logits por T antes del softmax) que reduce esa overconfidence sin alterar la
opcion elegida (argmax). Se aplica al motor con `TYDM_TEMPERATURE`.

Metodologia:

- T se ajusta minimizando el **NLL** sobre un set etiquetado
  (`.docs/knowledge/ai/tydm_calibration_set.json`), con casos cuya respuesta
  correcta esta fijada por P0/P1, los estado de los REQ y las lecciones
  LSN-001..008.
- Se reporta **NLL** y **Brier** (norma L2) como metricas primarias, y **ECE**
  top-label como secundaria con caveat, siguiendo Nixon et al. 2019
  ("Measuring Calibration in Deep Learning", arXiv:1904.01685).
- Se reporta **validacion cruzada k-fold** (T se ajusta en el train y se evalua
  en el test held-out) para estimar generalizacion; Kadavath et al. 2022
  (arXiv:2207.05221) documenta que los LLM son calibrables en eleccion multiple
  y verdadero-falso.

Resultado medido (Qwen3.5-4B Q4_K_M, set v11 de 202 casos, 2026-09-19):

| Metrica | T=1 | T=1.6 | CV (held-out) antes | CV despues |
|---|---|---|---|---|
| NLL | 0.780 | 0.749 | 0.781 | 0.760 |
| Brier | 0.465 | 0.449 | 0.465 | 0.453 |
| ECE | 0.134 | 0.112 | 0.216 | 0.169 |
| Accuracy | 0.668 | 0.668 | 0.668 | 0.668 |

Por tipo (T recomendada `1.6`): `choice` acc 0.864, `noul` acc 0.629, `score`
acc 0.515. La temperatura no cambia la accuracy (correcto por diseno); solo
recalibra la confianza. El tipo `score` (escala ordinal) es el menos fiable con
el proxy de primer token y no debe usarse como guardarrail sin calibracion
propia.

La T recomendada es especifica del modelo y del set: re-ejecutar
`python3 scripts/tydm_calibration.py` al cambiar de modelo o de dominio.

## Licencias

- `llama-cpp-python`: MIT
- Qwen3.5-4B: licencia de Qwen (open source, uso investigacion/comercial segun
  terminos del modelo)
- GGUF cuantizado por bartowski: misma licencia del modelo base
