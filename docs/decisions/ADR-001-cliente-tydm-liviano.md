---
id: ADR-001
titulo: Cliente MDT liviano con llama.cpp en lugar de OpenJev o API en la nube
estado: Aceptado
fecha: 2026-09-19
---

# ADR-001: Cliente MDT liviano con llama.cpp en lugar de OpenJev o API en la nube

## Contexto

El ecosistema necesita decisiones tipadas (`noul`, `choice`, `score`) con
probabilidades calibradas para clasificar requisitos, conocimiento y lecciones
(REQ-011, REQ-012). La maquina de desarrollo disponible solo tiene CPU (sin GPU
dedicada) y ~32 GB de RAM. El proyecto exige herramientas open source, gratuitas
y locales; procesar contenido del repositorio en servicios externos implicaria
riesgo de privacidad (P0.9). El presupuesto de inferencia por sesion es bajo
(P0.19).

## Alternativas consideradas

- **Alternativa A — OpenJev (DiffusionGemma)**: implementacion open source
  compatible, pero requiere ~24 GB de VRAM, por encima del hardware disponible;
  descartada por inviable en CPU.
- **Alternativa B — API de un proveedor en la nube**: sin requisitos de
  hardware, pero envia contenido del repositorio a terceros (riesgo P0.9),
  depende de red y de un proveedor externo, y tiene coste por token (P0.19);
  descartada.
- **Alternativa C — Cliente nativo con `llama-cpp-python` sobre un GGUF
  cuantizado (elegida)**: corre en CPU, sin red, con coste monetario 0 y modelo
  de ~3 GB.

## Decision

Se adopta la Alternativa C: un cliente propio (`scripts/tydm_llama.py`) que
carga un GGUF `Qwen_Qwen3.5-4B-Q4_K_M` (~3 GB) y lee logits sin samplear. La
calidad se valida con un set etiquetado y calibracion por temperatura (REQ-011).

## Consecuencias

- **Positivas**: 0 EUR de coste por inferencia; sin dependencia de red; los
  datos no salen de la maquina; el resultado cae dentro del esquema
  declarado (no genera texto libre).
- **Negativas / deuda asumida**: la precision es limitada (global 0.65; `score`
  0.417) y exige revision humana; el tipo `score` no puede usarse como
  guardarrail; la carga del modelo ~3 GB consume RAM y tarda decenas de
  segundos en CPU.
- **Reversibilidad**: alta; el modelo es un archivo en cache y el cliente se
  puede sustituir por otra implementacion compatible sin cambiar los REQ que lo
  consumen.

## Supuestos

- El hardware seguira sin GPU dedicada a corto plazo.
- Un modelo de 4B cuantizado es suficiente para clasificacion asistida (no
  autoritativa).
- Las etiquetas del set de calibracion son la referencia correcta (aprobadas
  por el programador el 2026-09-19).

## Metricas de exito

- `scripts/tydm_llama.py --demo` responde los tres tipos sin error.
- Accuracy global del set >= 0.5 y `choice` >= 0.8 (medidas: 0.65 y 0.917).
- Calibracion: NLL y Brier disminuyen al aplicar `TYDM_TEMPERATURE=2.0`.
- Coste monetario por inferencia = 0.

## Pre-mortem (Análisis Prospectivo de Fallos)

- **Escenario 1 — Precisión insuficiente de `score`**: el modelo de 4B no mejora la accuracy del tipo `score` (actual 0.417) tras recalibraciones. *Mitigación*: marcar `score` como `experimental` y no usarlo como guardarraíl; recalibrar solo `choice` y `noul`.
- **Escenario 2 — Latencia de carga en CPU**: el tiempo de carga del modelo (~30-60 s) vuelve inviable el uso interactivo frecuente. *Mitigación*: cachear el modelo en memoria entre invocaciones; evaluar `llama.cpp` server mode.
- **Escenario 3 — Modelo superior disponible**: aparece un GGUF mejor (p. ej. 7B Q4_K_M) con mismo coste de RAM. *Mitigación*: arquitectura desacoplada (`tydm_llama.py` + modelo en cache) permite swap sin tocar REQ-012.

## Referencias

- REQ-011 (cliente MDT liviano), REQ-012 (integracion con los tres pilares).
- `docs/ESTADO-TYDM-LLAMA.md`, `docs/REVISION-SET-CALIBRACION.md`.
- Leccion LSN-009 (la temperatura no mejora la accuracy, solo la confianza).
