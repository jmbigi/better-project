# Reglas de negocio del ecosistema

## Versionado de requisitos

Cada REQ tiene campo `version`: subirla al modificar alcance o criterios.
La `fecha_creacion` no cambia; el historial completo queda en Git.

## Estados validos de un requisito

Draft (borrador, sin compromiso), Aprobado (alcance aceptado, pendiente de
implementar), Implementado (codigo con referencia `REQ-XXX` existe),
Deprecado (fuera de alcance; el codigo no debe referenciarlo).

## Generados no versionados

`.docs/.storage/` (indices) y `lessons_context.txt` (exportacion) son
artefactos generados: no se versionan ni se editan a mano. Se regeneran con
los scripts correspondientes.
