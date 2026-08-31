# Instrucciones para GitHub Copilot

Este repositorio define sus reglas operativas en `AGENTS.md`. Antes de proponer
cambios, lee `AGENTS.md`, `README.md`, `CHECKLIST.md`, la documentación relevante
de `docs/` y la configuración de la herramienta afectada.

## Flujo obligatorio

1. Inspecciona el entorno, el estado de Git y el código relevante antes de editar.
2. Formula una hipótesis local y el chequeo que puede refutarla.
3. Para funcionalidades o cambios significativos, consulta `.docs/requirements/`
   y referencia el requisito implementado como `REQ-XXX` en el código.
4. Haz cambios pequeños y conserva las convenciones existentes.
5. Ejecuta el chequeo más específico inmediatamente después de editar y luego la
   verificación completa disponible (`bash scripts/verificar-proyecto.sh`).
6. Valida la trazabilidad de requisitos con `python3 scripts/doc_validator.py --strict`.
7. No inventes APIs, resultados, archivos, configuraciones ni secretos.
8. No ejecutes acciones destructivas, sobre producción o sobre credenciales.
9. Reporta evidencia real, fallos y elementos no verificados; no ocultes errores.

`AGENTS.md` y estas instrucciones se complementan: ante una regla de seguridad,
privacidad, autorización o verificación, prevalece la protección más estricta.

No asumas que un permiso de Copilot equivale a un bloqueo determinista: los
bloqueos dependen del runtime o sandbox activo.
