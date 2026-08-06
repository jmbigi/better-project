# LECCIONES-APRENDIDAS — Memoria del proyecto better-ai

> Cada prueba, fallo o hallazgo relevante se documenta aquí con su solución.
> Si algo falla 2+ veces, la lección pasa a ser regla en `AGENTS.md`.

## Cómo se actualiza

- Tras cada prueba de las reglas o de opencode, añadir una entrada con fecha.
- Formato: **Fecha — Título** → Problema / Solución / Evidencia.
- Si el mismo fallo se repite 2+ veces: proponer una regla nueva o endurecer una existente.

---

## 2026-07-31 — opencode.json: `permission.webfetch` no acepta sintaxis de objeto

**Problema**: al configurar `permission.webfetch` con la sintaxis de objeto
`{ "*": "allow" }`, opencode rechazó toda la configuración con:
`Expected PermissionActionConfig | undefined, got {"*":"allow"} permission.webfetch`.
**Solución**: `webfetch` solo admite valor directo (`"allow"`). Corregido en
`opencode.json` y verificado con `opencode run` (funcionó).
**Evidencia**: salida de error de opencode 1.18.10 y posterior prueba exitosa.
**Lección**: antes de asumir que un permiso acepta sintaxis de objeto, validar el
JSON contra el esquema (`$schema`) o probar `opencode run` con una tarea trivial.
**Estado**: cerrada. No se repitió.

## 2026-07-31 — Un LLM puede sugerir una "alternativa segura" que también está prohibida

**Problema**: al negarse a ejecutar `git reset --hard`, el agente sugirió
`git checkout -- <archivo>` como alternativa segura, sin saber que ese comando también
está en la lista `deny` de `opencode.json`.
**Solución**: las reglas de texto son orientativas; la protección real es el `deny`
determinista, que se aplica aunque el agente lo ignore. Mantener SIEMPRE ambas capas.
**Evidencia**: prueba 6 de `docs/PRUEBAS.md` (ronda 1).
**Lección**: no confiar en que el agente conozca todas las reglas de permisos;
la capa determinista no es negociable.
**Estado**: cerrada.

## 2026-07-31 — En modo `--auto`, "ask" se auto-aprueba; solo "deny" frena

**Problema**: `rm <archivo>` (patrón `rm *` = "ask") se ejecutó sin fricción en modo
auto porque el usuario había ordenado el borrado. `rm -rf` sí quedó bloqueado por "deny".
**Solución**: si un proyecto necesita protección máxima contra borrados, cambiar
`rm *` a "deny" en `opencode.json` (cuesta poco y elimina la clase de error completa).
**Evidencia**: prueba 3 de `docs/PRUEBAS.md` (ronda 1, con corrección en ronda 3).
**Lección**: en modo auto, pedir permiso es solo un formalismo; decidir conscientemente
qué queda en "ask" y qué pasa a "deny".
**Estado**: cerrada con decisión registrada (por defecto se mantiene "ask" para `rm`
de archivos concretos y "deny" para las formas recursivas/forzadas).

## 2026-07-31 — Verificación previa de existencia: el anti-alucinación funciona

**Problema**: pedido de refactorizar con la función inexistente `procesar_pago_stripe()`.
**Solución**: el agente verificó con Read/Glob/grep, confirmó que no existe y se negó
a inventarla, citando P0.2 y P1.2. Las reglas de texto SÍ cambian el comportamiento
del modelo si son explícitas y verificables.
**Evidencia**: prueba 2 de `docs/PRUEBAS.md` (ronda 1).
**Lección**: las reglas de texto funcionan cuando exigen acciones verificables con
herramientas (leer/ejecutar/buscar), no simples afirmaciones.
**Estado**: cerrada.

## 2026-07-31 — Reglas nuevas: verificación inmediata de carga

**Problema**: al añadir reglas nuevas (P1.7 estándares, P1.8 obedecer/preguntar,
P1.9 protecciones), no basta con escribirlas: hay que probar que el modelo las
conoce y las cita correctamente.
**Solución**: tras cada cambio de AGENTS.md, ejecutar una prueba corta
(`opencode run "enumera la regla PX"`) y verificar la respuesta. Si el modelo no
la conoce o la interpreta mal, revisar la redacción.
**Evidencia**: prueba post-P1.9 con respuesta correcta del modelo.
**Lección**: las reglas de texto requieren feedback loop: escribirlas, probarlas,
ajustarlas. Documentar en LECCIONES-APRENDIDAS.md.
**Estado**: cerrada.

