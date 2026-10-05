# Verificación local-first

Conocimiento operativo sobre la arquitectura de verificación del proyecto:
todo se verifica en local, sin cuentas ni servicios externos. Fuente:
`scripts/ci.sh`, `scripts/verificar-proyecto.sh`, `scripts/verificar_proyecto.py`
y la salida real del verificador (59 checks OK / 0 FALLOS, 2026-10-05).

## Principio rector

La verificación es local y gratuita por diseño (REQ-009): no se requiere
cuenta de forja, CI remoto ni pago. Los workflows de `.github/workflows/` son
opcionales y nunca sustituyen a `bash scripts/ci.sh`.

## CI local: copia limpia de HEAD

`bash scripts/ci.sh` exporta HEAD a una copia temporal limpia y ejecuta allí
toda la verificación. Así detecta archivos no versionados que enmascararían
fallos en el árbol de trabajo. Al terminar regenera `docs/health.md`
(REQ-024) y registra el run en `.docs/.storage/health_runs.jsonl`.

## Hook pre-commit

`scripts/hooks/pre-commit` ejecuta `verificar-proyecto.sh --pre-commit` sobre
una copia temporal del repo y aborta el commit si hay fallos (REQ-010). El
hook `commit-msg` exige el trailer `Assisted-by:` cuando aplica (REQ-019).
Ambos hooks se instalan con `scripts/setup.sh` y el verificador comprueba que
son idénticos a los scripts fuente.

## El verificador y sus capas

`verificar-proyecto.sh` (bash) y `verificar_proyecto.py` (Python) son dos
implementaciones con paridad exigida: mismo nombre de checks y mismos
alcances. Cubren seguridad (sin secretos/PII/`eval`), ecosistema (trazabilidad
REQ y StrictDoc, lecciones, retrieval recall@10 >= 0.7, suite aislada por
proceso, SBOM reproducible) y repositorio (hooks, git fsck, rama
sincronizada). El lint (ruff) cubre todo el Python versionado: `scripts`,
`tests` y `demo/src` (REQ-034).

## Capas opcionales con SKIP

Las herramientas que requieren instalación autorizada (syft para SBOM,
strictdoc para export HTML, ruff) degradan con `[SKIP]` si no están: el check
se omite sin marcar fallo. Consecuencia honesta: una corrida con SKIP es
menos evidencia que una con OK; el SKIP se reporta, nunca se oculta.

## Mutation testing

`python scripts/mutation_check.py --batch` corre en `ci.sh` y mide la fuerza
real de la suite (umbral 0.85; último batch medido 1.000 en `docs/health.md`).
`--all` es a demanda por coste de tiempo.
