# better-project

Ecosistema local de gestion de proyecto: requisitos, conocimiento y lecciones
viven en el repositorio como archivos; Git es el versionado; los scripts de
`scripts/` son las herramientas; los agentes de IA (opencode) las consumen
via reglas (`AGENTS.md`) y un servidor MCP local. Todo open source, local y
gratuito: sin nubes, sin Jira, sin Notion.

## Arquitectura: tres pilares

## Pilar 1: requisitos (el contrato)

`REQ-XXX.md` con frontmatter YAML en `.docs/requirements/` (`id`, `titulo`,
`estado` Draft/Aprobado/Implementado/Deprecado, `prioridad`, `version`,
`fecha_creacion`). El codigo que implementa un requisito lleva el comentario
`// REQ-XXX` (o `# REQ-XXX`). `scripts/doc_validator.py` verifica la
trazabilidad: referencias sin archivo, frontmatter invalido, estados
incoherentes (un REQ `Deprecado` referenciado en codigo es error). Se
bloquea el commit via hook de pre-commit.

## Pilar 2: conocimiento (el cerebro)

Markdown estructurado en `.docs/knowledge/` (una idea principal por seccion
H2). `scripts/index_knowledge.py` divide en chunks y los indexa en
`.docs/.storage/` (no versionado): ChromaDB + sentence-transformers
(`all-MiniLM-L6-v2`) si estan instalados, o indice JSON TF-IDF sin
dependencias. Indizado incremental por mtimes.

## Pilar 3: lecciones (la memoria)

`.docs/lessons/<anio>.yaml` (campos `id` LSN-NNN, `proyecto`, `fase`,
`categoria`, `problema`, `recomendacion`, `estado`, `fecha`).
`scripts/lessons_extractor.py` valida y exporta `lessons_context.txt`, que
los agentes leen antes de depurar.

## Los 50 errores de LLM que se previenen

