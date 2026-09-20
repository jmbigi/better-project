# Auditoría externa reproducible

Objetivo: que un tercero pueda clonar el repositorio y obtener, con un solo
comando, la misma verificación que ejecuta el proyecto. "Verde" significa que
pasan los checks de ESTE proyecto (auto-verificación); no sustituye una
auditoría de seguridad ni una revisión de estándares externos (se declara abajo).

## Requisitos

- `git` y `bash`.
- `python3` >= 3.10 (solo stdlib; sin dependencias obligatorias).

## Procedimiento

```bash
git clone <url-del-repo> better-project
cd better-project
bash scripts/ci.sh
```

`scripts/ci.sh` exporta `HEAD` a un directorio limpio (`git archive`), instala
allí el hook de pre-commit, ejecuta la sintaxis, la suite, la verificación
completa y la mutación multi-módulo, y falla si algo está en rojo (REQ-009).

## Salida esperada

- `[OK] bash -n en todos los scripts`
- Suite de tests: `OK`.
- `verificar-proyecto.sh --pre-commit`: **todos `[OK]`, 0 `[FALLO]`**.
- `mutation_check.py --batch`: `Batch: <muertos>/<total> score >= 0.800`.
- Cierre: `CI local VERDE.`

El script **no** borra el directorio temporal (P0.3); imprime su ruta
`/tmp/better-project-ci-XXXXXX` para que el operador lo elimine manualmente.

## Reproducir el SBOM y la severidad (P0.18/REQ-020)

```bash
pip-audit --no-deps -f cyclonedx-json -r requirements-optional.lock \
    -o docs/SBOM-$(date +%F).cdx.json
python3 scripts/audit_advisories.py --requirements requirements-optional.lock
```

El contrato reproducible es `requirements-optional.lock` (hashes transitivos).
Hallazgo vigente (2026-09-20): 5 advisories sin parche (4 en chromadb 1.5.9, 1
en diskcache 5.6.3), de severidad alta en modo **servidor** y mitigados por el
uso local embebido (LSN-007); CVSS/CVE via OSV en la salida de
`audit_advisories.py`.

## Qué NO cubre

- Pruebas de seguridad externas ni pentest.
- Ejecución del motor Jev (requiere el modelo GGUF y cómputo): no forma parte
  de `ci.sh`.
- Instalación de dependencias opcionales (chromadb, sentence-transformers,
  llama-cpp-python): `ci.sh` usa solo stdlib.
- Reproducibilidad bit a bit de los modelos (seed no soportado por opencode;
  ver `docs/ARQUITECTURA-DETERMINISMO.md`).