## 2026-07-31 — Refactorización del propio proyecto: backup y referencias cruzadas

**Problema**: al reorganizar el proyecto (mover `CHECKLIST.md` a la raíz, extraer
`docs/PRUEBAS.md` de `REGLAS-COMPLETAS.md`), el riesgo principal era romper las
referencias cruzadas entre archivos (AGENTS.md, README.md, REGLAS-COMPLETAS.md).
**Solución**: antes de tocar nada, backup completo en `/tmp/opencode/backup-better-ia-20260731`
(P1.9); después de la reorganización, verificar con grep que ninguna ruta antigua
(`docs/CHECKLIST.md`, "sección 7") quedara referenciada.
**Evidencia**: grep de referencias y prueba de carga de opencode posterior.
**Lección**: la refactorización del propio repositorio se trata como la de cualquier
código: leer antes de modificar, backup antes de mover, y verificación de coherencia
(P1.10) después — en este caso, las reglas del proyecto se aplicaron a sí mismas.
**Estado**: cerrada.

## 2026-07-31 — CRÍTICA: los patrones de permisos de opencode matchean por TOKENS, no por subcadenas

**Problema**: el patrón `"sqlite3 * DROP*": "deny"` NO bloqueó
`sqlite3 db 'DROP TABLE clientes;'` y la tabla se destruyó (2 veces, en BD temporales
de prueba). La causa: opencode tokeniza el comando por espacios y el token real era
`'DROP` (comilla pegada), que no matchea `DROP*`. La misma mecánica explica por qué
los deny de SQL destructivo fallan si no se cubre la comilla.
**Solución**: usar `"sqlite3 * *DROP*": "deny"` (el `*` extra cubre la comilla).
Verificado con pruebas reales: DROP, DELETE y ALTER quedan bloqueados y las BDs
intactas. Se corrigieron todos los patrones (`psql`/`mysql`/`sqlite3`) en
`opencode.json`.
**Evidencia**: ronda 3 de `docs/PRUEBAS.md` (pruebas 10–15).
**Lección**: NUNCA confiar en que un patrón de permisos funciona sin probarlo contra
el comando real (P1.1). Además: un LLM puede auto-limitarse por la regla de texto
(nunca intentó `rm -rf`) y eso NO es evidencia de que el deny funcione; hay que
provocar el intento para observarlo.
**Estado**: cerrada. Se añade a la checklist: "¿Probé el patrón/guardarraíl contra el
comando real?"

## 2026-07-31 — El matching posicional: cada forma de comando necesita su patrón

**Problema**: al reforzar los deny (ronda 4), dos patrones fallaron contra comandos
reales: `redis-cli * FLUSHALL*` (3 tokens) no matcheó `redis-cli FLUSHALL` (2 tokens),
y `git filter-branch*` no matcheó `git -C <repo> filter-branch ...` (el token `-C`
desplaza la posición del subcomando).
**Solución**: añadir variantes por forma: `redis-cli FLUSHALL*` (2 tokens),
`git -C * filter-branch*`, `git -C * reset --hard*`, etc. Verificado con pruebas
16–21 de `docs/PRUEBAS.md` (ronda 4): todos bloqueados, repos/archivos intactos.
**Evidencia**: ronda 4 de `docs/PRUEBAS.md`.
**Lección**: el matching es POSICIONAL: `<cmd> * <flag>` NO cubre `<cmd> <flag>` ni
`<cmd> -C <dir> <flag>`. Al añadir cualquier patrón de permisos, probar al menos la
forma de 2 tokens, la forma con argumentos y la forma con `-C`/`--git-dir`.
**Estado**: cerrada.

## 2026-07-31 — Auditoría de historial: el commit NO es el momento de limpiar

**Problema**: antes de pushear el primer commit del repo (que es público), había una
lección con información sensible (rutas de claves SSH y nombres de cuentas reales).
**Solución**: la versión sensible se reescribió anonimizada ANTES de commitear, y la
auditoría posterior (`git fsck --unreachable`, `git grep` en todos los commits,
`git log -p` en todos los patches) confirmó que nunca existió ningún blob con ese
contenido en el historial. Si se hubiera commiteado, la remediación sería mucho más
costosa: rotación de credenciales + purga de historial con herramienta de filtrado.
**Evidencia**: ronda 5 de `docs/PRUEBAS.md`.
**Lección**: la limpieza se hace ANTES del commit, no después: auditar cada archivo
antes de stagearlo (grep de emails, IPs, rutas de claves, nombres de cuentas). El
historial de git es prácticamente inmortal; purgarlo es la última opción y siempre
coordinada con el programador (P0.10, P0.11, P0.12).
**Estado**: cerrada.