1. **Alucinación**: inventar APIs, archivos, paquetes o resultados (P0.2)
2. **Falsa confirmación**: afirmar éxito sin evidencia (P0.1, P1.1)
3. **Acciones destructivas**: `rm -rf`, resets, drops (P0.3, P0.4)
4. **Ceguera de alcance**: modificar código no relacionado (P1.2)
5. **Degradación de contexto**: olvidar reglas en conversaciones largas (P1.3)
6. **Sicofancia**: confirmar los supuestos del usuario aunque estén mal (P1.3, P1.6)
7. **Dependencias rotas**: instalar/actualizar sin permiso (P1.2, P0.5)
8. **Secretos expuestos**: hardcodear o comitear credenciales (P0.6, P0.7)
9. **Violación de convenciones**: código que no sigue el proyecto (P1.5)
10. **Tests falsos**: tests que no pueden fallar (P1.1)
11. **Bucles de intentos fallidos**: repetir sin replantear (P1.6)
12. **Daño a producción**: migraciones/limpiezas sobre BD productivas (P0.4)
13. **Soluciones obsoletas o no estándar**: sin verificar documentación oficial (P1.7)
14. **Desobediencia / decisiones sin consultar**: ignorar órdenes o asumir intención (P1.8)
15. **Saltarse protecciones**: operaciones de riesgo sin dry-run/backup/sandbox (P1.9)
16. **Ejecución de código peligroso**: pipes a `bash` de contenido descargado, `eval`/`exec` no confiables (P0.8)
17. **Refactor innecesario / archivos superfluos**: tocar código que funciona, crear archivos duplicados (P1.2)
18. **Pérdida de contexto en el código**: borrar comentarios válidos por gusto (P1.5)
19. **Daños evitables por no preguntar**: actuar con ambigüedad sin consultar al programador (P1.8)
20. **Incoherencias ocultas**: ignorar contradicciones o emitir respuestas que se contradicen (P1.10)
21. **Reescrituras masivas**: big bang sin verificar cada paso, cambios acumulados sobre estados rotos (P1.11)
22. **Fuga de información personal**: leer/imprimir/publicar datos personales en proyectos públicos o privados (P0.9)
23. **Claves y datos personales en repos**: commits con `.env`, tokens o datos personales; auditar historial (P0.10)
24. **Filtraciones silenciadas**: no vigilar ramas/commits antiguos u ocultar hallazgos de seguridad (P0.11)
25. **Cambio de claves sin orden**: resets/rotaciones de credenciales que rompen accesos productivos (P0.12)
26. **Entrega mediocre al pedir "mejorar"/"avanzado"**: interpretar "mejorar" como versión mínima y "avanzado" como opcional, sin pulir ni verificar (P1.12)
27. **Autoría falsa de IA**: atribuir co-autoría a modelos o presentar slop como obra propia (P1.13)
28. **Uso de IA oculto**: partes significativas generadas sin declarar (P1.14)
29. **Slop sin revisión humana**: entregar "vibe code" sin que el humano lo entienda y pruebe (P1.15)
30. **Violar la política de IA del repo destino**: ignorar restricciones del anfitrión (P1.16)
31. **IA como intermediaria entre humanos**: responder revisiones con IA en nombre del programador (P1.17)
32. **Imports no verificados**: importar módulos inexistentes, sin usar o con licencia incompatible (P1.18)
33. **Fallbacks que ocultan errores**: código con `try/except` que devuelven defaults, `except: pass`/`catch {}` vacíos o sustituciones silenciosas de APIs que "funciona" pero con resultado incorrecto; también respuestas genéricas (test de intercambiabilidad) sin enfoque granular al caso (P1.19)
34. **Pérdida de memoria del proyecto**: no documentar pruebas, fallos ni hallazgos en `docs/LECCIONES-APRENDIDAS.md`, o documentarlos sin evidencia y sin anonimizar — los errores se repiten porque la lección murió con la sesión (P1.20)
35. **Secuestro del agente (prompt injection)**: obedecer instrucciones maliciosas incrustadas en contenido que el agente procesa (webs, documentos, correos, salidas de herramientas, archivos) como si fueran órdenes del programador (P0.13); incluye filtración del system prompt (OWASP LLM07 System Prompt Leakage)
36. **Integrar sin divide y vencerás**: construir e integrar módulos directamente en el código base sin prototipar y probar cada pieza de forma aislada con casos límite (aislando sus dependencias con mocks/stubs), contaminando un sistema que estaba en verde (P1.21)
37. **Pruebas visuales frágiles en CI**: integrar pruebas de screenshot, OCR o visión IA sin prototipar aislado ni calibrar umbrales; suites visuales en entornos no controlados generan falsos positivos (píxeles, DPI, fuentes, temas) que erosionan la confianza en los tests (P1.21b)
38. **Cambios sin consentimiento visual**: ejecutar cambios sin presentar un diagrama visual y opciones Sí/No/Cancelar al programador (P1.22)
39. **Cambios sin autorización explícita**: ejecutar cambios irreversibles/destructivos/de alto impacto sin confirmación previa del programador; el juicio humano se reserva para decisiones de riesgo (P1.23)
40. **Implementación sin especificación**: no seguir una planilla de requerimientos estándar con criterios de aceptación medibles y trazables; la hoja de requerimientos detallados no puede ser reemplazada por IA (P1.24)
41. **Cambios fuera de especificación**: desviarse de los requerimientos formalizados en la planilla sin declararlo explícitamente ni consultar al programador (P1.25)
42. **Errores silenciosos**: código con `except: pass`, `catch {}` vacíos, defaults ante fallos sin reportar o retornos de `null`/`default` sin logging que "funciona" pero con resultado incorrecto e indetectable; el error se eleva y reporta, no se traga (P1.26)
43. **Consolas web con errores**: entregar código frontend/SPA/PWA con errores en la consola del navegador (`console.error`, `TypeError`, `ReferenceError`, `SyntaxError`, `CORS error`, `Uncaught (in promise)`) sin corregir; verificar consola limpia antes de entregar y capturar errores en tests automatizados (P1.27)
44. **Recreación autónoma de entornos productivos**: borrar servidores, bases de datos, contenedores, directorios productivos, `.env` o configuraciones productivos para "volver a empezar" como solución a un error; no hay "reset productivo" aprobado por la IA: toda recuperación requiere plan humano, backup verificado y confirmación explícita (P0.14)
45. **No verificar destino antes de escribir/borrar**: asumir que un directorio/archivo remoto es "solo build" o "descartable" sin inspeccionarlo, ejecutando operaciones que destruyen contenido real; antes de cualquier rm/rsync/scp/sobrescritura: verificar con `ls`/`cat`/`stat` (P1.28)
46. **Adivinar configuraciones y secretos**: inventar valores para secretos, `.env`, credenciales, API keys o configuraciones faltantes en lugar de reportar la falta al programador; un secreto faltante se resuelve con el humano, no con la IA (P1.29)
47. **Empezar sin leer reglas y documentación**: iniciar tareas sin haber leído `AGENTS.md`, `README.md` y la documentación del proyecto, causando errores por desconocimiento de convenciones, scope creep o uso de modelos no permitidos (P0.15)
48. **Empezar sin detectar entorno**: ejecutar comandos incompatibles, instalar paquetes globales o usar rutas rotas por no identificar el entorno de desarrollo (lenguajes, frameworks, gestores de paquetes) y el SO (Linux, macOS, Windows, WSL, contenedor) (P0.16)
49. **Empezar sin leer el código**: alucinar APIs, romper convenciones, duplicar código o editar a ciegas por no explorar el código base real (estructura, módulos, tests, patrones) antes de modificar (P0.17)
50. **Ejecución de sudo y búsqueda de claves**: la IA nunca ejecuta comandos `sudo` (ni siquiera con autorización del programador), ya que otorgan privilegios de root y pueden instalar paquetes, modificar configs de sistema, cambiar claves de usuarios/BD o gestionar servicios — efectos irreversibles e impredecibles (P0.5). Tampoco busca ni intenta descubrir la clave de root ni de ningún usuario (`sudo su`, `sudo -l`, `cat /etc/shadow`, etc.): expondría credenciales y facilitaría accesos no autorizados (P0.12)

