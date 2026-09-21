# Política de seguridad

> better-project es una herramienta **local-first**. Por defecto no expone
> servicios de red: el único canal con un agente es `scripts/mcp_server.py` por
> **stdio** (JSON-RPC). El modelo de amenazas completo está en
> `docs/THREAT-MODEL.md`.

## Versiones soportadas

El proyecto sigue Git como versionado; se da soporte de seguridad a la rama
`main` y a la última etiqueta publicada. No hay versiones LTS.

| Versión | Soporte |
|---------|---------|
| `main` (HEAD) | Sí |
| Última etiqueta (`v*`) | Sí |
| Etiquetas anteriores | No |

## Cómo reportar una vulnerabilidad

**No abras un issue público** para vulnerabilidades: expondrías el fallo antes
de que exista una corrección.

Usa uno de estos canales privados:

1. **GitHub Security Advisories**: pestaña *Security → Report a vulnerability*
   del repositorio (canal preferido).
2. **Contacto del maintainer**: `security@better-project.local` (dirección local
   de marcador; ver `GOVERNANCE.md`).

Incluye, si es posible:

- Descripción del fallo y su impacto.
- Pasos para reproducirlo (comando exacto, entrada y salida real).
- Versión/commit afectado (`git rev-parse HEAD`).
- Mitigación o parche propuesto, si lo tienes.
- Si el hallazgo es de una **dependencia**, indica paquete y versión.

## Qué puedes esperar

- **Acuse de recibo**: en un plazo de 7 días.
- **Evaluación inicial**: en un plazo de 14 días, con severidad (CVSS) si aplica.
- **Corrección**: según severidad y disponibilidad del maintainer; se coordina
  la divulgación contigo.
- **Crédito**: si lo deseas, se te acredita en el CHANGELOG y en el advisory.

Este es un proyecto mantenido por voluntarios (bus factor 1; ver `GOVERNANCE.md`),
por lo que los plazos son de mejor esfuerzo.

## Alcance

Quedan dentro del alcance, entre otros:

- Eludir los patrones de permiso de `opencode.json`/`kilo.json`
  (218 `deny`, 85 `ask`, 1 `allow`).
- Inyección a través de contenido no confiable procesado por el agente
  (P0.13) o fuga del system prompt (OWASP LLM07).
- Ejecución de código no confiable (`curl | bash`, `eval`/`exec`) vía los
  wrappers o el servidor MCP.
- Fuga de secretos, credenciales o datos personales en el repositorio.
- Fallos en `scripts/mcp_server.py` que rompan los límites de entrada
  (REQ-007) o la auditoría JSONL.

Quedan **fuera** de alcance:

- Vulnerabilidades en dependencias **opcionales** ya documentadas con
  advisories abiertos (chromadb, diskcache): ver `docs/ALCANCE.md` y
  `README.md`.
- Riesgos derivados de instalar dependencias fuera del `.venv` del proyecto.
- El motor Jev, que es **experimental** (accuracy 0.646) y no emite decisiones
  autoritativas (P0.20/P1.31).

## Prácticas del proyecto

- `sudo` está prohibido siempre (P0.5); el agente no modifica el sistema.
- Producción es de solo lectura (P0.4).
- Antes de cada commit corre `bash scripts/verificar-proyecto.sh` (53 checks),
  que audita secretos, datos personales, trazabilidad y seguridad.
- Los `deny` de la configuración son la protección determinista real; un `ask`
  no es un límite duro (ver `docs/THREAT-MODEL.md`).