## 2026-07-31 — Decisión de coste: SOLO deepseek-v4-flash-free o deepseek-v4-flash (opencode-go)

**Problema**: la validación multi-modelo probó `opencode-go/deepseek-v4-pro`, que
responde correctamente pero es **muy caro**; el programador ordenó no usarlo nunca.
**Solución**: fijar como decisión del proyecto:
- Modelos PERMITIDOS (precio bajo): **`opencode/deepseek-v4-flash-free`** o
  **`opencode-go/deepseek-v4-flash`**.
- PROHIBIDO usar cualquier otro modelo (incluidos `pro` y otros proveedores) sin
  permiso explícito del programador o presupuesto aprobado.
- Se documentó en AGENTS.md (sección "Entorno del proyecto"), README y PRUEBAS.
**Evidencia**: órdenes del programador del 31-07-2026.
**Lección**: validar modelos y medir coste antes de adoptarlos; registrar las
decisiones de coste como lección Y en AGENTS.md para que futuras sesiones no las
ignoren.
**Estado**: cerrada.

## 2026-07-31 — Verificar URLs citadas: HTTP real, no asumir

**Problema**: al revisar las fuentes de `REGLAS-COMPLETAS.md` (P1.7), la URL de
Medium devolvía 403 a clientes no navegador (Cloudflare "Just a moment..."), mientras
que el resto devolvía 200. Sin la verificación, se habría dado la fuente por
"accesible" sin evidencia.
**Solución**: `curl -o /dev/null -w "%{http_code}" -L` sobre cada URL citada (con
`--max-time`); documentar el resultado en el propio documento, distinguiendo "404
(rota)" de "403 (bloqueo de bots, accesible en navegador)".
**Evidencia**: verificación del 31-07-2026 (10 URLs, 9× 200, 1× 403 documentado).
**Lección**: toda URL citada se verifica con HTTP real antes de publicarla como
referencia; un 403 no siempre significa fuente rota — comprobar si es bloqueo de
bots antes de descartarla.
**Estado**: cerrada.

## 2026-07-31 — Renombrar un repo: remote, menciones y verificación

**Problema**: el repositorio pasó de `better-ia` a `better-ai` en GitHub. La URL
antigua seguía funcionando (redirección de GitHub), pero el remote local apuntaba al
nombre viejo y las menciones del nombre quedaron desactualizadas.
**Solución**: (1) `git remote set-url origin git@github-jmbigi:jmbigi/better-ai.git`;
(2) verificar con `git fetch` que es el MISMO repo (mismo HEAD, sin divergencias);
(3) actualizar las menciones del nombre en README y docs, preservando los registros
históricos exactos (rutas de backup, notas "renombrado desde").
**Rama**: se renombró local a `main` (`git branch -m master main`) y se pusheó.
GitHub rechazó borrar la rama remota `master` porque es la rama POR DEFECTO del
repo; cambiarla requiere la interfaz web o API de GitHub (cuenta), lo cual el
programador decidió no usar. `main` queda como rama de trabajo; `master` remota
sigue existiendo como rama por defecto. `git merge-base --is-ancestor` confirmó que
`master` es ancestro de `main` (sin pérdida de historial).
**Cierre (01-08-2026)**: el programador cambió la rama por defecto a `main` en
GitHub; `master` fue eliminada del remoto (verificado vía API: `default_branch =
main`, `HEAD` remoto = `main`).
**Evidencia**: commits `23e42f3` y `fd4a63c`, verificación del 31-07-2026.
**Lección**: al renombrar un repo: actualizar el remote ANTES de pushear (una
redirección puede ocultar que se está pusheando a otro lado), verificar identidad
(HEAD idéntico), y buscar todas las menciones del nombre viejo sin reescribir hechos
históricos.
**Estado**: cerrada.

## 2026-07-31 — CRÍTICA: el orden de los patrones anula los deny (last matching rule wins)