## Integracion con agentes

`AGENTS.md` define el flujo de trabajo (consultar requisitos antes de
implementar, fundamentar en conocimiento, revisar lecciones antes de
depurar). `opencode.json` lanza `scripts/mcp_server.py` como servidor MCP
local con las herramientas `search_knowledge`, `read_requirement`,
`validate_requirements` y `create_lesson`. El guardarrailes de `opencode.json`
hereda el ruleset determinista de better-ai: **304 patrones bash (218 `deny`, 85 `ask`, 1 `allow`)**, bloqueo de lectura/edicion de claves y credenciales, y proveedores de modelo restringidos.

## Estructura

```text
.
├── .docs/
│   ├── requirements/        # REQ-001..N (frontmatter YAML)
│   ├── knowledge/           # architecture/, business-rules/, glossary.md
│   ├── lessons/             # <anio>.yaml (lecciones aprendidas)
│   └── .storage/            # generado: indices (no versionado)
├── .opencode/agents/        # code-reviewer, security-auditor, compliance-checker,
│                            # cost-optimizer, dependency-auditor (solo lectura)
├── scripts/
│   ├── doc_validator.py     # trazabilidad REQ (REQ-001)
│   ├── index_knowledge.py   # indice de conocimiento (REQ-002)
│   ├── lessons_extractor.py # exportacion de lecciones (REQ-003)
│   ├── mcp_server.py        # servidor MCP para agentes (REQ-004, endurecido REQ-007)
│   ├── tui.py               # interfaz TUI minimalista (REQ-006)
│   ├── setup.sh             # onboarding guiado (REQ-008)
│   ├── ci.sh                # CI local sin proveedores (REQ-009)
│   ├── verificar-proyecto.sh# verificacion de coherencia del repo (tests: REQ-010)
│   └── hooks/pre-commit     # hook git local
├── demo/                    # proyecto de ejemplo (gestor de notas CLI)
│   ├── src/notas.py         # codigo con referencias REQ-XXX
│   ├── .docs/requirements/  # REQ-001 (Implementado), REQ-002 (Aprobado), REQ-003 (Deprecado)
│   ├── .docs/knowledge/     # arquitectura + glosario
│   └── .docs/lessons/       # leccion de ejemplo
├── docs/                    # reglas completas, pruebas y lecciones del ruleset
├── AGENTS.md                # reglas IA + directivas del proyecto
├── opencode.json            # guardarrailes + MCP
├── .pre-commit-config.yaml  # hooks pre-commit (framework)
├── CHECKLIST.md             # checklist pre-entrega
└── LICENSE                  # GPL-3.0-or-later
```

