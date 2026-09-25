# Alcance y casos de uso

## Para qué sirve

Ecosistema **local-first** para que un programador (o un equipo pequeño) gestione
requisitos, conocimiento, lecciones y control de sesgos como archivos Git, y los
consuma con agentes de IA vía `AGENTS.md` + un servidor MCP local. Sin nube, sin
Jira/Notion, sin dependencias obligatorias.

## Encaje recomendado

| Caso | Adecuado | Notas |
|---|---|---|
| Uso personal / investigación | **Sí** | Backend stdlib por defecto |
| Equipo pequeño / open source | **Sí** | Trazabilidad y CI local reproducibles |
| Entorno regulado / auditoría formal | **No aún** | Falta auditoría externa y SLSA |
| Producción crítica / enterprise | **No aún** | Ver limitaciones abajo |

## Qué NO promete

- **Verificación independiente**: "verde" = pasa los checks del propio proyecto
  (`scripts/ci.sh`), no una auditoría de terceros.
- **Reproducibilidad bit a bit** de modelos: `seed` no está soportado por
  opencode (`docs/ARQUITECTURA-DETERMINISMO.md`).
- **IA fiable para decidir**: Jev es experimental (accuracy 0.646); ningún tipo
  experimental emite decisión autoritativa (P0.20/P1.31).
- **Cero riesgo de dependencias**: los extras opcionales tienen 5 advisories sin
  parche (chromadb/diskcache); el backend stdlib evita instalarlos.

## Procedencia (estado actual)

- Sin releases firmadas ni SLSA >= 2: la procedencia verificable hoy es
  **commit Git + `requirements-optional.lock` (hashes) + SBOM CycloneDX**
  (generado con `syft` v1.52.0, binario verificado por checksum SHA256).
- `syft` está instalado localmente (`.local/bin`, sin sudo) y el verificador
  lo usa si está disponible (regenera el SBOM en temp si falta).
  `grype`/`openssf scorecard` no están instalados; su adopción requiere
  autorización explícita (P0.5) y no forma parte del CI por defecto.

## Camino a producción (si algún día aplica)

1. Cerrar/aislar advisories y lock con hashes (hecho el lock; advisories abiertos).
2. Mutación en todos los módulos críticos y en CI.
3. Auditoría externa + threat model revisado (`docs/THREAT-MODEL.md`).
4. Procedencia firmada (SLSA) y política de releases.