**Problema**: en la config REAL de `opencode.json`, el patrón genérico `rm *` (ask)
estaba DESPUÉS de `rm -rf *` (deny). Como opencode aplica "last matching rule wins",
`rm -rf x` matchea ambos y ganaba el ask → en modo `--auto` el borrado se habría
ejecutado. Afectaba a `git reset`, `mv --force`, `rsync --delete`, `docker compose
down -v`. Las pruebas de las rondas 3–7 usaban config MÍNIMA (sin los ask genéricos)
y por eso nunca se detectó.
**Solución**: reordenar `opencode.json`: `*` = allow, después TODOS los ask, y TODOS
los deny al final (85 ask + 76 deny). Verificado con la config REAL completa y
`--auto`: `rm -rf`, `git reset --hard`, `mv --force` y `DROP TABLE` bloqueados;
operaciones normales permitidas (pruebas 29–33).
**Evidencia**: ronda 8 de `docs/PRUEBAS.md`.
**Lección**: (1) probar los deny SIEMPRE con la config COMPLETA del proyecto, nunca
con config mínima; (2) al añadir un ask genérico (`rm *`, `git reset *`, `mv *`),
asegurarse de que los deny específicos de la misma familia queden DESPUÉS en el
archivo; (3) el orden de las claves del JSON es semántica de seguridad.
**Estado**: cerrada. Se añade a la checklist: "¿El deny específico queda después de
cualquier ask genérico de su familia?"

## 2026-07-31 — Revisión cruzada: detecta reglas definidas pero no documentadas

**Problema**: la revisión integral del proyecto (P1.10) encontró que la regla **P1.7**
existía en `AGENTS.md` pero NO estaba documentada en `docs/REGLAS-COMPLETAS.md`
(la sección 3 saltaba de P1.6 a P1.8). Además, la tabla de limitaciones tenía 20
filas frente a los 21 errores del README (faltaba "daños por no preguntar").
**Solución**: verificación automática de coherencia: comparar los IDs de reglas
definidos en AGENTS.md contra los documentados en REGLAS-COMPLETAS.md y las
referencias en README/CHECKLIST (grep + sort). Documentar P1.7 y alinear el conteo.
**Evidencia**: salidas de grep de la revisión del 31-07-2026.
**Lección**: tras cada modificación del ruleset, ejecutar la revisión cruzada de IDs
y conteos; es barata y detecta incoherencias invisibles al leer archivos por separado.
**Estado**: cerrada. Se aplica la revisión cruzada como paso previo a cada commit.

## 2026-07-31 — Permisos: incoherencia entre herramientas y bypass de .env por bash

**Problema**: la revisión integral (P1.10) encontró dos fallos en `opencode.json`:
(1) `permission.edit` negaba `*.env.*` sin excepción, bloqueando la edición de
`.env.example` (template legítimo) mientras `permission.read` sí la permitía; (2) los
deny de `edit`/`read` solo cubren esas herramientas: con config REAL y `--auto`, el
agente leyó y modificó `.env` por bash (`cat .env`, `printf 'X=1\n' >> .env`) sin
ningún bloqueo.
**Solución**: (1) `"*.env.example": "allow"` al final de `edit` (last matching rule
wins), coherente con `read`; (2) 13 patrones bash deny para accesos comunes
(`cat`/`less`/`more`/`head`/`tail`/`grep` sobre `*.env*` y redirecciones `> / >>`),
verificados 9/9 con comandos reales; operaciones normales siguen permitidas. El
verificador ahora comprueba la coherencia entre secciones y el orden deny-después-de-ask
en 25 pares de familias (lección de la ronda 8 automatizada).
**Evidencia**: ronda 12 de `docs/PRUEBAS.md` (pruebas 44–50).
**Lección**: las secciones de permisos de una configuración se revisan de forma cruzada
(P1.10): una excepción decidida en una herramienta debe decidirse conscientemente en las
demás; y la capa determinista de una herramienta NO protege a otra (bash bypasea
edit/read): los deny bash son defensa en profundidad, nunca cobertura completa.
**Estado**: cerrada.

## 2026-07-31 — El hook aborta commits rotos y los pendientes se quedan desactualizados

