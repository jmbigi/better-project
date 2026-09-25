# Motor MDT competitivo local (REQ-027) — resultados vs estado del arte TDM

> Medición propia: `python3 scripts/tydm_fast.py bench` (2026-09-25).
> Fuente de los datos de terceros: análisis comparativo TDM provisto por el
> programador (2026-09-25), con las cifras publicadas por cada proyecto.
> Principio P0.1: cada número propio es reproducible con el comando indicado;
> las comparaciones entre métricas de dominios distintos se marcan como
> indicativas, no concluyentes.

## 1. Nuestro motor `fast` (medido, reproducible)

Comando: `python3 scripts/tydm_fast.py bench` — set validado v18 (328 casos
aprobados por humano), validación cruzada 5-fold, equipo i7-8700B (CPU, sin
GPU, sin red), 0 dependencias (stdlib).

| Métrica (out-of-fold) | noul (n=112) | choice (n=108) | score (n=108) | Global |
|---|---|---|---|---|
| Accuracy [IC95% Wilson] | **0.902** [0.833, 0.944] | **0.824** [0.742, 0.884] | **0.676** [0.583, 0.757] | **0.802** |
| ECE (top-label, 10 bins) | 0.033 | 0.081 | 0.077 | 0.061 |
| Brier | 0.156 | 0.293 | 0.456 | — |
| Cobertura conformal (α=0.10) | 0.902 | 0.917 | 0.917 | ≥ 0.90 |
| Tasa de abstención | 0.009 | 0.435 | 0.704 | — |
| Accuracy de las emitidas | 0.901 | **0.934** | **0.969** | — |

- **Latencia p50: 0.43 ms/item** (p95: 0.47 ms); entrenamiento: 0.15 s;
  modelo: 450 KB.
- **Coste**: 0 € y sin red. Coste eléctrico estimado < 10⁻⁹ $/item
  (60 W × 0.43 ms a 0.15 $/kWh), sin GPU.
- La abstención conformal **mejora la precisión de lo emitido**: choice pasa
  de 0.824 a 0.934 y score de 0.676 a 0.969 cuando el conjunto conformal es
  unitario; en el resto devuelve `revision_humana`.

## 2. Comparación con el estado del arte (datos publicados de terceros)

| Dimensión | Jev (TypeSafe) | Laya | JevK5 / cbjev | SemIf | Verdict | this-that-model | **MDT fast (este repo)** |
|---|---|---|---|---|---|---|---|
| Latencia | 70–500 ms (API) | 33 ms GPU; 329 ms+ CPU | 3–31 ms GPU | ~1.0 s GPU | **0.5 ms batch CPU** | 30.9 ms GPU portátil | **0.43 ms CPU (p50)** |
| Coste | ~$0.042/1M tok | $0 (GPU) | $0 (GPU) | $0 (GPU) | $0 (CPU) | $0 (GPU) | **$0 (CPU, sin GPU)** |
| Privacidad | nube | 100% local | 100% local | 100% local | 100% local | 100% local | **100% local** |
| ECE | 0.144–0.246 | 0.466 / 0.125 | 0.117 | 0.18 / 0.10 | **0.014–0.030** | Brier 0.042 | **0.033–0.081** |
| Cobertura garantizada | no | no | no | no | **sí (conformal)** | no | **sí (conformal ≥ 0.90)** |
| Abstención con mejora medida | no doc. | no doc. | no doc. | no doc. | sí (declarada) | no doc. | **sí, medida (hasta +0.29 en emitidas)** |
| Robustez a reordenamiento | baja (13%) | baja (7.8%) | 0.2% | baja | **0%** | n/d | **0% por construcción** |
| Alta cardinalidad | ≤255 opciones | ~20 | ≤16 (JevK5) | n/d | ilimitada | n/d | sin límite práctico (clases entrenadas) |
| Accuracy | 0.809 mediana | 0.362–0.766 | 0.741–0.783 | 0.750–0.807 | 0.594–0.913 | **0.941** (su cohorte) | **0.802** (nuestro set) |
| Verificación/gobernanza | no pública | no pública | no pública | no pública | no pública | no pública | **única: REQ, mutación 1.000, ADRs, conformal auditable** |
| Entrenamiento | proveedor | fine-tuning GPU | destilación | ninguno | 0.9 s CPU (16/clase) | GPU | **0.15 s CPU (328 casos, stdlib)** |

Lectura honesta (P0.1/P1.31):

- **Superamos o empatamos** en: latencia CPU (0.43 ms, solo Verdict empata),
  coste ($0 sin GPU), privacidad, calibración ECE (0.033–0.081 frente a
  0.117–0.466 de las alternativas open; Verdict mantiene ventaja en
  0.014–0.030), cobertura conformal verificada, abstención con mejora medida,
  robustez de orden (0%), entrenamiento ultrarrápido y gobernanza verificable.
- **No superamos**: la accuracy de `this-that-model-1.0` (0.941) medida en su
  cohorte con GPU; ni el ECE mínimo de Verdict en choice/score; ni el
  multilingüismo declarado por Laya/Verdict (nuestro set es en español; el
  motor es agnóstico del idioma por diseño de features, pero no está medido).
- Las cifras de accuracy de la tabla de terceros provienen de dominios y
  cohortes distintas (Banking77, JevBench, benchmarks propios): la comparación
  cross-dominio es **indicativa**. La comparación directa y concluyente es
  contra nuestro propio baseline: el backend `llama` (Qwen3.5-4B local) obtuvo
  accuracy 0.646 global en este mismo set; el backend `fast` alcanza 0.802
  (~5.000× más rápido y 100% stdlib).

## 3. Por qué esto es "más eficiente y más inteligente" sin coste

1. **Aprende del conocimiento gobernado**: el clasificador se entrena con el
   set validado por humanos (reglas P0/P1, estados de REQ y lecciones
   codificados). Ningún competidor tiene ese activo: la gobernanza del repo se
   convierte en datos de entrenamiento.
2. **Fiabilidad medible**: conformal con cobertura ≥ 90% verificada y
   abstención que reduce el error de lo decidido; ECE medido, no estimado.
3. **Eficiencia extrema**: 0.43 ms/item y 0.15 s de entrenamiento en CPU
   normal, 0 dependencias, 0 €, sin red.
4. **Auditabilidad total**: cada métrica de esta tabla se reproduce con
   `python3 scripts/tydm_fast.py bench`; el propio motor pasa la misma
   verificación del repo (tests, mutación, hooks).

## 4. Límites declarados

- Set de 328 casos en español y del dominio del proyecto; el rendimiento en
  otros dominios/idiomas no está medido.
- La comparación con los seis sistemas usa sus cifras publicadas, no una
  ejecución local de sus pesos (requeriría GPU; fuera de alcance por P0.5).
- `score` (ordinal) mantiene abstención alta (70%) por la garantía conformal:
  es el precio de no emitir decisiones mal calibradas en una escala subjetiva.
- El híbrido `fast` → `llama` (fallback en abstención) está especificado en
  REQ-027 pero su medición end-to-end queda como siguiente paso.

## 5. Reproducir

```bash
python3 scripts/tydm_fast.py bench          # tabla + métricas
python3 scripts/tydm_fast.py bench --json   # mismos datos en JSON
python3 scripts/tydm_fast.py train          # entrena y guarda el modelo
python3 scripts/tydm_fast.py predict --tipo noul --estado "..." --instrucciones "..."
```

Servidor MCP / consumidores: el backend `fast` es stdlib y determinista
(semilla 20260925); sus decisiones son **experimentales** y no autoritativas
(P1.31): la etiqueta definitiva sigue requiriendo revisión humana.