## Uso rapido

```bash
# Onboarding guiado: entorno, hook, deps opcionales y primera validacion
bash scripts/setup.sh

# Generar el indice de conocimiento (tras clonar)
python3 scripts/index_knowledge.py

# Consultar el conocimiento
python3 scripts/index_knowledge.py search "tiempo de espera"

# Validar trazabilidad de requisitos
python3 scripts/doc_validator.py --strict

# Validar un proyecto externo (la demo)
python3 scripts/doc_validator.py --root demo

# Exportar lecciones para los agentes
python3 scripts/lessons_extractor.py

# Interfaz TUI (curses, sin dependencias)
python3 scripts/tui.py

# Suite de tests (30 casos, stdlib unittest)
python3 -m unittest discover -s tests -q

# Verificacion completa previa a commit
bash scripts/verificar-proyecto.sh

# CI local sin proveedores: exporta HEAD a copia limpia y verifica alli
bash scripts/ci.sh
```

## Hook de pre-commit (local, sin CI)

El hook ejecuta `verificar-proyecto.sh` antes de cada commit:

```bash
cp scripts/hooks/pre-commit .git/hooks/pre-commit
```

La verificacion cubre reglas, config, seguridad (P0.9/P0.10), trazabilidad
REQ (`--strict`), lecciones, indice de conocimiento y la suite de tests.

## Dependencias opcionales

Sin dependencias, el ecosistema funciona con stdlib (indice JSON TF-IDF). Para
busqueda vectorial real (`requirements-optional.txt`):

```bash
bash scripts/setup.sh    # las instala en .venv, solo tras doble confirmacion
```

⚠️ P0.18: la auditoria `pip-audit` del 2026-09-04
(`docs/SBOM-2026-09-04.spdx.json`, 117 paquetes resueltos) encontro 4
advisories ABIERTOS en chromadb 1.5.9 sin version de parche (inyeccion de
codigo y autorizacion en modo SERVIDOR). El uso local embebido no expone esa
superficie, pero instalarlas implica aceptar el riesgo por escrito; el
backend stdlib es el recomendado por defecto.

## Verificacion y seguridad

`scripts/verificar-proyecto.sh` comprueba reglas, config, seguridad (P0.9,
P0.10) y estado del repositorio antes de cada commit. Los subagentes
`@code-reviewer`, `@security-auditor`, `@compliance-checker`,
`@cost-optimizer` y `@dependency-auditor` anaden una revision humana de solo
lectura (P1.13, P1.15).

## Licencia

**GNU General Public License v3.0 or later** (GPL-3.0-or-later). Texto legal
en `LICENSE` (fuente oficial: https://www.gnu.org/licenses/gpl-3.0.txt).

Las reglas de IA (`AGENTS.md`, `opencode.json`, `.opencode/`) derivan de
[jmbigi/better-ai](https://github.com/jmbigi/better-ai) (CC BY-SA 4.0), del
mismo autor; relicenciadas a GPLv3 por decision del propietario para este
proyecto. La verificacion de coherencia de este repo:

```bash
bash scripts/verificar-proyecto.sh
```