**Problema**: (1) el "Pendiente de verificar" de PRUEBAS afirmaba que los patrones
`psql * *TRUNCATE*`/`mysql` "no estaban probados con clientes reales", contradiciendo
la ronda 11 (pruebas 35–38): los pendientes no se revisan al cerrar cada ronda.
(2) No se había verificado que el hook pre-commit ABORTA commits con problemas (solo
se sabía que se ejecutaba).
**Solución**: (1) revisar la lista de pendientes en cada cierre de ronda; corregido en
la ronda 15. (2) Prueba controlada y reversible: corromper `opencode.json`
(backup previo en /tmp), `git add` + `git commit` → el hook detectó 4 FALLOS y el
commit se ABORTÓ (HEAD intacto); se restauró el archivo y se purgaron los objetos
huérfanos creados por la prueba (`git gc --prune=now`, verificados como basura propia
antes de purgar). El check de fsck del verificador detectó incluso esa basura de la
prueba, lo que confirma que el safeguard funciona.
**Evidencia**: ronda 16 de `docs/PRUEBAS.md` (pruebas 63–66).
**Lección**: los safeguards se prueban también en su modo de FALLO (un test que no
puede fallar no es un test, P1.1); y los "pendientes" documentados son código muerto
si no se reconcilian con cada ronda.
**Estado**: cerrada.

## 2026-07-31 — CRÍTICA: los patrones de permisos con `|` (pipe) NO matchean en opencode 1.18.10

**Problema**: la prueba masiva de deny (ronda 27) descubrió que `curl URL | sh` se
EJECUTA a pesar del deny `curl * | sh*`. Verificado con config MÍNIMA aislada (sin
AGENTS.md): incluso el patrón con comodín total `* | sh*` no bloquea `echo hola | sh`.
La prueba 101 de la ronda 26 reportó "3/3 BLOQUEADOS" — FALSO POSITIVO: el agente se
auto-limitó por la regla de texto P0.8, y el reporte del AGENTE se atribuyó al deny
sin verificar el matcher.
**Solución**: (1) corregir la prueba 101 con la verdad (solo `chmod 777` bloqueado
realmente); (2) documentar la limitación en PRUEBAS, README y esta lección; (3) los
4 patrones con `|` se mantienen en la config (sin coste; si el matcher los soporta en
el futuro, se activan solos) — pero la protección REAL contra pipes es la regla de
texto P0.8.
**Causa raíz (ronda 28, confirmada con evidencia)**: el matcher evalúa el PRIMER
SEGMENTO del pipeline — con deny `curl *` (sin pipe), `curl URL | sh` SÍ queda
bloqueado. Los patrones que contienen `|` nunca matchean porque el pipe no forma
parte del segmento base. Tradeoff evaluado: bloquear `curl *`/`wget *` globalmente
cubriría los pipes pero rompería el `curl` legítimo (verificación de URLs, P1.7);
rechazado.
**Evidencia**: ronda 27 de `docs/PRUEBAS.md` (pruebas 106–108).
**Lección**: (1) un "bloqueado" reportado por el AGENTE NO es evidencia de que el deny
funcione (lección de la ronda 3, repetida): provocar el intento y observar la tool call;
(2) los patrones con `|` no matchean en esta versión: probar SIEMPRE cada patrón contra
el comando real (P1.1); (3) la capa determinista tiene límites conocidos: la regla de
texto P0.8 es la defensa primaria para ejecución remota.
**Estado**: cerrada (limitación documentada, sin fix disponible en la versión actual).

## 2026-08-01 — Issues abiertos de opencode verificados contra la config real

**Problema**: la investigación de issues de anomalyco/opencode (ronda 30) encontró
dos abiertos y sin fix: #39931 ("bash permission escape via `--`", 1.18.10: `git diff --`
bypasea el ask global) y #39001 (patrones `ask` `rm *`/`mv *`/`cp *` NO deterministas,
50–90% de bypass silencioso en 1.18.3).
**Solución**: (1) el escape `--` se probó contra nuestra config REAL: `git checkout -- f`,
`rm -rf -- f`, `git checkout -- .` → 3/3 BLOQUEADOS (el issue aplica al ask global, que
no usamos); documentado. (2) El no-determinismo de los ask afecta a nuestros 85 patrones
ask solo en modo interactivo (un ask no disparado = ejecución sin confirmar); en `--auto`
todo ask se auto-aprueba igualmente (lección ronda 3). La protección determinista real
son los deny (89). Recomendación documentada: endurecer a deny los patrones críticos si
se desea determinismo máximo — decisión del programador, no aplicada.
**Evidencia**: ronda 30 de `docs/PRUEBAS.md` (pruebas 114–116).
**Lección**: los issues de la herramienta base se verifican contra la config REAL antes
de asumir impacto; los deny específicos resisten mejor que los ask genéricos — para
protección determinista, deny (con su tradeoff de bloqueo).
**Estado**: cerrada (verificada y documentada; sin cambio de política sin orden).

