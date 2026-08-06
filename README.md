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

## Integracion con agentes

`AGENTS.md` define el flujo de trabajo (consultar requisitos antes de
implementar, fundamentar en conocimiento, revisar lecciones antes de
depurar). `opencode.json` lanza `scripts/mcp_server.py` como servidor MCP
local con las herramientas `search_knowledge`, `read_requirement`,
`validate_requirements` y `create_lesson`. El guardarrailes de `opencode.json`
hereda el ruleset determinista de better-ai: **245 patrones** de permisos
bash (**159 `deny`**, **85 `ask`**), bloqueo de lectura/edicion de claves y
credenciales, y proveedores de modelo restringidos.

## Estructura

```text
.
├── .docs/
│   ├── requirements/        # REQ-001..N (frontmatter YAML)
│   ├── knowledge/           # architecture/, business-rules/, glossary.md
│   ├── lessons/             # <anio>.yaml (lecciones aprendidas)
│   └── .storage/            # generado: indices (no versionado)
├── .opencode/agents/        # security-auditor, code-reviewer (solo lectura)
├── scripts/
│   ├── doc_validator.py     # trazabilidad REQ (REQ-001)
│   ├── index_knowledge.py   # indice de conocimiento (REQ-002)
│   ├── lessons_extractor.py # exportacion de lecciones (REQ-003)
│   ├── mcp_server.py        # servidor MCP para agentes (REQ-004)
│   ├── verificar-proyecto.sh# verificacion de coherencia del repo
│   └── hooks/pre-commit     # hook git local
├── docs/                    # reglas completas, pruebas y lecciones del ruleset
├── AGENTS.md                # reglas IA + directivas del proyecto
├── opencode.json            # guardarrailes + MCP
├── .pre-commit-config.yaml  # hooks pre-commit (framework)
├── CHECKLIST.md             # checklist pre-entrega
└── LICENSE                  # GPL-3.0-or-later
```

## Uso rapido

```bash
# Generar el indice de conocimiento (tras clonar)
python3 scripts/index_knowledge.py

# Consultar el conocimiento
python3 scripts/index_knowledge.py search "tiempo de espera"

# Validar trazabilidad de requisitos
python3 scripts/doc_validator.py --strict

# Exportar lecciones para los agentes
python3 scripts/lessons_extractor.py

# Verificacion completa previa a commit
bash scripts/verificar-proyecto.sh
```

## Dependencias opcionales

Sin dependencias, el ecosistema funciona con stdlib (indice JSON TF-IDF). Para
busqueda vectorial real:

```bash
pip install chromadb sentence-transformers   # en venv del proyecto
```

## Verificacion y seguridad

`scripts/verificar-proyecto.sh` comprueba reglas, config, seguridad (P0.9,
P0.10) y estado del repositorio antes de cada commit. Los subagentes
`@security-auditor` y `@code-reviewer` anaden una revision humana de solo
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
