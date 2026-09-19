---
id: ADR-003
titulo: Auto-auditoria propia con stdlib antes de adoptar herramientas externas
estado: Aceptado
fecha: 2026-09-19
---

# ADR-003: Auto-auditoria propia con stdlib antes de adoptar herramientas externas

## Contexto

El Pilar 4 exige auditar sesgos, decisiones y calidad del propio repositorio. La
investigacion (2026-09-19) identifico herramientas externas utiles (Vale para
prosa, mutmut para tests, pip-audit para dependencias) y otras especificas de
modelos ML que no aplican aqui. El proyecto prioriza stdlib, local y sin coste;
incorporar 3 o mas dependencias exige un ADR y pasar P0.18.

## Alternativas consideradas

- **Alternativa A — No auditar**: mantener solo el verificador actual (39
  checks); coste 0, pero no cubre sesgos, frescura de evidencias ni tests
  debiles.
- **Alternativa B — Adoptar ya Vale + mutmut + pip-audit**: cobertura amplia,
  pero suma 3 dependencias, binarios externos y mantenimiento antes de saber si
  el equipo las usa.
- **Alternativa C — Auto-auditoria propia en stdlib y externas opcionales
  despues (elegida)**: `scripts/auto_audit.py` con 5 subcomandos sin
  dependencias; las externas quedan documentadas como propuestas en
  `docs/HERRAMIENTAS-Y-FUENTES.md`.

## Decision

Se adopta la Alternativa C. `auto_audit.py` cubre sesgos documentales,
frescura del SBOM, decisiones pendientes, tests debiles y trazabilidad de IA, y
se integra en el verificador (1 check nuevo). Las herramientas externas se
adoptan solo si un ADR posterior justifica su coste.

## Consecuencias

- **Positivas**: 0 dependencias nuevas; corre en cualquier proyecto que copie 1
  archivo; cubre 5 clases de riesgo (P1.1, P1.14, P1.26, P0.18 y Pilar 4).
- **Negativas / deuda asumida**: las heuristicas textuales y de AST tienen
  falsos positivos y falsos negativos; no reemplazan herramientas maduras como
  mutmut ni un linter de prosa.
- **Reversibilidad**: alta; es un script aislado sin estado.

## Supuestos

- El equipo ejecuta el verificador en cada pre-commit (ya es el caso).
- Las heuristicas detectan una parte util del problema; la revision humana
  sigue siendo necesaria.

## Metricas de exito

- `python3 scripts/auto_audit.py all` termina con 0 errores.
- El verificador mantiene 40 checks (39 previos + 1 de auto-auditoria) en verde.
- 0 dependencias nuevas en `requirements-optional.txt` por este ADR.

## Premortem

Si en 6 meses la auto-auditoria produce ruido y se ignora, las causas probables
serian: (1) demasiados falsos positivos, (2) alertas sin responsables, o (3) no
integrarse en el flujo. Mitigacion: mantener la lista blanca de documentos
normativos, integrarla en el pre-commit y revisar las alertas en la
retrospectiva.

## Referencias

- `docs/HERRAMIENTAS-Y-FUENTES.md`, REQ-014, `docs/SESGOS-Y-FALACIAS.md`.
- ADR-002 (adopcion del Pilar 4).