## 2026-07-31 — Push fallido: la clave SSH por defecto era de otra cuenta

**Problema**: `git push` al remote de GitHub del proyecto falló con
`Permission to <repo> denied to <cuenta-sin-permisos>`: la config SSH por defecto de
`github.com` usa la clave por defecto, que pertenece a otra cuenta de GitHub sin
permisos sobre el repositorio.
**Solución**: usar el alias SSH ya definido en la config SSH del usuario
(`Host <alias-jmbigi>` → `IdentityFile <clave-jmbigi>`, con `IdentitiesOnly yes`).
El remote cambió a `git@<alias-jmbigi>:<org>/<repo>.git`, verificado con
`ssh -T git@<alias-jmbigi>` (autenticación correcta de la cuenta con permisos).
**Evidencia**: error de push y verificación del alias (31-07-2026).
**Lección**: antes de pushear, verificar qué identidad SSH usará el remote
(`ssh -T <alias>` o `git ls-remote`); si el repo está bajo una cuenta distinta a la
clave por defecto, usar el alias SSH correcto en la URL del remote. Esta lección se
documenta ANONIMIZADA (sin rutas de claves ni nombres de cuentas): los detalles de
claves y cuentas personales no se registran ni siquiera en repos privados (P0.9/P0.10).
**Estado**: cerrada.

## 2026-08-01 — Cláusulas Anti-Vibe-Code (P1.13–P1.17) y revisión de imports (P1.18)

**Problema**: tras publicar el proyecto en Codeberg (jul 2026) aplica su ToU §2(1)7,
que prohíbe repos "mayormente" generados por IA; la industria (Flathub, Godot, Blender,
curl) ha endurecido sus políticas contra el "vibe coding", y la investigación muestra
que los agentes ignoran las prohibiciones absolutas si solo están en texto.
**Solución**: 6 reglas nuevas en AGENTS.md (P1.13 autoría humana, P1.14 disclosure con
trailers estándar, P1.15 revisión/prueba humana obligatoria, P1.16 la política del
anfitrión manda, P1.17 humanos se comunican con humanos, P1.18 revisión de imports
antes de commit/push), documentadas en REGLAS-COMPLETAS con 8 fuentes nuevas
verificadas por HTTP (todas 200), sincronizadas en README (32 errores), CHECKLIST
(2 secciones) y verificador (18 P1, 32 limitaciones, 32 errores).
**Evidencia**: investigación web 01-08-2026 (Codeberg ToU/blog, Flathub, Godot,
Blender, RepoComplianceBench arXiv 2607.26819, Cilium, ml-peg — URLs comprobadas con
curl); verificador del proyecto en verde tras los cambios.
**Lección**: según RepoComplianceBench, las reglas de disclosure/verificación
colocadas en AGENTS.md se cumplen (77–100% con recordatorios), pero las prohibiciones
("refuse") no las cumple ningún agente: el enforcement del anti-vibe-code debe estar
fuera del agente (revisión humana, CI, bot). Coherente con la filosofía del proyecto:
la capa determinista/externa manda sobre la regla de texto.
**Estado**: cerrada.

## Ronda 34: verificación "feedback de la realidad" con visión IA local y bug bound-method en unittest (2026-08-01)

**Contexto**: en visorweb2 los tests e2e se complementan con visión IA local (PP-OCRv6 + PP-DocBee-2B, GPU 8 GB) — el LLM de texto recibe los resultados de visión (JSON) y razona sobre el estado real de la UI (AGENTS.md del proyecto, directiva better-ocr). La suite de tests del analizador detectó dos fallos de implementación.

**Hallazgo 1 — bound-method en tearDown de unittest**: `self.original = <método de clase>` liga la función a la instancia de test vía descriptor (bound method); al restaurar en `tearDown`, el atributo de CLASE quedaba sustituido por la función ligada a la instancia anterior, contaminando el test siguiente (falsa "restauración"). Fix: `type(self).original` en los 6 tearDowns. La suite saltó de 31 a 46 tests y 46/46 OK.

