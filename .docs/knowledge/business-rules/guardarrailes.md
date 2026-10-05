# Guardarraíles de agentes (deny/ask/allow)

Conocimiento operativo sobre los guardarraíles deterministas del proyecto.
Fuente: `AGENTS.md`, `opencode.json`/`kilo.json` y `docs/PRUEBAS.md`
(conteos verificados leyendo la config, no solo la documentación).

## Filosofía: deny-all con lista de permitidos

Los guardarraíles viven en `experimental.policies` y `permission` de
`opencode.json`/`kilo.json`. La política de proveedores es deny-all: solo se
permite el proveedor explícito en la allow-list. Los permisos de herramientas
se evalúan por patrones: `deny` bloquea siempre, `ask` exige confirmación
humana, `allow` deja pasar. Un `ask` posterior nunca debe anular un `deny`
(hay un check del verificador que lo audita por familias de patrones).

## Conteos verificados

`permission.bash` contiene 304 patrones: 218 `deny`, 85 `ask` y 1 `allow`.
`edit` y `read` permiten todo excepto `*.env` y `*.env.*` (`deny`): las
plantillas `.env.example` sí se pueden leer y escribir.

## Familias críticas de deny

- Destrucción de archivos: `rm -rf *` y variantes recursivas/forzadas.
- Git destructivo: `git reset --hard*`, `git clean -fdx*`, `git push --force*`.
- Bases de datos: `DROP`, `TRUNCATE`, `DELETE` sin `WHERE` (patrones `psql`/`mysql`/`sqlite3`).
- Sistema operativo: `sudo *` (prohibido siempre, P0.5), gestores de paquetes del sistema.

## Perfiles de autonomía (puertas de revisión)

- `audit`: solo lectura/verificación; subagentes con `edit: deny`.
- `plan`: lectura + propuesta; lo destructivo queda en `ask`.
- `build`: ejecución controlada; los `deny` bloquean lo irreversible.

En modo `--auto` los `ask` se auto-aprueban: la protección determinista real
son los `deny`. Para máxima seguridad, mover patrones críticos de `ask` a
`deny` en la copia local de la config.

## Verificación de los propios guardarraíles

El verificador comprueba: conteos coherentes README/config, pares críticos
deny presentes, que ningún `ask` anule un `deny`, y bloqueo de `.env` en
`edit`/`read`. Sonda de comportamiento en runtime (manual, gasta tokens,
P0.19): `python scripts/probar_policies.py {provider|bash|all}` (REQ-031).