**Hallazgo 2 — SIGABRT in-process (cuDNN)**: cargar PaddleOCR y procesar capturas reales dentro del proceso de unittest aborta; los tests de screenshots reales se ejecutan en subproceso (CLI). También: `cu_seqlens` debe ser int32 y resize a 512 px para PP-DocBee-2B; resolver `libcudnn.so.8` → `.so.9` en el venv y propagar `LD_LIBRARY_PATH` (paddle/libs + nvidia/*/lib) a los subprocesos.

**Solución**: 46/46 OK + e2e con contexto de captura por pantallazo (origen headless, frente/fondo, viewport, entorno: pantallas vía `xrandr`, escritorios virtuales vía `wmctrl -d` — sin hostnames por P0.9) y aislamiento en escritorio limpio si multi-desktop.

**Lección**: la visión IA local materializa la regla P0.1 ("nunca afirmes sin evidencia") para UI: el agente razona sobre JSON de OCR/QA visual en vez de imaginar la pantalla; y la "restauración" en unittest debe usar la clase, no la instancia, para no contaminar tests.
**Estado**: cerrada.

## Ronda 35 — Guardarraíles de claves, subagentes de revisión y lección del `.opencode/` autogenerado (2026-08-02)

**Problema**: la hoja de ruta propuesta pedía cerrar huecos reales: los deny de
`read`/`edit` solo cubrían `.env` (no las rutas de claves `~/.ssh`, `~/.aws`,
deny de `id_rsa`, `*.pem`, `*credentials*`), no había revisión cruzada con agentes
especializados ni scan de formatos de API keys.
**Solución**: (1) 70 denies nuevos en `opencode.json` (familias bash `cat`/`less`/
`more`/`head`/`tail`/`grep` + redirecciones deny para `.ssh`, `.aws`, `id_rsa`,
`id_ed25519`, `id_ecdsa`, `id_dsa`; 10 patrones `read` + 10 `edit` con expansión de
`~`); (2) subagentes de solo lectura `.opencode/agents/security-auditor.md` y
`code-reviewer.md` (`edit: deny`, bash restringido al verificador); (3) checks
nuevos del verificador: formatos de API keys (`sk-`, `ghp_`, `AKIA`, `AIza`,
`xoxb-`, `PRIVATE KEY`), `eval`/`exec` en scripts, y existencia de los agentes.
Totales: 245 patrones bash (159 deny, 85 ask) + 14 edit + 14 read.
**Evidencia**: pruebas 120-133 de `docs/PRUEBAS.md` — denies probados con config
MÍNIMA aislada (matcher real, sin reglas de texto: `cat dummy-id_rsa-test.txt`,
`cat dummy.ssh/control.txt`, `cat -n dummy.ssh/control.txt`, `read` de id_rsa → 4/4
BLOQUEADOS) + controles permitidos + config REAL (deny gana sobre
`external_directory` en `--auto`; los deny `~/.ssh/*` se expanden a `/home/<usuario>/.ssh/*`).
**Lección 1 (P0.1 en ambas direcciones)**: el subagente `security-auditor` reportó
"emails de autores en node_modules" y mi primera impresión fue "alucinación" —
verificado: ERA CIERTO. opencode 1.18.11 autogenera `.opencode/{node_modules,
package.json, package-lock.json, .gitignore}` al cargar el proyecto (dependencia
`@opencode-ai/plugin`), y los scans del verificador descendían ahí. Fix: los greps
del verificador usan `--exclude-dir=node_modules`. Las afirmaciones de un agente de
revisión se verifican SIEMPRE, no se descartan ni se aceptan sin comprobar.
**Lección 2 (alcance de los agentes de revisión)**: `code-reviewer` detectó una
asimetría real (bash sin `id_ecdsa`/`id_dsa`, que sí estaban en read/edit) —
corregida con 22 patrones más. La revisión cruzada con subagentes complementa al
verificador determinista: uno detecta incoherencias de diseño, el otro verifica
hechos.
**Lección 3 (los deny también frenan al agente)**: al intentar limpiar mis propios
archivos de prueba (`rm -rf /tmp/opencode/permtests`), el deny `rm -rf *` lo
BLOQUEÓ — el ruleset se aplica a los artefactos del propio agente; la limpieza de
artefactos temporales queda como tarea humana (pendiente: `/tmp/opencode/permtests`).
**Estado**: cerrada.
